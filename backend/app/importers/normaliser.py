from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

WORLD_CUP_YEARS = [1987, 1991, 1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023]

COUNTRY_ALIASES = {
    "all blacks": "New Zealand",
    "new zealand": "New Zealand",
    "nz": "New Zealand",
    "springboks": "South Africa",
    "south africa": "South Africa",
    "rsa": "South Africa",
    "wallabies": "Australia",
    "australia": "Australia",
    "chile": "Chile",
    "spain": "Spain",
    "england": "England",
    "france": "France",
    "cote divoire": "Ivory Coast",
    "côte divoire": "Ivory Coast",
    "ivory coast": "Ivory Coast",
    "ireland": "Ireland",
    "wales": "Wales",
    "scotland": "Scotland",
    "argentina": "Argentina",
    "fiji": "Fiji",
    "japan": "Japan",
    "italy": "Italy",
    "samoa": "Samoa",
    "western samoa": "Samoa",
    "tonga": "Tonga",
    "usa": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "canada": "Canada",
    "uruguay": "Uruguay",
    "namibia": "Namibia",
    "portugal": "Portugal",
    "georgia": "Georgia",
    "romania": "Romania",
    "zimbabwe": "Zimbabwe",
}

POSITION_ALIASES = {
    "1": "LH",
    "loosehead": "LH",
    "loosehead prop": "LH",
    "lh": "LH",
    "prop": "TBC",
    "2": "HK",
    "hooker": "HK",
    "hk": "HK",
    "3": "TH",
    "tighthead": "TH",
    "tighthead prop": "TH",
    "th": "TH",
    "4": "LK4",
    "lock": "LK4",
    "locks": "LK4",
    "second row": "LK4",
    "second-row": "LK4",
    "lk": "LK4",
    "lk4": "LK4",
    "5": "LK5",
    "lk5": "LK5",
    "6": "BSF",
    "blindside": "BSF",
    "blindside flanker": "BSF",
    "bsf": "BSF",
    "7": "OSF",
    "openside": "OSF",
    "openside flanker": "OSF",
    "osf": "OSF",
    "flanker": "TBC",
    "back row": "TBC",
    "loose forward": "TBC",
    "8": "N8",
    "number 8": "N8",
    "number eight": "N8",
    "no. 8": "N8",
    "n8": "N8",
    "9": "SH",
    "scrum half": "SH",
    "scrum-half": "SH",
    "scrumhalf": "SH",
    "sh": "SH",
    "10": "FH",
    "fly half": "FH",
    "fly-half": "FH",
    "flyhalf": "FH",
    "fh": "FH",
    "11": "LW",
    "left wing": "LW",
    "lw": "LW",
    "wing": "TBC",
    "12": "IC",
    "inside centre": "IC",
    "inside center": "IC",
    "ic": "IC",
    "13": "OC",
    "outside centre": "OC",
    "outside center": "OC",
    "centre": "TBC",
    "center": "TBC",
    "oc": "OC",
    "14": "RW",
    "right wing": "RW",
    "rw": "RW",
    "15": "FB",
    "fullback": "FB",
    "full back": "FB",
    "fb": "FB",
    "utility": "UTIL",
    "util": "UTIL",
    "tbc": "TBC",
    "": "TBC",
}

CAPTAIN_VALUES = {"1", "true", "yes", "y", "captain", "c", "(c)"}
REPLACEMENT_VALUES = {"1", "true", "yes", "y", "replacement", "replaced"}


@dataclass(frozen=True)
class NameParts:
    first_name: Optional[str]
    last_name: Optional[str]


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_reference_marks(value: str) -> str:
    value = re.sub(r"\[[^\]]+\]", "", value)
    value = value.replace("*", "")
    return collapse_whitespace(value)


def normalise_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"['`’ʻ.]", "", value)
    return collapse_whitespace(value).lower()


def normalise_player_name(value: str) -> str:
    name = strip_reference_marks(value)
    name = re.sub(r"\s+\((c|captain)\)$", "", name, flags=re.IGNORECASE)
    return collapse_whitespace(name)


def has_captain_marker(value: str) -> bool:
    return bool(re.search(r"\((c|captain)\)\s*$", value.strip(), flags=re.IGNORECASE))


def split_player_name(player_name: str) -> NameParts:
    parts = player_name.split()
    if len(parts) <= 1:
        return NameParts(first_name=None, last_name=None)
    return NameParts(first_name=parts[0], last_name=" ".join(parts[1:]))


def normalise_country(value: str) -> str:
    country = strip_reference_marks(value)
    return COUNTRY_ALIASES.get(normalise_key(country), country)


def normalise_position(value: str) -> str:
    return POSITION_ALIASES.get(normalise_key(value), value.strip().upper() or "TBC")


def normalise_positions(value: str) -> list[str]:
    if not value:
        return []

    raw_positions = re.split(r"[/,;|]", value)
    positions: list[str] = []
    for raw_position in raw_positions:
        position = normalise_position(raw_position)
        if position and position not in positions:
            positions.append(position)
    return positions


def normalise_bool(value: str, true_values: set[str]) -> bool:
    return normalise_key(value) in true_values


def normalise_captain(value: str) -> bool:
    return normalise_bool(value, CAPTAIN_VALUES)


def normalise_replacement(value: str) -> bool:
    return normalise_bool(value, REPLACEMENT_VALUES)
