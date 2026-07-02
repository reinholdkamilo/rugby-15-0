from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

from . import models

DEFAULT_PLAYER_RATING = 80.0

STARTING_XV_POSITIONS = [
    "LH",
    "HK",
    "TH",
    "LK",
    "LK",
    "BSF",
    "OSF",
    "N8",
    "SH",
    "FH",
    "LW",
    "IC",
    "OC",
    "RW",
    "FB",
]

PACK_POSITIONS = {"LH", "HK", "TH", "LK", "BSF", "OSF", "N8"}
SPINE_POSITIONS = {"SH", "FH", "IC", "FB"}
BACKLINE_POSITIONS = {"SH", "FH", "LW", "IC", "OC", "RW", "FB"}


@dataclass
class PickRatings:
    position: str
    overall: float
    attack: float
    defence: float
    set_piece: float
    breakdown: float
    goal_kicking: float


def normalize_position(position: str) -> str:
    code = position.strip().upper()
    if code in {"LK", "LK4", "LK5", "LOCK"}:
        return "LK"
    return code


def average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def rating_for_pick(pick: models.DraftPick) -> Optional[models.Rating]:
    squad_appearance = pick.squad_appearance
    for rating in squad_appearance.ratings:
        if rating.player_id == pick.player_id:
            return rating
    return None


def pick_ratings(pick: models.DraftPick) -> PickRatings:
    rating = rating_for_pick(pick)
    position = normalize_position(pick.selected_position)

    if rating is None:
        return PickRatings(
            position=position,
            overall=DEFAULT_PLAYER_RATING,
            attack=DEFAULT_PLAYER_RATING,
            defence=DEFAULT_PLAYER_RATING,
            set_piece=DEFAULT_PLAYER_RATING,
            breakdown=DEFAULT_PLAYER_RATING,
            goal_kicking=DEFAULT_PLAYER_RATING,
        )

    return PickRatings(
        position=position,
        overall=rating.overall,
        attack=rating.attack,
        defence=rating.defense,
        set_piece=rating.set_piece,
        breakdown=average([rating.defense, rating.stamina]),
        goal_kicking=rating.kicking,
    )


def missing_positions(position_count: Counter[str]) -> list[str]:
    required = Counter(STARTING_XV_POSITIONS)
    missing: list[str] = []

    for position in STARTING_XV_POSITIONS:
        if position_count[position] < required[position]:
            missing.append(position)
            position_count[position] += 1

    return missing


def calculate_draft_session_rating(
    draft_session: models.DraftSession,
) -> dict[str, object]:
    picks = [pick_ratings(pick) for pick in draft_session.picks]
    position_count = Counter(pick.position for pick in picks)
    missing = missing_positions(position_count.copy())

    pack_picks = [pick for pick in picks if pick.position in PACK_POSITIONS]
    backline_picks = [pick for pick in picks if pick.position in BACKLINE_POSITIONS]
    spine_picks = [pick for pick in picks if pick.position in SPINE_POSITIONS]

    return {
        "overall_rating": average(pick.overall for pick in picks),
        "pack_rating": average(pick.overall for pick in pack_picks),
        "backline_rating": average(pick.overall for pick in backline_picks),
        "spine_rating": average(pick.overall for pick in spine_picks),
        "set_piece_rating": average(pick.set_piece for pick in pack_picks),
        "breakdown_rating": average(pick.breakdown for pick in pack_picks),
        "attack_rating": average(pick.attack for pick in picks),
        "defence_rating": average(pick.defence for pick in picks),
        "goal_kicking_rating": average(pick.goal_kicking for pick in picks),
        "missing_positions": missing,
        "position_count": dict(sorted(position_count.items())),
        "is_complete": (
            not missing and len(draft_session.picks) >= draft_session.max_picks
        ),
    }
