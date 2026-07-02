from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import BACKEND_DIR, SessionLocal
from ..models import Player, Position, SpinPool, SquadAppearance
from ..position_eligibility import expand_position_codes
from .schema_utils import ensure_spin_pool_schema

REPORT_PATH = BACKEND_DIR / "reports" / "tbc_position_enrichment_report.json"
REVIEW_PATH = BACKEND_DIR / "reports" / "tbc_position_review.csv"

WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "Rugby15-0/1.0 (TBC position enrichment)"
HIGH_CONFIDENCE_THRESHOLD = 0.9

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

WIKITEXT_POSITION_ALIASES = {
    "loosehead prop": ("LH", 0.98),
    "hooker": ("HK", 0.98),
    "tighthead prop": ("TH", 0.98),
    "lock": ("LK", 0.96),
    "blindside flanker": ("BF", 0.98),
    "openside flanker": ("OF", 0.98),
    "number eight": ("NE", 0.98),
    "number 8": ("NE", 0.98),
    "scrum-half": ("SH", 0.98),
    "scrumhalf": ("SH", 0.98),
    "fly-half": ("FH", 0.98),
    "flyhalf": ("FH", 0.98),
    "inside centre": ("IC", 0.98),
    "inside center": ("IC", 0.98),
    "outside centre": ("OC", 0.98),
    "outside center": ("OC", 0.98),
    "left wing": ("WG", 0.98),
    "right wing": ("WG", 0.98),
    "wing": ("WG", 0.92),
    "fullback": ("FB", 0.98),
}

AMBIGUOUS_TERMS = {
    "prop",
    "flanker",
    "back row",
    "centre",
    "center",
    "utility",
    "utility back",
    "back",
}

CSV_COLUMNS = [
    "player_name",
    "country",
    "year",
    "current_position",
    "suggested_position",
    "source",
    "confidence",
    "reason",
    "notes",
]


@dataclass(frozen=True)
class PositionCandidate:
    code: str
    source: str
    confidence: float
    evidence: str
    raw_value: str


def enrich_tbc_positions(db: Session, dry_run: bool = False) -> dict[str, Any]:
    positions_by_code = {
        position.code: position for position in db.scalars(select(Position)).all()
    }
    tbc_position = positions_by_code.get("TBC")

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "summary": {
            "tbc_before": 0,
            "positions_updated": 0,
            "still_tbc": 0,
            "unresolved_players": 0,
            "unresolved_appearances": 0,
        },
        "source_count": {},
        "updates": [],
        "unresolved_players": [],
        "warnings": [],
    }

    if tbc_position is None:
        report["warnings"].append("TBC position is not seeded; enrichment skipped.")
        return report

    appearances = load_tbc_appearances(db, tbc_position.id)
    report["summary"]["tbc_before"] = len(appearances)

    grouped_appearances: dict[int, list[SquadAppearance]] = defaultdict(list)
    for appearance in appearances:
        grouped_appearances[appearance.player_id].append(appearance)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    source_counter: Counter[str] = Counter()
    unresolved_rows: list[dict[str, Any]] = []

    for player_id, player_appearances in grouped_appearances.items():
        player = player_appearances[0].player
        if player is None or player.country is None:
            continue

        result = infer_player_position(session, player.display_name, player.country.name)
        if result is None or result.confidence < HIGH_CONFIDENCE_THRESHOLD:
            unresolved_rows.extend(
                build_review_rows(player_appearances, result, reason_for(result))
            )
            continue

        source_counter[result.source] += len(player_appearances)
        for appearance in player_appearances:
            report["updates"].append(
                {
                    "player_id": player.id,
                    "player_name": player.display_name,
                    "country": appearance.country.name,
                    "year": appearance.tournament.year,
                    "squad_appearance_id": appearance.id,
                    "from_position": "TBC",
                    "to_position": result.code,
                    "source": result.source,
                    "confidence": result.confidence,
                    "evidence": result.evidence,
                    "raw_value": result.raw_value,
                }
            )
            if not dry_run:
                apply_position_update(appearance, positions_by_code[result.code], result)
            report["summary"]["positions_updated"] += 1

    report["summary"]["still_tbc"] = report["summary"]["tbc_before"] - report["summary"][
        "positions_updated"
    ]
    report["summary"]["unresolved_players"] = len(grouped_unresolved_players(unresolved_rows))
    report["summary"]["unresolved_appearances"] = len(unresolved_rows)
    report["source_count"] = dict(source_counter)
    report["unresolved_players"] = unresolved_rows

    if report["summary"]["tbc_before"] > 0 and report["summary"]["positions_updated"] == 0:
        report["warnings"].append(
            "No high-confidence structured position matches were found; all TBC rows remain pending manual review."
        )

    if dry_run:
        db.rollback()
    else:
        db.commit()

    write_report(report)
    write_review_csv(unresolved_rows)
    return report


def load_tbc_appearances(db: Session, tbc_position_id: int) -> list[SquadAppearance]:
    return db.scalars(
        select(SquadAppearance)
        .options(
            selectinload(SquadAppearance.player).selectinload(Player.country),
            selectinload(SquadAppearance.country),
            selectinload(SquadAppearance.tournament),
            selectinload(SquadAppearance.position),
            selectinload(SquadAppearance.spin_pool_entries),
        )
        .where(SquadAppearance.position_id == tbc_position_id)
        .order_by(SquadAppearance.tournament_id, SquadAppearance.country_id, SquadAppearance.player_id),
    ).all()


def infer_player_position(
    session: requests.Session,
    player_name: str,
    country_name: str,
) -> PositionCandidate | None:
    for candidate in search_wikidata_candidates(session, player_name, country_name):
        if candidate is not None:
            return candidate

    for candidate in search_wikipedia_infobox(session, player_name, country_name):
        if candidate is not None:
            return candidate

    return None


def search_wikidata_candidates(
    session: requests.Session,
    player_name: str,
    country_name: str,
) -> list[PositionCandidate]:
    results = wikidata_search(session, player_name)
    candidates: list[PositionCandidate] = []

    for result in results:
        if not wikidata_result_matches_context(result, player_name, country_name):
            continue

        qid = result.get("id")
        if not qid:
            continue

        claims = wikidata_claims(session, qid)
        for raw_value in extract_claim_values(claims, "P413"):
            candidate = position_candidate_from_text(
                raw_value,
                source="wikidata:P413",
                confidence=0.97,
                evidence=f"Wikidata {qid}",
            )
            if candidate is not None:
                candidates.append(candidate)

    return ranked_candidates(candidates)


def search_wikipedia_infobox(
    session: requests.Session,
    player_name: str,
    country_name: str,
) -> list[PositionCandidate]:
    titles = wikipedia_search_titles(session, player_name, country_name)
    candidates: list[PositionCandidate] = []

    for title in titles:
        wikitext = wikipedia_wikitext(session, title)
        if not wikitext:
            continue

        for raw_value in extract_infobox_positions(wikitext):
            candidate = position_candidate_from_text(
                raw_value,
                source="wikipedia:infobox",
                confidence=0.94,
                evidence=title,
            )
            if candidate is not None:
                candidates.append(candidate)

    return ranked_candidates(candidates)


def wikidata_search(session: requests.Session, player_name: str) -> list[dict[str, Any]]:
    try:
        response = session.get(
            WIKIDATA_API_URL,
            params={
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "type": "item",
                "search": player_name,
                "limit": 10,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        return list(data.get("search", []))
    except requests.RequestException:
        return []


def wikidata_claims(session: requests.Session, qid: str) -> dict[str, Any]:
    try:
        response = session.get(
            WIKIDATA_API_URL,
            params={
                "action": "wbgetentities",
                "format": "json",
                "ids": qid,
                "languages": "en",
                "props": "claims",
            },
            timeout=15,
        )
        response.raise_for_status()
        entities = response.json().get("entities", {})
        return entities.get(qid, {}).get("claims", {})
    except requests.RequestException:
        return {}


def wikipedia_search_titles(
    session: requests.Session,
    player_name: str,
    country_name: str,
) -> list[str]:
    queries = [
        f'"{player_name}" {country_name} rugby union',
        f"{player_name} {country_name} rugby union",
        f'"{player_name}" rugby union',
        player_name,
    ]
    titles: list[str] = []
    seen: set[str] = set()

    for query in queries:
        try:
            response = session.get(
                WIKIPEDIA_API_URL,
                params={
                    "action": "query",
                    "list": "search",
                    "format": "json",
                    "srsearch": query,
                    "srlimit": 10,
                },
                timeout=15,
            )
            response.raise_for_status()
            results = response.json().get("query", {}).get("search", [])
        except requests.RequestException:
            continue

        for result in results:
            title = result.get("title")
            if not title or title in seen:
                continue
            seen.add(title)
            titles.append(title)

    return titles


def wikipedia_wikitext(session: requests.Session, title: str) -> str:
    try:
        response = session.get(
            WIKIPEDIA_API_URL,
            params={
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "format": "json",
                "formatversion": 2,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("parse", {}).get("wikitext", "")
    except requests.RequestException:
        return ""


def extract_claim_values(claims: dict[str, Any], property_id: str) -> list[str]:
    values: list[str] = []
    for claim in claims.get(property_id, []):
        mainsnak = claim.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        datavalue = mainsnak.get("datavalue", {}).get("value", {})
        if isinstance(datavalue, dict) and datavalue.get("id"):
            values.append(str(datavalue["id"]))
    return values


def extract_infobox_positions(wikitext: str) -> list[str]:
    match = re.search(
        r"\|\s*position\s*=\s*(.+?)(?=\n\|[a-zA-Z_]+\s*=|\n\}\}|\Z)",
        wikitext,
        flags=re.DOTALL,
    )
    if not match:
        return []

    raw = match.group(1)
    cleaned = (
        raw.replace("{{", "")
        .replace("}}", "")
        .replace("[[", "")
        .replace("]]", "")
    )
    cleaned = re.sub(r"\|", ",", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    parts = re.split(r"[,/;]| and ", cleaned)
    return [part.strip() for part in parts if part.strip()]


def position_candidate_from_text(
    raw_value: str,
    source: str,
    confidence: float,
    evidence: str,
) -> PositionCandidate | None:
    normalised = normalise_text(raw_value)
    if not normalised:
        return None

    for part in split_candidate_parts(normalised):
        code, position_confidence = map_position_text(part)
        if code is None:
            continue
        if position_confidence < HIGH_CONFIDENCE_THRESHOLD:
            continue
        return PositionCandidate(
            code=code,
            source=source,
            confidence=min(confidence, position_confidence),
            evidence=evidence,
            raw_value=raw_value.strip(),
        )

    return None


def split_candidate_parts(raw_value: str) -> list[str]:
    parts = re.split(r"[,/;]|\band\b", raw_value)
    return [part.strip() for part in parts if part.strip()]


def map_position_text(value: str) -> tuple[Optional[str], float]:
    text = normalise_text(value)
    if not text:
        return None, 0.0

    if text in AMBIGUOUS_TERMS:
        return None, 0.0

    mapped = WIKITEXT_POSITION_ALIASES.get(text)
    if mapped is not None:
        return mapped

    if text in POSITION_PRIORITY:
        return text, 0.95

    return None, 0.0


def ranked_candidates(candidates: Iterable[PositionCandidate]) -> list[PositionCandidate]:
    unique: dict[tuple[str, str], PositionCandidate] = {}
    for candidate in candidates:
        key = (candidate.code, candidate.source)
        current = unique.get(key)
        if current is None or candidate.confidence > current.confidence:
            unique[key] = candidate

    return sorted(
        unique.values(),
        key=lambda candidate: (
            -candidate.confidence,
            POSITION_PRIORITY.index(candidate.code)
            if candidate.code in POSITION_PRIORITY
            else len(POSITION_PRIORITY),
            candidate.source,
        ),
    )


def normalise_text(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("rugby union", "")
    value = value.replace("rugby", "")
    value = value.replace("player", "")
    value = value.replace("infobox", "")
    value = value.replace("position(s)", "position")
    value = re.sub(r"\(\s*captain\s*\)", "", value)
    value = re.sub(r"\(\s*c\s*\)", "", value)
    value = re.sub(r"\[\[|\]\]", "", value)
    value = re.sub(r"\{\{|\}\}", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ,;/")


def country_hint_matches(country_name: str, description: str) -> bool:
    country = normalise_text(country_name)
    if not country:
        return True

    description = normalise_text(description)
    hints = {
        "usa": ["usa", "united states", "american"],
        "ivory coast": ["ivory coast", "cote divoire", "ivorian"],
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
    for hint in hints.get(country, [country]):
        if hint in description:
            return True
    return False


def wikidata_result_matches_context(
    result: dict[str, Any],
    player_name: str,
    country_name: str,
) -> bool:
    label = normalise_text(str(result.get("label", "")))
    description = normalise_text(str(result.get("description", "")))
    query = normalise_text(player_name)

    if query and label == query:
        return True

    if country_name and country_hint_matches(country_name, description):
        return True

    if country_name and country_hint_matches(country_name, label):
        return True

    # Keep exact player matches even when Wikidata omits a country hint.
    if query and query in label:
        return True

    return False


def apply_position_update(
    appearance: SquadAppearance,
    position: Position,
    result: PositionCandidate,
) -> None:
    appearance.position = position
    appearance.notes = merge_enrichment_note(
        appearance.notes,
        source=result.source,
        confidence=result.confidence,
        position_code=result.code,
    )
    eligible_positions = ",".join(expand_position_codes([result.code]))
    for spin_pool in appearance.spin_pool_entries:
        spin_pool.eligible_positions = eligible_positions


def merge_enrichment_note(
    existing_notes: Optional[str],
    source: str,
    confidence: float,
    position_code: str,
) -> str:
    note = (
        f"Position enriched: {position_code} "
        f"(source: {source}, confidence: {confidence:.2f})"
    )
    if not existing_notes:
        return note
    if note in existing_notes:
        return existing_notes
    return f"{existing_notes}; {note}"


def build_review_rows(
    appearances: list[SquadAppearance],
    result: PositionCandidate | None,
    reason: str,
) -> list[dict[str, Any]]:
    review_rows: list[dict[str, Any]] = []
    for appearance in appearances:
        review_rows.append(
            {
                "player_name": appearance.player.display_name,
                "country": appearance.country.name,
                "year": appearance.tournament.year,
                "current_position": "TBC",
                "suggested_position": result.code if result else "",
                "source": result.source if result else "",
                "confidence": f"{result.confidence:.2f}" if result else "",
                "reason": reason,
                "notes": (result.raw_value if result else ""),
            }
        )
    return review_rows


def reason_for(result: PositionCandidate | None) -> str:
    if result is None:
        return "No trusted structured position source found"
    return "Confidence below threshold"


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def write_review_csv(rows: list[dict[str, Any]], path: Path = REVIEW_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def grouped_unresolved_players(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("player_name", "")), str(row.get("country", "")))
        for row in rows
        if row.get("player_name")
    }


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Enrich TBC squad appearance positions from public sources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database.",
    )
    args = parser.parse_args(argv)

    ensure_spin_pool_schema()
    with SessionLocal() as db:
        report = enrich_tbc_positions(db, dry_run=args.dry_run)

    print(json.dumps(report, indent=2))
    print(f"Enrichment report written to {REPORT_PATH}")
    print(f"Review CSV written to {REVIEW_PATH}")


if __name__ == "__main__":
    main()
