from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from app.database import Base, SessionLocal, engine
    from app.models import (
        Country,
        Player,
        Position,
        SpinPool,
        SquadAppearance,
        Tournament,
    )
    from app.seed import seed_countries, seed_positions, seed_tournaments
else:
    from .database import Base, SessionLocal, engine
    from .models import (
        Country,
        Player,
        Position,
        SpinPool,
        SquadAppearance,
        Tournament,
    )
    from .seed import seed_countries, seed_positions, seed_tournaments


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQUADS_DIR = PROJECT_ROOT / "data" / "squads"

POSITION_ALIASES = {
    "LOCK": "LK4",
    "LK": "LK4",
}


@dataclass
class ImportSummary:
    files: int = 0
    rows: int = 0
    players_created: int = 0
    players_updated: int = 0
    squad_appearances_created: int = 0
    squad_appearances_updated: int = 0
    spin_pool_created: int = 0
    spin_pool_existing: int = 0
    skipped_rows: int = 0


def normalize_code(value: str) -> str:
    code = value.strip().upper()
    return POSITION_ALIASES.get(code, code)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def split_name(player_name: str) -> tuple[Optional[str], Optional[str]]:
    parts = player_name.strip().split()
    if len(parts) <= 1:
        return None, None
    return parts[0], " ".join(parts[1:])


def build_notes(secondary_positions: list[str], source_url: str) -> Optional[str]:
    notes: list[str] = []
    if secondary_positions:
        notes.append(f"Secondary positions: {', '.join(secondary_positions)}")
    if source_url:
        notes.append(f"Source: {source_url}")
    return "; ".join(notes) if notes else None


def csv_files() -> list[Path]:
    return sorted(SQUADS_DIR.glob("*.csv"))


def get_country(db: Session, country_name: str) -> Optional[Country]:
    return db.scalar(select(Country).where(Country.name == country_name.strip()))


def get_tournament(db: Session, year: int) -> Optional[Tournament]:
    return db.scalar(select(Tournament).where(Tournament.year == year))


def get_position(db: Session, position_code: str) -> Optional[Position]:
    return db.scalar(
        select(Position).where(Position.code == normalize_code(position_code)),
    )


def get_or_create_player(
    db: Session,
    player_name: str,
    country: Country,
    position: Optional[Position],
    summary: ImportSummary,
) -> Player:
    player = db.scalar(
        select(Player).where(
            Player.display_name == player_name,
            Player.country_id == country.id,
        ),
    )

    first_name, last_name = split_name(player_name)
    if player is None:
        player = Player(
            first_name=first_name,
            last_name=last_name,
            display_name=player_name,
            country=country,
            primary_position=position,
        )
        db.add(player)
        db.flush()
        summary.players_created += 1
    else:
        player.first_name = first_name
        player.last_name = last_name
        player.primary_position = position
        summary.players_updated += 1

    return player


def ensure_spin_pool(
    db: Session,
    country: Country,
    tournament: Tournament,
    summary: ImportSummary,
) -> None:
    spin_pool = db.scalar(
        select(SpinPool).where(
            SpinPool.country_id == country.id,
            SpinPool.tournament_id == tournament.id,
        ),
    )

    if spin_pool is None:
        db.add(SpinPool(country=country, tournament=tournament))
        summary.spin_pool_created += 1
    else:
        spin_pool.is_active = True
        summary.spin_pool_existing += 1


def upsert_squad_appearance(
    db: Session,
    player: Player,
    country: Country,
    tournament: Tournament,
    position: Optional[Position],
    captain: bool,
    notes: Optional[str],
    summary: ImportSummary,
) -> None:
    squad_appearance = db.scalar(
        select(SquadAppearance).where(
            SquadAppearance.player_id == player.id,
            SquadAppearance.country_id == country.id,
            SquadAppearance.tournament_id == tournament.id,
        ),
    )

    if squad_appearance is None:
        db.add(
            SquadAppearance(
                player=player,
                country=country,
                tournament=tournament,
                position=position,
                is_captain=captain,
                notes=notes,
            ),
        )
        summary.squad_appearances_created += 1
    else:
        squad_appearance.position = position
        squad_appearance.is_captain = captain
        squad_appearance.notes = notes
        summary.squad_appearances_updated += 1


def secondary_position_codes(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    return [normalize_code(value) for value in raw_value.split("/") if value.strip()]


def import_row(db: Session, row: dict[str, str], summary: ImportSummary) -> None:
    summary.rows += 1

    year = int(row["year"])
    country = get_country(db, row["country"])
    tournament = get_tournament(db, year)
    position = get_position(db, row["position"])

    if country is None or tournament is None or position is None:
        summary.skipped_rows += 1
        missing = [
            label
            for label, value in (
                ("country", country),
                ("tournament", tournament),
                ("position", position),
            )
            if value is None
        ]
        print(f"Skipping row {summary.rows}: missing {', '.join(missing)}")
        return

    player_name = row["player_name"].strip()
    secondary_positions = secondary_position_codes(row.get("secondary_positions", ""))
    source_url = row.get("source_url", "").strip()
    notes = build_notes(secondary_positions, source_url)
    captain = parse_bool(row.get("captain", ""))

    player = get_or_create_player(db, player_name, country, position, summary)
    upsert_squad_appearance(
        db=db,
        player=player,
        country=country,
        tournament=tournament,
        position=position,
        captain=captain,
        notes=notes,
        summary=summary,
    )
    ensure_spin_pool(db, country, tournament, summary)


def import_file(db: Session, path: Path, summary: ImportSummary) -> None:
    summary.files += 1
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            import_row(db, row, summary)


def import_squads(paths: Iterable[Path] | None = None) -> ImportSummary:
    summary = ImportSummary()
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        countries_by_code = seed_countries(db)
        seed_positions(db)
        seed_tournaments(db, countries_by_code)
        db.flush()

        for path in paths or csv_files():
            import_file(db, path, summary)

        db.commit()

    return summary


def print_summary(summary: ImportSummary) -> None:
    print("Squad import complete.")
    print(f"Files processed: {summary.files}")
    print(f"Rows read: {summary.rows}")
    print(f"Players created: {summary.players_created}")
    print(f"Players updated: {summary.players_updated}")
    print(f"Squad appearances created: {summary.squad_appearances_created}")
    print(f"Squad appearances updated: {summary.squad_appearances_updated}")
    print(f"Spin pool created: {summary.spin_pool_created}")
    print(f"Spin pool existing: {summary.spin_pool_existing}")
    print(f"Rows skipped: {summary.skipped_rows}")


if __name__ == "__main__":
    print_summary(import_squads())
