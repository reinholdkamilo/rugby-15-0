from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, Position, SpinPool, SquadAppearance
from .normaliser import normalise_country, normalise_key, normalise_position
from .schema_utils import ensure_spin_pool_schema

PROJECT_ROOT = BACKEND_DIR.parent
DICTIONARY_PATH = PROJECT_ROOT / "data" / "reference" / "player_positions.csv"
REPORT_PATH = BACKEND_DIR / "reports" / "player_position_dictionary_report.json"


def apply_dictionary(
    db: Session,
    dictionary_path: Path = DICTIONARY_PATH,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dictionary_file": str(dictionary_path),
        "rows_read": 0,
        "rows_skipped": 0,
        "players_matched": 0,
        "squad_appearances_updated": 0,
        "squad_appearances_unchanged": 0,
        "spin_pool_rows_updated": 0,
        "warnings": [],
        "updates": [],
    }

    if not dictionary_path.exists():
        report["warnings"].append(f"Dictionary file not found: {dictionary_path}")
        return report

    positions_by_code = {
        position.code: position
        for position in db.scalars(select(Position)).all()
    }
    tbc_position = positions_by_code.get("TBC")
    if tbc_position is None:
        report["warnings"].append("TBC position is not seeded; dictionary skipped.")
        return report

    players_by_country = build_player_lookup(db)
    with dictionary_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            report["rows_read"] += 1
            apply_dictionary_row(
                db=db,
                row=row,
                row_number=row_number,
                positions_by_code=positions_by_code,
                tbc_position=tbc_position,
                players_by_country=players_by_country,
                report=report,
            )

    db.commit()
    return report


def build_player_lookup(db: Session) -> dict[tuple[str, str], Player]:
    players = db.scalars(
        select(Player)
        .options(
            selectinload(Player.country),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.position),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.country),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.tournament),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.spin_pool_entries),
        ),
    ).all()

    lookup: dict[tuple[str, str], Player] = {}
    for player in players:
        if player.country is None:
            continue
        key = (normalise_key(player.display_name), player.country.name)
        lookup[key] = player
    return lookup


def apply_dictionary_row(
    db: Session,
    row: dict[str, str],
    row_number: int,
    positions_by_code: dict[str, Position],
    tbc_position: Position,
    players_by_country: dict[tuple[str, str], Player],
    report: dict[str, Any],
) -> None:
    player_name = row.get("player_name", "").strip()
    country = normalise_country(row.get("country", "").strip())
    primary_position_code = normalise_position(row.get("primary_position", "").strip())
    secondary_positions = normalise_secondary_positions(
        row.get("secondary_positions", ""),
    )

    if not player_name or not country or not primary_position_code:
        skip_row(report, row_number, "Missing player_name, country, or primary_position")
        return

    if primary_position_code == "TBC":
        skip_row(report, row_number, "Primary position cannot be TBC")
        return

    primary_position = positions_by_code.get(primary_position_code)
    if primary_position is None:
        skip_row(report, row_number, f"Unknown primary position: {primary_position_code}")
        return

    invalid_secondary_positions = [
        position_code
        for position_code in secondary_positions
        if position_code not in positions_by_code
    ]
    if invalid_secondary_positions:
        skip_row(
            report,
            row_number,
            "Unknown secondary position(s): "
            f"{', '.join(invalid_secondary_positions)}",
        )
        return

    player = players_by_country.get((normalise_key(player_name), country))
    if player is None:
        skip_row(report, row_number, f"No player match for {player_name}, {country}")
        return

    report["players_matched"] += 1
    eligible_positions = build_eligible_positions(
        primary_position_code,
        secondary_positions,
    )

    for appearance in sorted(
        player.squad_appearances,
        key=lambda value: value.tournament.year if value.tournament else 0,
    ):
        if appearance.country.name != country:
            continue
        if appearance.position_id != tbc_position.id:
            report["squad_appearances_unchanged"] += 1
            continue

        appearance.position = primary_position
        spin_pool_updates = update_spin_pool_rows(appearance, eligible_positions)
        report["squad_appearances_updated"] += 1
        report["spin_pool_rows_updated"] += spin_pool_updates
        report["updates"].append(
            {
                "player_name": player.display_name,
                "country": country,
                "year": appearance.tournament.year,
                "squad_appearance_id": appearance.id,
                "from_position": "TBC",
                "to_position": primary_position_code,
                "eligible_positions": eligible_positions,
                "source": row.get("source", "").strip(),
                "notes": row.get("notes", "").strip(),
            },
        )


def normalise_secondary_positions(raw_value: str) -> list[str]:
    positions: list[str] = []
    for raw_position in raw_value.replace("/", ",").replace(";", ",").split(","):
        raw_position = raw_position.strip()
        if not raw_position:
            continue
        position_code = normalise_position(raw_position)
        if position_code not in positions:
            positions.append(position_code)
    return positions


def build_eligible_positions(
    primary_position: str,
    secondary_positions: list[str],
) -> str:
    positions = [primary_position]
    for position in secondary_positions:
        if position not in positions:
            positions.append(position)
    return ",".join(positions)


def update_spin_pool_rows(
    appearance: SquadAppearance,
    eligible_positions: str,
) -> int:
    updated = 0
    for spin_pool in appearance.spin_pool_entries:
        if spin_pool.eligible_positions == eligible_positions:
            continue
        spin_pool.eligible_positions = eligible_positions
        updated += 1
    return updated


def skip_row(report: dict[str, Any], row_number: int, message: str) -> None:
    report["rows_skipped"] += 1
    report["warnings"].append(f"Row {row_number}: {message}")


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    ensure_spin_pool_schema()
    with SessionLocal() as db:
        report = apply_dictionary(db)

    write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Player position dictionary report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
