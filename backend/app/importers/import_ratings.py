from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, Position, Rating, SquadAppearance, Tournament
from .normaliser import normalise_country, normalise_key, normalise_position
from .schema_utils import ensure_database_schema

PROJECT_ROOT = BACKEND_DIR.parent
RATING_SEED_PATH = PROJECT_ROOT / "data" / "ratings" / "rating_seed.csv"
REPORT_PATH = BACKEND_DIR / "reports" / "rating_import_report.json"
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


def import_ratings(db: Session, path: Path = RATING_SEED_PATH) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file": str(path),
        "rows_read": 0,
        "rows_skipped": 0,
        "ratings_created": 0,
        "ratings_updated": 0,
        "warnings": [],
    }
    if not path.exists():
        report["warnings"].append(f"Rating seed file not found: {path}")
        return report

    players = build_player_lookup(db)
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            report["rows_read"] += 1
            import_rating_row(db, row, row_number, players, report)

    db.commit()
    return report


def build_player_lookup(db: Session) -> dict[tuple[str, str], Player]:
    lookup: dict[tuple[str, str], Player] = {}
    for player in db.scalars(select(Player)).all():
        if player.country is None:
            continue
        lookup[(normalise_key(player.display_name), player.country.name)] = player
    return lookup


def import_rating_row(
    db: Session,
    row: dict[str, str],
    row_number: int,
    players: dict[tuple[str, str], Player],
    report: dict[str, Any],
) -> None:
    player_name = row.get("player_name", "").strip()
    country = normalise_country(row.get("country", "").strip())
    if not player_name or not country:
        skip(report, row_number, "Missing player_name or country")
        return

    player = players.get((normalise_key(player_name), country))
    if player is None:
        skip(report, row_number, f"No player match for {player_name}, {country}")
        return

    year = parse_optional_int(row.get("year", "").strip())
    tournament: Optional[Tournament] = None
    squad_appearance: Optional[SquadAppearance] = None
    if year is not None:
        tournament = db.scalar(select(Tournament).where(Tournament.year == year))
        if tournament is None:
            skip(report, row_number, f"Unknown tournament year: {year}")
            return
        squad_appearance = db.scalar(
            select(SquadAppearance).where(
                SquadAppearance.player_id == player.id,
                SquadAppearance.country_id == player.country_id,
                SquadAppearance.tournament_id == tournament.id,
            ),
        )
        if squad_appearance is None:
            skip(
                report,
                row_number,
                f"No squad appearance for {player.display_name}, {country}, {year}",
            )
            return

    best_position_code = normalise_position(row.get("best_position", "").strip())
    best_position = db.scalar(
        select(Position).where(Position.code == best_position_code),
    )
    if best_position is None:
        skip(report, row_number, f"Unknown best_position: {best_position_code}")
        return

    rating = find_existing_rating(db, player, squad_appearance, tournament, best_position)
    created = rating is None
    if rating is None:
        rating = Rating(player=player)
        db.add(rating)

    apply_rating_values(
        rating=rating,
        row=row,
        tournament=tournament,
        squad_appearance=squad_appearance,
        best_position=best_position,
    )
    if created:
        report["ratings_created"] += 1
    else:
        report["ratings_updated"] += 1


def find_existing_rating(
    db: Session,
    player: Player,
    squad_appearance: Optional[SquadAppearance],
    tournament: Optional[Tournament],
    best_position: Position,
) -> Optional[Rating]:
    query = select(Rating).where(
        Rating.player_id == player.id,
        Rating.position_id == best_position.id,
    )
    if squad_appearance is None:
        query = query.where(Rating.squad_appearance_id.is_(None))
    else:
        query = query.where(Rating.squad_appearance_id == squad_appearance.id)
    if tournament is None:
        query = query.where(Rating.tournament_id.is_(None))
    else:
        query = query.where(Rating.tournament_id == tournament.id)
    return db.scalar(query)


def apply_rating_values(
    rating: Rating,
    row: dict[str, str],
    tournament: Optional[Tournament],
    squad_appearance: Optional[SquadAppearance],
    best_position: Position,
) -> None:
    values = {
        field: parse_rating(row.get(field, ""))
        for field in RATING_FIELDS
    }
    for field, value in values.items():
        setattr(rating, field, value)

    rating.attack = mean(
        values["carry"],
        values["passing"],
        values["strike"],
    )
    rating.defense = values["defence"]
    rating.pace = values["strike"]
    rating.stamina = values["discipline"]
    rating.tournament = tournament
    rating.squad_appearance = squad_appearance
    rating.position = best_position
    rating.best_position = best_position.code
    rating.style = row.get("style", "").strip() or None
    rating.rating_status = "seeded"
    source = row.get("source", "").strip()
    rating.source = "Manual Seed" if source == "seed_manual" else source or "Manual Seed"
    rating.notes = row.get("notes", "").strip() or None


def parse_rating(value: str) -> float:
    value = value.strip()
    if not value:
        return 80.0
    return float(value)


def parse_optional_int(value: str) -> Optional[int]:
    return int(value) if value else None


def mean(*values: float) -> float:
    return round(sum(values) / len(values), 2)


def skip(report: dict[str, Any], row_number: int, message: str) -> None:
    report["rows_skipped"] += 1
    report["warnings"].append(f"Row {row_number}: {message}")


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    ensure_database_schema()
    with SessionLocal() as db:
        report = import_ratings(db)
    write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Rating import report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
