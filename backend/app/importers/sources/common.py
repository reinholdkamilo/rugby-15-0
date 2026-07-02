from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

from ...database import BACKEND_DIR
from ...position_eligibility import to_storage_position_code
from ..normaliser import normalise_country, normalise_key

POSITION_PRIORITY = [
    "LH",
    "HK",
    "TH",
    "LK",
    "BF",
    "OF",
    "NE",
    "SH",
    "FH",
    "IC",
    "OC",
    "WG",
    "FB",
]

POSITION_TEXT_ALIASES = {
    "loosehead prop": "LH",
    "loosehead": "LH",
    "hooker": "HK",
    "tighthead prop": "TH",
    "tighthead": "TH",
    "lock": "LK",
    "second row": "LK",
    "blindside flanker": "BF",
    "blind side flanker": "BF",
    "blind-side flanker": "BF",
    "openside flanker": "OF",
    "open side flanker": "OF",
    "open-side flanker": "OF",
    "number eight": "NE",
    "number 8": "NE",
    "no. 8": "NE",
    "8": "NE",
    "scrumhalf": "SH",
    "scrum half": "SH",
    "scrum-half": "SH",
    "halfback": "SH",
    "flyhalf": "FH",
    "fly half": "FH",
    "fly-half": "FH",
    "first five": "FH",
    "first five-eighth": "FH",
    "first five eighth": "FH",
    "inside centre": "IC",
    "inside center": "IC",
    "outside centre": "OC",
    "outside center": "OC",
    "wing": "WG",
    "winger": "WG",
    "left wing": "WG",
    "right wing": "WG",
    "fullback": "FB",
    "full back": "FB",
    "full-back": "FB",
}

AMBIGUOUS_POSITION_TERMS = {
    "prop",
    "flanker",
    "centre",
    "center",
    "back row",
    "utility",
    "utility back",
    "back",
}

COUNTRY_HINTS = {
    "usa": ["usa", "united states", "american"],
    "ivory coast": ["ivory coast", "cote divoire", "cote d'ivoire", "ivorian"],
    "new zealand": ["new zealand", "new zealander"],
    "south africa": ["south africa", "south african"],
    "australia": ["australia", "australian"],
    "england": ["england", "english"],
    "france": ["france", "french"],
    "ireland": ["ireland", "irish"],
    "wales": ["wales", "welsh"],
    "scotland": ["scotland", "scottish"],
    "argentina": ["argentina", "argentine"],
    "fiji": ["fiji", "fijian"],
    "japan": ["japan", "japanese"],
    "italy": ["italy", "italian"],
    "samoa": ["samoa", "samoan"],
    "tonga": ["tonga", "tongan"],
    "canada": ["canada", "canadian"],
    "uruguay": ["uruguay", "uruguayan"],
    "namibia": ["namibia", "namibian"],
    "georgia": ["georgia", "georgian"],
    "romania": ["romania", "romanian"],
    "russia": ["russia", "russian"],
    "spain": ["spain", "spanish"],
    "portugal": ["portugal", "portuguese"],
    "chile": ["chile", "chilean"],
    "zimbabwe": ["zimbabwe", "zimbabwean"],
}


@dataclass(frozen=True)
class ScrapeResult:
    player_name: str
    country: str
    position_raw: str
    position_code: str
    confidence: float
    source_url: str
    source_name: str
    notes: str = ""


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str
    score: float


@dataclass(frozen=True)
class SourceConfig:
    source_name: str
    domains: tuple[str, ...]
    search_templates: tuple[str, ...]


@dataclass
class ScrapeContext:
    cache_dir: Path = field(default_factory=lambda: BACKEND_DIR / "cache" / "position_scrape")
    refresh: bool = False
    delay_seconds: float = 0.25
    timeout_seconds: float = 3.0
    user_agent: str = "Rugby15-0/1.0 (+polite TBC position scraping)"
    session: requests.Session = field(default_factory=requests.Session)
    warnings: list[str] = field(default_factory=list)
    _last_request_at: float = 0.0
    _robots_cache: dict[str, robotparser.RobotFileParser] = field(default_factory=dict)
    _robots_denied: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.session.headers.update({"User-Agent": self.user_agent})

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def source_cache_dir(self, source_name: str) -> Path:
        return self.cache_dir / source_name

    def cache_path(self, source_name: str, kind: str, cache_key: str, suffix: str) -> Path:
        return self.source_cache_dir(source_name) / kind / f"{cache_key}{suffix}"

    def cache_key(self, *parts: str) -> str:
        digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()
        return digest

    def load_json(self, path: Path) -> Optional[dict[str, Any]]:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

    def save_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def fetch_json(
        self,
        url: str,
        source_name: str,
        kind: str,
        cache_key: str,
    ) -> dict[str, Any]:
        cache_path = self.cache_path(source_name, kind, cache_key, ".json")
        if cache_path.exists() and not self.refresh:
            cached = self.load_json(cache_path)
            if cached is not None:
                return cached

        if not self.allowed_by_robots(url):
            self.warn(f"{source_name}: blocked by robots.txt for {url}")
            return {}

        self.throttle()
        try:
            response = self.session.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            self.warn(f"{source_name}: failed to fetch JSON {url}: {exc}")
            return {}
        except ValueError as exc:
            self.warn(f"{source_name}: invalid JSON from {url}: {exc}")
            return {}

        self.save_json(cache_path, payload)
        return payload

    def fetch_text(
        self,
        url: str,
        source_name: str,
        kind: str,
        cache_key: str,
    ) -> str:
        cache_path = self.cache_path(source_name, kind, cache_key, ".html")
        if cache_path.exists() and not self.refresh:
            return cache_path.read_text(encoding="utf-8", errors="ignore")

        if not self.allowed_by_robots(url):
            self.warn(f"{source_name}: blocked by robots.txt for {url}")
            return ""

        self.throttle()
        try:
            response = self.session.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            self.warn(f"{source_name}: failed to fetch page {url}: {exc}")
            return ""

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(response.text, encoding="utf-8")
        return response.text

    def allowed_by_robots(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        if parsed.netloc in self._robots_denied:
            return False

        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._robots_cache.get(parsed.netloc)
        if parser is None:
            parser = robotparser.RobotFileParser()
            cache_key = self.cache_key(robots_url)
            cache_path = self.cache_path("robots", "files", cache_key, ".txt")
            if cache_path.exists() and not self.refresh:
                try:
                    parser.parse(cache_path.read_text(encoding="utf-8", errors="ignore").splitlines())
                    self._robots_cache[parsed.netloc] = parser
                except Exception:
                    self._robots_denied.add(parsed.netloc)
                    return False
            else:
                try:
                    if not self.allowed_to_fetch_robots(parsed.scheme, parsed.netloc):
                        self._robots_denied.add(parsed.netloc)
                        return False
                    text = self._fetch_robots_text(robots_url)
                    if not text:
                        self._robots_denied.add(parsed.netloc)
                        return False
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(text, encoding="utf-8")
                    parser.parse(text.splitlines())
                    self._robots_cache[parsed.netloc] = parser
                except Exception:
                    self._robots_denied.add(parsed.netloc)
                    return False

        return parser.can_fetch(self.user_agent, url)

    def allowed_to_fetch_robots(self, scheme: str, netloc: str) -> bool:
        return scheme in {"http", "https"} and bool(netloc)

    def _fetch_robots_text(self, robots_url: str) -> str:
        self.throttle()
        try:
            response = self.session.get(robots_url, timeout=self.timeout_seconds)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            self.warn(f"Failed to fetch robots.txt {robots_url}: {exc}")
            return ""

    def throttle(self) -> None:
        if self.delay_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay_seconds:
            time.sleep(self.delay_seconds - elapsed)
        self._last_request_at = time.monotonic()


class RugbySourceAdapter:
    def __init__(self, config: SourceConfig, context: Optional[ScrapeContext] = None) -> None:
        self.config = config
        self.context = context or ScrapeContext(
            cache_dir=BACKEND_DIR / "cache" / "position_scrape",
        )

    def set_context(self, context: ScrapeContext) -> None:
        self.context = context

    def find_player_position(self, player_name: str, country: str) -> Optional[ScrapeResult]:
        cache_key = self.context.cache_key(self.config.source_name, player_name, country)
        cached = self.context.load_json(
            self.context.cache_path(self.config.source_name, "parsed", cache_key, ".json"),
        )
        if cached is not None and not self.context.refresh:
            return self._result_from_cache(cached)

        best_result = self._search_and_parse(player_name, country)
        self.context.save_json(
            self.context.cache_path(self.config.source_name, "parsed", cache_key, ".json"),
            self._cache_payload(best_result),
        )
        return best_result

    def _search_and_parse(self, player_name: str, country: str) -> Optional[ScrapeResult]:
        search_hits = self.search_player(player_name, country)
        if not search_hits:
            return None

        candidates: list[ScrapeResult] = []
        seen_urls: set[str] = set()
        for hit in search_hits:
            if hit.url in seen_urls:
                continue
            seen_urls.add(hit.url)
            page_html = self.context.fetch_text(
                hit.url,
                self.config.source_name,
                "pages",
                self.context.cache_key(hit.url),
            )
            if not page_html:
                continue
            result = self.parse_profile_page(player_name, country, hit.url, page_html, hit.title)
            if result is not None:
                candidates.append(result)

        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda result: (-result.confidence, len(result.position_raw), result.source_url),
        )[0]

    def search_player(self, player_name: str, country: str) -> list[SearchHit]:
        hits: list[SearchHit] = []
        seen_urls: set[str] = set()
        for query in self.queries_for(player_name, country):
            for template in self.config.search_templates:
                search_url = template.format(query=quote_plus(query))
                cache_key = self.context.cache_key(search_url)
                cache_path = self.context.cache_path(
                    self.config.source_name,
                    "search",
                    cache_key,
                    ".json",
                )
                cached_search = self.context.load_json(cache_path)
                if cached_search is not None and not self.context.refresh:
                    hits.extend(self.search_hits_from_cache(cached_search))
                    continue

                page = self.context.fetch_text(
                    search_url,
                    self.config.source_name,
                    "search",
                    cache_key,
                )
                if not page:
                    continue
                extracted_hits = self.extract_hits_from_html(
                    page,
                    search_url,
                    player_name,
                    country,
                )
                self.context.save_json(
                    cache_path,
                    {
                        "search_url": search_url,
                        "hits": [
                            {
                                "url": hit.url,
                                "title": hit.title,
                                "snippet": hit.snippet,
                                "score": hit.score,
                            }
                            for hit in extracted_hits
                        ],
                    },
                )
                hits.extend(extracted_hits)

        ranked_hits = sorted(
            {hit.url: hit for hit in hits}.values(),
            key=lambda hit: (-hit.score, len(hit.title), hit.url),
        )

        for hit in ranked_hits:
            if hit.url not in seen_urls:
                seen_urls.add(hit.url)

        return ranked_hits

    def queries_for(self, player_name: str, country: str) -> list[str]:
        country = country.strip()
        base_queries = [
            player_name,
            f"{player_name} rugby",
            f"{player_name} {country}",
            f"{player_name} {country} rugby",
        ]
        return [query for query in base_queries if query.strip()]

    def extract_hits_from_payload(
        self,
        payload: dict[str, Any],
        search_url: str,
        player_name: str,
        country: str,
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        base_url = f"{urlparse(search_url).scheme}://{urlparse(search_url).netloc}"

        for candidate in self.flatten_payload_candidates(payload):
            url = candidate.get("url") or candidate.get("href") or candidate.get("link")
            title = candidate.get("title") or candidate.get("name") or ""
            snippet = candidate.get("snippet") or candidate.get("text") or ""
            if not url:
                continue
            absolute_url = urljoin(base_url, str(url))
            score = self.score_search_hit(title, absolute_url, snippet, player_name, country)
            if score <= 0:
                continue
            hits.append(
                SearchHit(
                    url=absolute_url,
                    title=strip_whitespace(title) or absolute_url,
                    snippet=strip_whitespace(snippet),
                    score=score,
                ),
            )

        return hits

    def search_hits_from_cache(self, payload: dict[str, Any]) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for item in payload.get("hits", []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", ""))
            title = str(item.get("title", ""))
            snippet = str(item.get("snippet", ""))
            score = float(item.get("score", 0.0))
            if not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    title=title or url,
                    snippet=snippet,
                    score=score,
                ),
            )
        return hits

    def extract_hits_from_html(
        self,
        html: str,
        search_url: str,
        player_name: str,
        country: str,
    ) -> list[SearchHit]:
        soup = BeautifulSoup(html, "html.parser")
        base_url = f"{urlparse(search_url).scheme}://{urlparse(search_url).netloc}"
        hits: list[SearchHit] = []

        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")
            if not href:
                continue
            absolute_url = urljoin(base_url, href)
            if not self.url_is_allowed_domain(absolute_url):
                continue
            title = strip_whitespace(anchor.get_text(" ", strip=True))
            snippet = strip_whitespace(self.anchor_snippet(anchor))
            score = self.score_search_hit(title, absolute_url, snippet, player_name, country)
            if score <= 0:
                continue
            hits.append(
                SearchHit(
                    url=absolute_url,
                    title=title or absolute_url,
                    snippet=snippet,
                    score=score,
                ),
            )

        return hits

    def parse_profile_page(
        self,
        player_name: str,
        country: str,
        source_url: str,
        html: str,
        title_hint: str = "",
    ) -> Optional[ScrapeResult]:
        soup = BeautifulSoup(html, "html.parser")
        title_text = strip_whitespace(soup.title.get_text(" ", strip=True)) if soup.title else ""
        heading_text = strip_whitespace(
            " ".join(tag.get_text(" ", strip=True) for tag in soup.find_all(["h1", "h2"])[:3]),
        )
        page_text = strip_whitespace(soup.get_text("\n", strip=True))
        jsonld_texts = self.extract_jsonld_texts(soup)
        candidate_blocks = [
            ("title", title_text),
            ("heading", heading_text),
            ("jsonld", " ".join(jsonld_texts)),
        ]

        for label, snippet in candidate_blocks:
            result = self.result_from_snippet(
                player_name=player_name,
                country=country,
                source_url=source_url,
                source_name=self.config.source_name,
                snippet=snippet,
                label=label,
            )
            if result is not None:
                return result

        for snippet in self.table_snippets(soup):
            result = self.result_from_snippet(
                player_name=player_name,
                country=country,
                source_url=source_url,
                source_name=self.config.source_name,
                snippet=snippet,
                label="table",
            )
            if result is not None:
                return result

        for snippet in self.labelled_snippets(page_text):
            result = self.result_from_snippet(
                player_name=player_name,
                country=country,
                source_url=source_url,
                source_name=self.config.source_name,
                snippet=snippet,
                label="text",
            )
            if result is not None:
                return result

        return None

    def result_from_snippet(
        self,
        player_name: str,
        country: str,
        source_url: str,
        source_name: str,
        snippet: str,
        label: str,
    ) -> Optional[ScrapeResult]:
        position = self.position_from_snippet(snippet)
        if position is None:
            return None

        name_score = self.name_match_score(player_name, snippet)
        country_score = self.country_match_score(country, snippet)
        confidence = self.base_confidence_for_label(label) + name_score + country_score
        if name_score == 0 and country_score == 0:
            confidence = min(confidence, 0.82)
        if confidence > 0.99:
            confidence = 0.99

        notes = f"Matched from {label} snippet"
        if name_score == 0:
            notes += "; weak player-name match"
        if country_score == 0:
            notes += "; country not explicit"

        return ScrapeResult(
            player_name=player_name,
            country=country,
            position_raw=snippet.strip(),
            position_code=position,
            confidence=confidence,
            source_url=source_url,
            source_name=source_name,
            notes=notes,
        )

    def position_from_snippet(self, snippet: str) -> Optional[str]:
        text = normalise_text(snippet)
        if not text:
            return None

        if text in AMBIGUOUS_POSITION_TERMS:
            return None

        labeled = self.extract_position_label(text)
        if labeled is not None:
            return labeled

        for token in self.tokenize_positions(text):
            mapped = POSITION_TEXT_ALIASES.get(token)
            if mapped is not None:
                return mapped

        return None

    def extract_position_label(self, text: str) -> Optional[str]:
        patterns = [
            r"(?:^|\b)(?:playing position|primary position|current position|position|role)\s*[:\-=]\s*([^\n|]+)",
            r"(?:^|\b)positions?\s*[:\-=]\s*([^\n|]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            raw_value = match.group(1)
            for token in self.tokenize_positions(raw_value):
                mapped = POSITION_TEXT_ALIASES.get(token)
                if mapped is not None:
                    return mapped
        return None

    def tokenize_positions(self, text: str) -> list[str]:
        cleaned = re.sub(r"[\[\]\(\)\{\}]", " ", text)
        cleaned = cleaned.replace("&", " and ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
        parts = re.split(r"[,/;]| and | or ", cleaned)
        tokens: list[str] = []
        for part in parts:
            part = strip_whitespace(part.lower())
            if not part:
                continue
            tokens.append(part)
        tokens.sort(key=len, reverse=True)
        return tokens

    def table_snippets(self, soup: BeautifulSoup) -> list[str]:
        snippets: list[str] = []
        for row in soup.find_all("tr"):
            cells = [strip_whitespace(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            label = normalise_key(cells[0])
            if "position" in label or "role" in label:
                snippets.append(" ".join(cells[1:]))

        for dt in soup.find_all("dt"):
            label = normalise_key(dt.get_text(" ", strip=True))
            if "position" in label or "role" in label:
                dd = dt.find_next_sibling("dd")
                if dd is not None:
                    snippets.append(dd.get_text(" ", strip=True))

        return snippets

    def labelled_snippets(self, text: str) -> list[str]:
        snippets: list[str] = []
        for pattern in [
            r"(?:playing position|primary position|current position|position|role)\s*[:\-=]\s*([^\n.]+)",
            r"(?:positions?)\s*[:\-=]\s*([^\n.]+)",
        ]:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                snippets.append(match.group(1))
        return snippets

    def extract_jsonld_texts(self, soup: BeautifulSoup) -> list[str]:
        texts: list[str] = []
        for script in soup.find_all("script", type="application/ld+json"):
            script_text = script.string or script.get_text(" ", strip=True)
            if not script_text:
                continue
            try:
                payload = json.loads(script_text)
            except json.JSONDecodeError:
                continue
            texts.extend(self.flatten_json_text(payload))
        return texts

    def flatten_json_text(self, value: Any) -> list[str]:
        texts: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and key.lower() in {"jobtitle", "description", "name"}:
                    texts.append(item)
                texts.extend(self.flatten_json_text(item))
        elif isinstance(value, list):
            for item in value:
                texts.extend(self.flatten_json_text(item))
        return texts

    def anchor_snippet(self, anchor: Any) -> str:
        parent = anchor.parent
        if parent is None:
            return ""
        return strip_whitespace(parent.get_text(" ", strip=True))

    def score_search_hit(
        self,
        title: str,
        url: str,
        snippet: str,
        player_name: str,
        country: str,
    ) -> float:
        score = 0.0
        title_text = normalise_key(title)
        snippet_text = normalise_key(snippet)
        url_text = normalise_key(url)
        player_key = normalise_key(player_name)
        surname = normalise_key(player_name.split()[-1]) if player_name.split() else ""
        country_key = normalise_key(country)

        if player_key and player_key in title_text:
            score += 4.0
        if surname and surname in title_text:
            score += 2.0
        if player_key and player_key in snippet_text:
            score += 3.0
        if surname and surname in snippet_text:
            score += 1.5
        if country_key and country_key in title_text:
            score += 1.0
        if country_key and country_key in snippet_text:
            score += 1.0
        if player_key and player_key.replace(" ", "") in url_text.replace(" ", ""):
            score += 2.0
        if surname and surname in url_text:
            score += 0.75
        if "player" in url_text or "profile" in url_text:
            score += 0.25

        return score

    def url_is_allowed_domain(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc in {domain.replace("https://", "").replace("http://", "") for domain in self.config.domains}:
            return True
        return any(parsed.netloc.endswith(domain) for domain in self.config.domains)

    def base_confidence_for_label(self, label: str) -> float:
        if label in {"table", "heading"}:
            return 0.95
        if label == "title":
            return 0.92
        if label == "jsonld":
            return 0.96
        return 0.9

    def name_match_score(self, player_name: str, snippet: str) -> float:
        player_key = normalise_key(player_name)
        snippet_key = normalise_key(snippet)
        if not player_key:
            return 0.0
        if player_key == snippet_key:
            return 0.03
        if player_key in snippet_key:
            return 0.02
        surname = normalise_key(player_name.split()[-1]) if player_name.split() else ""
        if surname and surname in snippet_key:
            return 0.01
        return 0.0

    def country_match_score(self, country: str, snippet: str) -> float:
        if not country:
            return 0.0
        country_key = normalise_key(country)
        snippet_key = normalise_key(snippet)
        hints = COUNTRY_HINTS.get(country_key, [country_key])
        for hint in hints:
            if normalise_key(hint) in snippet_key:
                return 0.02
        return 0.0

    def flatten_payload_candidates(self, value: Any) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if isinstance(value, dict):
            if any(key in value for key in {"url", "href", "link", "title", "name", "snippet", "text"}):
                candidates.append(value)
            for item in value.values():
                candidates.extend(self.flatten_payload_candidates(item))
        elif isinstance(value, list):
            for item in value:
                candidates.extend(self.flatten_payload_candidates(item))
        return candidates

    def _cache_payload(self, result: Optional[ScrapeResult]) -> dict[str, Any]:
        if result is None:
            return {"result": None}
        return {
            "result": {
                "player_name": result.player_name,
                "country": result.country,
                "position_raw": result.position_raw,
                "position_code": result.position_code,
                "confidence": result.confidence,
                "source_url": result.source_url,
                "source_name": result.source_name,
                "notes": result.notes,
            }
        }

    def _result_from_cache(self, payload: dict[str, Any]) -> Optional[ScrapeResult]:
        result = payload.get("result")
        if not result:
            return None
        return ScrapeResult(
            player_name=str(result.get("player_name", "")),
            country=str(result.get("country", "")),
            position_raw=str(result.get("position_raw", "")),
            position_code=str(result.get("position_code", "")),
            confidence=float(result.get("confidence", 0.0)),
            source_url=str(result.get("source_url", "")),
            source_name=str(result.get("source_name", self.config.source_name)),
            notes=str(result.get("notes", "")),
        )


def strip_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def storage_position_code(game_position_code: str) -> str:
    code = normalise_key(game_position_code).upper()
    if code == "LK":
        return "LK4"
    return to_storage_position_code(game_position_code)
