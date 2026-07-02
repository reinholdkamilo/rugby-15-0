from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, Position, SpinPool, SquadAppearance, Tournament
from .schema_utils import ensure_spin_pool_schema

REPORT_PATH = BACKEND_DIR / "reports" / "position_audit.json"
TEMPLATE_PATH = BACKEND_DIR / "reports" / "position_corrections_template.csv"
CORRECTION_COLUMNS = [
    "player_name",
    "country",
    "year",
    "current_position",
    "suggested_position",
    "notes",
]


def build_position_audit(db: Session) -> dict[str, Any]:
    tbc_rows = find_tbc_squad_appearances(db)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_tbc_positions": len(tbc_rows),
        "tbc_positions_by_year": count_tbc_by_year(db),
        "tbc_positions_by_country": count_tbc_by_country(db),
        "top_100_players_with_tbc_positions": tbc_rows[:100],
        "positions_currently_used_in_squad_appearances": (
            positions_used_in_squad_appearances(db)
        ),
        "invalid_position_codes": find_invalid_position_codes(db),
    }
    return report


def find_tbc_squad_appearances(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            SquadAppearance.id,
            Player.display_name,
            Country.name,
            Tournament.year,
            Position.code,
        )
        .select_from(SquadAppearance)
        .join(Player, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .join(Position, SquadAppearance.position_id == Position.id)
        .where(Position.code == "TBC")
        .order_by(Tournament.year, Country.name, Player.display_name),
    ).all()

    return [
        {
            "squad_appearance_id": squad_appearance_id,
            "player_name": player_name,
            "country": country,
            "year": year,
            "current_position": position_code,
        }
        for squad_appearance_id, player_name, country, year, position_code in rows
    ]


def count_tbc_by_year(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Tournament.year, func.count(SquadAppearance.id))
        .select_from(SquadAppearance)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .join(Position, SquadAppearance.position_id == Position.id)
        .where(Position.code == "TBC")
        .group_by(Tournament.year)
        .order_by(Tournament.year),
    ).all()
    return [{"year": year, "count": count} for year, count in rows]


def count_tbc_by_country(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Country.name, func.count(SquadAppearance.id))
        .select_from(SquadAppearance)
        .join(Country, SquadAppearance.country_id == Country.id)
        .join(Position, SquadAppearance.position_id == Position.id)
        .where(Position.code == "TBC")
        .group_by(Country.name)
        .order_by(func.count(SquadAppearance.id).desc(), Country.name),
    ).all()
    return [{"country": country, "count": count} for country, count in rows]


def positions_used_in_squad_appearances(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Position.code, Position.name, func.count(SquadAppearance.id))
        .select_from(SquadAppearance)
        .join(Position, SquadAppearance.position_id == Position.id)
        .group_by(Position.code, Position.name)
        .order_by(Position.sort_order),
    ).all()
    return [
        {
            "position": code,
            "name": name,
            "count": count,
        }
        for code, name, count in rows
    ]


def find_invalid_position_codes(db: Session) -> dict[str, list[dict[str, Any]]]:
    valid_codes = set(db.scalars(select(Position.code)).all())
    invalid_squad_appearances = find_invalid_squad_appearance_positions(db, valid_codes)
    invalid_spin_pool_positions = find_invalid_spin_pool_positions(db, valid_codes)
    return {
        "squad_appearances": invalid_squad_appearances,
        "spin_pool_eligible_positions": invalid_spin_pool_positions,
    }


def find_invalid_squad_appearance_positions(
    db: Session,
    valid_codes: set[str],
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            SquadAppearance.id,
            Player.display_name,
            Country.name,
            Tournament.year,
            Position.code,
        )
        .select_from(SquadAppearance)
        .join(Player, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .outerjoin(Position, SquadAppearance.position_id == Position.id)
        .order_by(Tournament.year, Country.name, Player.display_name),
    ).all()

    invalid: list[dict[str, Any]] = []
    for squad_appearance_id, player_name, country, year, code in rows:
        if code in valid_codes:
            continue
        invalid.append(
            {
                "squad_appearance_id": squad_appearance_id,
                "player_name": player_name,
                "country": country,
                "year": year,
                "position": code,
            },
        )
    return invalid


def find_invalid_spin_pool_positions(
    db: Session,
    valid_codes: set[str],
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            SpinPool.id,
            SpinPool.eligible_positions,
            Player.display_name,
            Country.name,
            Tournament.year,
        )
        .select_from(SpinPool)
        .join(SquadAppearance, SpinPool.squad_appearance_id == SquadAppearance.id)
        .join(Player, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .order_by(Tournament.year, Country.name, Player.display_name),
    ).all()

    invalid: list[dict[str, Any]] = []
    for spin_pool_id, raw_positions, player_name, country, year in rows:
        for code in parse_position_codes(raw_positions):
            if code in valid_codes:
                continue
            invalid.append(
                {
                    "spin_pool_id": spin_pool_id,
                    "player_name": player_name,
                    "country": country,
                    "year": year,
                    "position": code,
                },
            )
    return invalid


def parse_position_codes(raw_positions: Optional[str]) -> list[str]:
    if not raw_positions:
        return []
    return [
        code.strip().upper()
        for code in raw_positions.split(",")
        if code.strip()
    ]


def write_json_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def write_correction_template(
    tbc_rows: list[dict[str, Any]],
    path: Path = TEMPLATE_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CORRECTION_COLUMNS)
        writer.writeheader()
        for row in tbc_rows:
            writer.writerow(
                {
                    "player_name": row["player_name"],
                    "country": row["country"],
                    "year": row["year"],
                    "current_position": row["current_position"],
                    "suggested_position": "",
                    "notes": "",
                },
            )


def main() -> None:
    ensure_spin_pool_schema()
    with SessionLocal() as db:
        report = build_position_audit(db)

    write_json_report(report)
    write_correction_template(report["top_100_players_with_tbc_positions"])
    print(json.dumps(report, indent=2))
    print(f"Position audit report written to {REPORT_PATH}")
    print(f"Correction template written to {TEMPLATE_PATH}")


if __name__ == "__main__":
    main()
