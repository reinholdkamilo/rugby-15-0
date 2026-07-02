from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, Position, SpinPool, SquadAppearance, Tournament
from .normaliser import normalise_country, normalise_position
from .schema_utils import ensure_spin_pool_schema

CORRECTIONS_PATH = BACKEND_DIR / "reports" / "position_corrections.csv"


def apply_corrections(
    db: Session,
    path: Path = CORRECTIONS_PATH,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "file": str(path),
        "rows_read": 0,
        "rows_skipped": 0,
        "rows_updated": 0,
        "rows_unchanged": 0,
        "warnings": [],
    }

    if not path.exists():
        summary["warnings"].append(
            "No correction file found. Create reports/position_corrections.csv "
            "from reports/position_corrections_template.csv.",
        )
        return summary

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            summary["rows_read"] += 1
            apply_correction_row(db, row, row_number, summary)

    db.commit()
    return summary


def apply_correction_row(
    db: Session,
    row: dict[str, str],
    row_number: int,
    summary: dict[str, Any],
) -> None:
    player_name = row.get("player_name", "").strip()
    country_name = normalise_country(row.get("country", "").strip())
    raw_year = row.get("year", "").strip()
    current_position = row.get("current_position", "").strip().upper()
    suggested_position = normalise_position(row.get("suggested_position", "").strip())

    if not player_name or not country_name or not raw_year or not suggested_position:
        skip_row(summary, row_number, "Missing required correction value")
        return

    try:
        year = int(raw_year)
    except ValueError:
        skip_row(summary, row_number, f"Invalid year: {raw_year}")
        return

    position = db.scalar(select(Position).where(Position.code == suggested_position))
    if position is None:
        skip_row(summary, row_number, f"Unknown suggested position: {suggested_position}")
        return

    squad_appearance = find_squad_appearance(db, player_name, country_name, year)
    if squad_appearance is None:
        skip_row(
            summary,
            row_number,
            f"No squad appearance found for {player_name}, {country_name}, {year}",
        )
        return

    existing_position = (
        squad_appearance.position.code
        if squad_appearance.position is not None
        else ""
    )
    if current_position and current_position != existing_position:
        skip_row(
            summary,
            row_number,
            "Current position mismatch for "
            f"{player_name}, {country_name}, {year}: "
            f"expected {current_position}, found {existing_position}",
        )
        return

    eligible_positions = suggested_position
    changed = False
    if squad_appearance.position_id != position.id:
        squad_appearance.position = position
        changed = True

    spin_pool = db.scalar(
        select(SpinPool).where(
            SpinPool.squad_appearance_id == squad_appearance.id,
        ),
    )
    if spin_pool is not None and spin_pool.eligible_positions != eligible_positions:
        spin_pool.eligible_positions = eligible_positions
        changed = True

    if changed:
        summary["rows_updated"] += 1
    else:
        summary["rows_unchanged"] += 1


def find_squad_appearance(
    db: Session,
    player_name: str,
    country_name: str,
    year: int,
) -> Optional[SquadAppearance]:
    return db.scalar(
        select(SquadAppearance)
        .join(Player, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .where(
            Player.display_name == player_name,
            Country.name == country_name,
            Tournament.year == year,
        ),
    )


def skip_row(summary: dict[str, Any], row_number: int, message: str) -> None:
    summary["rows_skipped"] += 1
    summary["warnings"].append(f"Row {row_number}: {message}")


def main() -> None:
    ensure_spin_pool_schema()
    with SessionLocal() as db:
        summary = apply_corrections(db)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
