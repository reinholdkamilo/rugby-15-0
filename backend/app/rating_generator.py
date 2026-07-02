from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import models

GENERATED_SOURCE = "Generated Baseline v1"
MANUAL_SOURCE = "Manual Seed"

COUNTRY_BASELINES: dict[str, tuple[int, int]] = {
    "New Zealand": (84, 90),
    "South Africa": (84, 90),
    "Australia": (82, 88),
    "England": (82, 88),
    "France": (82, 88),
    "Ireland": (82, 88),
    "Wales": (80, 86),
    "Scotland": (80, 86),
    "Argentina": (80, 86),
    "Fiji": (77, 84),
    "Samoa": (77, 84),
    "Tonga": (77, 84),
    "Italy": (77, 84),
    "Japan": (77, 84),
}
DEFAULT_BASELINE = (74, 81)

ERA_ADJUSTMENTS = {
    1987: -1.0,
    1991: -0.5,
    1995: 0.0,
    1999: 0.5,
    2003: 0.8,
    2007: 1.0,
    2011: 1.2,
    2015: 1.4,
    2019: 1.6,
    2023: 1.8,
}

POSITION_TEMPLATES: dict[str, dict[str, float | str]] = {
    "LH": {
        "style": "Scrummaging prop",
        "set_piece": 5,
        "scrum": 8,
        "lineout": -5,
        "breakdown": 0,
        "carry": 2,
        "passing": -8,
        "kicking": -14,
        "goal_kicking": -18,
        "strike": -8,
        "defence": 2,
        "leadership": 0,
        "discipline": -1,
        "big_game": 0,
        "rugby_iq": 0,
    },
    "TH": {
        "style": "Scrummaging prop",
        "set_piece": 6,
        "scrum": 9,
        "lineout": -5,
        "breakdown": 0,
        "carry": 1,
        "passing": -9,
        "kicking": -14,
        "goal_kicking": -18,
        "strike": -8,
        "defence": 2,
        "leadership": 0,
        "discipline": -1,
        "big_game": 0,
        "rugby_iq": 0,
    },
    "HK": {
        "style": "Set-piece hooker",
        "set_piece": 7,
        "scrum": 4,
        "lineout": 7,
        "breakdown": 3,
        "carry": 1,
        "passing": -4,
        "kicking": -13,
        "goal_kicking": -18,
        "strike": -4,
        "defence": 3,
        "leadership": 1,
        "discipline": -1,
        "big_game": 0,
        "rugby_iq": 1,
    },
    "LK4": {
        "style": "Lineout lock",
        "set_piece": 6,
        "scrum": 3,
        "lineout": 9,
        "breakdown": 1,
        "carry": 3,
        "passing": -6,
        "kicking": -13,
        "goal_kicking": -18,
        "strike": -4,
        "defence": 3,
        "leadership": 1,
        "discipline": -1,
        "big_game": 1,
        "rugby_iq": 1,
    },
    "LK5": {
        "style": "Lineout lock",
        "set_piece": 6,
        "scrum": 3,
        "lineout": 9,
        "breakdown": 1,
        "carry": 3,
        "passing": -6,
        "kicking": -13,
        "goal_kicking": -18,
        "strike": -4,
        "defence": 3,
        "leadership": 1,
        "discipline": -1,
        "big_game": 1,
        "rugby_iq": 1,
    },
    "BSF": {
        "style": "Physical loose forward",
        "set_piece": 1,
        "scrum": 0,
        "lineout": 3,
        "breakdown": 7,
        "carry": 5,
        "passing": -3,
        "kicking": -11,
        "goal_kicking": -17,
        "strike": 0,
        "defence": 7,
        "leadership": 2,
        "discipline": 0,
        "big_game": 1,
        "rugby_iq": 3,
    },
    "OSF": {
        "style": "Breakdown flanker",
        "set_piece": 0,
        "scrum": 0,
        "lineout": 1,
        "breakdown": 9,
        "carry": 4,
        "passing": -2,
        "kicking": -11,
        "goal_kicking": -17,
        "strike": 1,
        "defence": 8,
        "leadership": 2,
        "discipline": 0,
        "big_game": 1,
        "rugby_iq": 4,
    },
    "N8": {
        "style": "Ball-carrying number eight",
        "set_piece": 1,
        "scrum": 1,
        "lineout": 2,
        "breakdown": 6,
        "carry": 8,
        "passing": -1,
        "kicking": -10,
        "goal_kicking": -17,
        "strike": 2,
        "defence": 6,
        "leadership": 2,
        "discipline": 0,
        "big_game": 1,
        "rugby_iq": 3,
    },
    "SH": {
        "style": "Tempo scrum-half",
        "set_piece": -8,
        "scrum": -12,
        "lineout": -12,
        "breakdown": 1,
        "carry": 0,
        "passing": 9,
        "kicking": 5,
        "goal_kicking": -8,
        "strike": 2,
        "defence": 3,
        "leadership": 2,
        "discipline": 1,
        "big_game": 1,
        "rugby_iq": 8,
    },
    "FH": {
        "style": "Playmaking fly-half",
        "set_piece": -9,
        "scrum": -13,
        "lineout": -13,
        "breakdown": -2,
        "carry": 0,
        "passing": 9,
        "kicking": 9,
        "goal_kicking": 6,
        "strike": 2,
        "defence": 0,
        "leadership": 4,
        "discipline": 2,
        "big_game": 3,
        "rugby_iq": 9,
    },
    "LW": {
        "style": "Finishing wing",
        "set_piece": -10,
        "scrum": -14,
        "lineout": -14,
        "breakdown": -2,
        "carry": 3,
        "passing": 0,
        "kicking": 2,
        "goal_kicking": -10,
        "strike": 10,
        "defence": 2,
        "leadership": -1,
        "discipline": 1,
        "big_game": 1,
        "rugby_iq": 2,
    },
    "RW": {
        "style": "Finishing wing",
        "set_piece": -10,
        "scrum": -14,
        "lineout": -14,
        "breakdown": -2,
        "carry": 3,
        "passing": 0,
        "kicking": 2,
        "goal_kicking": -10,
        "strike": 10,
        "defence": 2,
        "leadership": -1,
        "discipline": 1,
        "big_game": 1,
        "rugby_iq": 2,
    },
    "IC": {
        "style": "Carrying centre",
        "set_piece": -8,
        "scrum": -12,
        "lineout": -12,
        "breakdown": 1,
        "carry": 7,
        "passing": 5,
        "kicking": 0,
        "goal_kicking": -8,
        "strike": 5,
        "defence": 6,
        "leadership": 1,
        "discipline": 1,
        "big_game": 1,
        "rugby_iq": 4,
    },
    "OC": {
        "style": "Defensive centre",
        "set_piece": -8,
        "scrum": -12,
        "lineout": -12,
        "breakdown": 1,
        "carry": 5,
        "passing": 4,
        "kicking": 0,
        "goal_kicking": -9,
        "strike": 7,
        "defence": 7,
        "leadership": 1,
        "discipline": 1,
        "big_game": 1,
        "rugby_iq": 4,
    },
    "FB": {
        "style": "Counter-attacking fullback",
        "set_piece": -10,
        "scrum": -14,
        "lineout": -14,
        "breakdown": -2,
        "carry": 3,
        "passing": 3,
        "kicking": 7,
        "goal_kicking": -3,
        "strike": 8,
        "defence": 6,
        "leadership": 1,
        "discipline": 1,
        "big_game": 1,
        "rugby_iq": 5,
    },
    "UTIL": {
        "style": "Utility back",
        "set_piece": -6,
        "scrum": -9,
        "lineout": -8,
        "breakdown": 1,
        "carry": 3,
        "passing": 4,
        "kicking": 3,
        "goal_kicking": -5,
        "strike": 5,
        "defence": 4,
        "leadership": 0,
        "discipline": 1,
        "big_game": 0,
        "rugby_iq": 4,
    },
    "TBC": {
        "style": "Utility / Unknown",
        "set_piece": 0,
        "scrum": 0,
        "lineout": 0,
        "breakdown": 0,
        "carry": 0,
        "passing": 0,
        "kicking": 0,
        "goal_kicking": -6,
        "strike": 0,
        "defence": 0,
        "leadership": 0,
        "discipline": 0,
        "big_game": 0,
        "rugby_iq": 0,
    },
}

RATING_FIELDS = [
    "overall",
    "set_piece",
    "scrum",
    "lineout",
    "breakdown",
    "carry",
    "passing",
    "kicking",
    "goal_kicking",
    "strike",
    "defence",
    "leadership",
    "discipline",
    "big_game",
    "rugby_iq",
]


def stable_int(*parts: object) -> int:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def stable_variation(
    player_id: int,
    tournament_id: int,
    salt: str,
    spread: int,
) -> int:
    return stable_int(player_id, tournament_id, salt) % (spread * 2 + 1) - spread


def clamp(value: float, minimum: float = 40.0, maximum: float = 99.0) -> float:
    return round(max(minimum, min(maximum, value)), 1)


def base_for_country(country_name: str) -> tuple[int, int]:
    return COUNTRY_BASELINES.get(country_name, DEFAULT_BASELINE)


def generated_overall(
    appearance: models.SquadAppearance,
    anchor_adjustments: dict[str, float],
) -> float:
    low, high = base_for_country(appearance.country.name)
    span = high - low
    bucket = stable_int(appearance.player_id, appearance.tournament_id, "overall")
    base = low + (bucket % (span * 10 + 1)) / 10
    era_adjustment = ERA_ADJUSTMENTS.get(appearance.tournament.year, 0.0)
    position_adjustment = 0.4 if position_code(appearance) != "TBC" else -1.0
    captain_adjustment = 1.2 if appearance.is_captain else 0.0
    anchor_adjustment = anchor_adjustments.get(appearance.country.name, 0.0)
    return clamp(
        base
        + era_adjustment
        + position_adjustment
        + captain_adjustment
        + anchor_adjustment,
        74,
        93,
    )


def position_code(appearance: models.SquadAppearance) -> str:
    if appearance.position is None:
        return "TBC"
    code = appearance.position.code
    return code if code in POSITION_TEMPLATES else "TBC"


def build_rating_values(
    appearance: models.SquadAppearance,
    anchor_adjustments: dict[str, float],
) -> dict[str, Any]:
    code = position_code(appearance)
    template = POSITION_TEMPLATES[code]
    overall = generated_overall(appearance, anchor_adjustments)
    values: dict[str, Any] = {"overall": overall}

    for field in RATING_FIELDS:
        if field == "overall":
            continue
        offset = float(template[field])
        variation = stable_variation(
            appearance.player_id,
            appearance.tournament_id,
            field,
            2,
        )
        values[field] = clamp(overall + offset + variation)

    values["attack"] = round(
        (values["carry"] + values["passing"] + values["strike"]) / 3,
        1,
    )
    values["defense"] = values["defence"]
    values["pace"] = values["strike"]
    values["stamina"] = values["discipline"]
    values["best_position"] = code
    values["style"] = str(template["style"])
    values["rating_status"] = "generated"
    values["source"] = GENERATED_SOURCE
    values["notes"] = (
        "Deterministic baseline generated from country tier, tournament era, "
        "manual rating anchors, position template, captain flag, and stable "
        "player/tournament variation."
    )
    return values


def build_anchor_adjustments(db: Session) -> dict[str, float]:
    rows = db.execute(
        select(
            models.Country.name,
            func.avg(models.Rating.overall),
        )
        .select_from(models.Rating)
        .join(models.Player, models.Rating.player_id == models.Player.id)
        .join(models.Country, models.Player.country_id == models.Country.id)
        .where(models.Rating.source != GENERATED_SOURCE)
        .group_by(models.Country.name),
    ).all()
    adjustments: dict[str, float] = {}
    for country_name, average_rating in rows:
        if average_rating is None:
            continue
        adjustments[country_name] = clamp(
            (float(average_rating) - 90.0) * 0.15,
            -1.0,
            1.0,
        )
    return adjustments


def is_generated_rating(rating: models.Rating) -> bool:
    return rating.source == GENERATED_SOURCE or rating.rating_status == "generated"


def existing_rating_for_appearance(
    ratings_by_appearance: dict[int, models.Rating],
    ratings_by_player_tournament: dict[tuple[int, int], models.Rating],
    appearance: models.SquadAppearance,
) -> Optional[models.Rating]:
    if appearance.id in ratings_by_appearance:
        return ratings_by_appearance[appearance.id]
    return ratings_by_player_tournament.get(
        (appearance.player_id, appearance.tournament_id),
    )


def apply_values(
    rating: models.Rating,
    appearance: models.SquadAppearance,
    position: Optional[models.Position],
    values: dict[str, Any],
) -> None:
    for field in RATING_FIELDS:
        setattr(rating, field, values[field])
    rating.attack = values["attack"]
    rating.defense = values["defense"]
    rating.pace = values["pace"]
    rating.stamina = values["stamina"]
    rating.player = appearance.player
    rating.tournament = appearance.tournament
    rating.squad_appearance = appearance
    rating.position = position
    rating.best_position = values["best_position"]
    rating.style = values["style"]
    rating.rating_status = values["rating_status"]
    rating.source = values["source"]
    rating.notes = values["notes"]


def rating_band(overall: float) -> str:
    if overall >= 97:
        return "97-99 all-time great / World XV calibre"
    if overall >= 94:
        return "94-96 elite tournament-defining player"
    if overall >= 90:
        return "90-93 world-class international"
    if overall >= 85:
        return "85-89 strong test player"
    if overall >= 80:
        return "80-84 regular World Cup squad player"
    return "74-79 lower-tier/fringe squad player"


def empty_report(overwrite_generated_only: bool) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": GENERATED_SOURCE,
        "overwrite_generated_only": overwrite_generated_only,
        "ratings_created": 0,
        "ratings_updated": 0,
        "manual_ratings_preserved": 0,
        "generated_rating_count": 0,
        "ratings_by_band": {},
        "ratings_by_country": {},
        "ratings_by_year": {},
        "unrated_squad_appearances_remaining": 0,
    }


def generate_baseline_ratings(
    db: Session,
    overwrite_generated_only: bool = False,
) -> dict[str, Any]:
    report = empty_report(overwrite_generated_only)
    anchor_adjustments = build_anchor_adjustments(db)
    positions_by_code = {
        position.code: position
        for position in db.scalars(select(models.Position)).all()
    }
    ratings = db.scalars(select(models.Rating)).all()
    for rating in ratings:
        if rating.source == "seed_manual":
            rating.source = MANUAL_SOURCE

    ratings_by_appearance = {
        rating.squad_appearance_id: rating
        for rating in ratings
        if rating.squad_appearance_id is not None
    }
    ratings_by_player_tournament = {
        (rating.player_id, rating.tournament_id): rating
        for rating in ratings
        if rating.tournament_id is not None
    }

    appearances = db.scalars(
        select(models.SquadAppearance)
        .options(
            selectinload(models.SquadAppearance.player),
            selectinload(models.SquadAppearance.country),
            selectinload(models.SquadAppearance.tournament),
            selectinload(models.SquadAppearance.position),
        )
        .order_by(models.SquadAppearance.id),
    ).all()

    for appearance in appearances:
        existing = existing_rating_for_appearance(
            ratings_by_appearance,
            ratings_by_player_tournament,
            appearance,
        )
        if existing is not None and not is_generated_rating(existing):
            report["manual_ratings_preserved"] += 1
            continue
        if existing is not None and not overwrite_generated_only:
            continue

        values = build_rating_values(appearance, anchor_adjustments)
        rating = existing
        if rating is None:
            rating = models.Rating()
            db.add(rating)
            report["ratings_created"] += 1
        else:
            report["ratings_updated"] += 1

        apply_values(
            rating=rating,
            appearance=appearance,
            position=positions_by_code.get(values["best_position"]),
            values=values,
        )
        ratings_by_appearance[appearance.id] = rating
        ratings_by_player_tournament[
            (appearance.player_id, appearance.tournament_id)
        ] = rating

    db.commit()
    return populate_rating_report(db, report)


def populate_rating_report(db: Session, report: dict[str, Any]) -> dict[str, Any]:
    generated_ratings = db.scalars(
        select(models.Rating).where(models.Rating.source == GENERATED_SOURCE),
    ).all()
    report["generated_rating_count"] = len(generated_ratings)

    ratings_by_band: dict[str, int] = {}
    for rating in db.scalars(select(models.Rating)).all():
        band = rating_band(float(rating.overall))
        ratings_by_band[band] = ratings_by_band.get(band, 0) + 1
    report["ratings_by_band"] = dict(sorted(ratings_by_band.items()))

    country_rows = db.execute(
        select(models.Country.name, func.count(models.Rating.id))
        .select_from(models.Rating)
        .join(models.SquadAppearance, models.Rating.squad_appearance_id == models.SquadAppearance.id)
        .join(models.Country, models.SquadAppearance.country_id == models.Country.id)
        .group_by(models.Country.name)
        .order_by(models.Country.name),
    ).all()
    report["ratings_by_country"] = {
        country: count
        for country, count in country_rows
    }

    year_rows = db.execute(
        select(models.Tournament.year, func.count(models.Rating.id))
        .select_from(models.Rating)
        .join(models.SquadAppearance, models.Rating.squad_appearance_id == models.SquadAppearance.id)
        .join(models.Tournament, models.SquadAppearance.tournament_id == models.Tournament.id)
        .group_by(models.Tournament.year)
        .order_by(models.Tournament.year),
    ).all()
    report["ratings_by_year"] = {
        str(year): count
        for year, count in year_rows
    }
    report["unrated_squad_appearances_remaining"] = count_unrated_appearances(db)
    return report


def count_unrated_appearances(db: Session) -> int:
    rows = db.execute(
        select(models.SquadAppearance.id)
        .outerjoin(
            models.Rating,
            models.Rating.squad_appearance_id == models.SquadAppearance.id,
        )
        .where(models.Rating.id.is_(None)),
    ).all()
    missing = 0
    for (appearance_id,) in rows:
        appearance = db.get(models.SquadAppearance, appearance_id)
        if appearance is None:
            continue
        rating = db.scalar(
            select(models.Rating).where(
                models.Rating.player_id == appearance.player_id,
                models.Rating.tournament_id == appearance.tournament_id,
            ),
        )
        if rating is None:
            missing += 1
    return missing


def build_rating_summary(db: Session) -> dict[str, Any]:
    ratings = db.scalars(select(models.Rating)).all()
    bands: dict[str, int] = {}
    manual = 0
    generated = 0
    for rating in ratings:
        if rating.source == GENERATED_SOURCE:
            generated += 1
        else:
            manual += 1
        band = rating_band(float(rating.overall))
        bands[band] = bands.get(band, 0) + 1
    return {
        "total_ratings": len(ratings),
        "manual_ratings": manual,
        "generated_ratings": generated,
        "unrated_squad_appearances": count_unrated_appearances(db),
        "rating_bands": dict(sorted(bands.items())),
    }
