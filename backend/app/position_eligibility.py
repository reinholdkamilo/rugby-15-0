from __future__ import annotations

from typing import Iterable, Optional

GAME_POSITION_ORDER = [
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
    "TBC",
]

PLAYABLE_POSITION_CODES = [
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

POSITION_ALIASES = {
    "LOCK": "LK",
    "LK4": "LK",
    "LK5": "LK",
    "BSF": "BF",
    "BF": "BF",
    "OSF": "OF",
    "OF": "OF",
    "N8": "NE",
    "NE": "NE",
    "LW": "WG",
    "RW": "WG",
    "W": "WG",
    "WG": "WG",
}

STORAGE_POSITION_ALIASES = {
    "BF": "BSF",
    "OF": "OSF",
    "NE": "N8",
    "WG": "LW",
    "LOCK": "LK",
    "LK4": "LK",
    "LK5": "LK",
}

ELIGIBILITY_GROUPS = [
    {"FH", "FB", "IC"},
    {"OF", "BF", "NE"},
    {"LH", "TH"},
]


def to_game_position_code(value: Optional[str]) -> str:
    if value is None:
        return ""
    code = value.strip().upper()
    return POSITION_ALIASES.get(code, code)


def to_storage_position_code(value: str) -> str:
    raw_code = value.strip().upper()
    if raw_code in {"LW", "RW", "BSF", "OSF", "N8", "LK"}:
        return raw_code
    game_code = to_game_position_code(value)
    return STORAGE_POSITION_ALIASES.get(game_code, game_code)


def ordered_position_codes(codes: Iterable[str]) -> list[str]:
    seen = {code for code in codes if code}
    return sorted(
        seen,
        key=lambda code: (
            GAME_POSITION_ORDER.index(code)
            if code in GAME_POSITION_ORDER
            else len(GAME_POSITION_ORDER),
            code,
        ),
    )


def expand_position_codes(codes: Iterable[str]) -> list[str]:
    expanded = {to_game_position_code(code) for code in codes}
    expanded.discard("")

    for group in ELIGIBILITY_GROUPS:
        if expanded.intersection(group):
            expanded.update(group)

    return ordered_position_codes(expanded)


def expand_position_codes_for_draft(codes: Iterable[str]) -> list[str]:
    expanded = expand_position_codes(codes)
    if "TBC" in expanded:
        return PLAYABLE_POSITION_CODES.copy()
    return expanded


def parse_needed_positions(raw_positions: Optional[str]) -> list[str]:
    if not raw_positions:
        return []

    return ordered_position_codes(
        to_game_position_code(code)
        for code in raw_positions.split(",")
        if code.strip()
    )
