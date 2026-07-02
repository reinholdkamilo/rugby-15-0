from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, Position, SpinPool, SquadAppearance, Tournament

REPORT_PATH = BACKEND_DIR / "reports" / "data_quality_audit.json"


def build_audit_report(db: Session) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": build_totals(db),
        "duplicate_player_name_country_combinations": (
            find_duplicate_player_name_country_combinations(db)
        ),
        "players_appearing_for_multiple_countries": (
            find_players_appearing_for_multiple_countries(db)
        ),
        "squad_appearances_without_spin_pool_rows": (
            find_squad_appearances_without_spin_pool_rows(db)
        ),
        "spin_pool_rows_without_squad_appearances": (
            find_spin_pool_rows_without_squad_appearances(db)
        ),
        "tbc_positions_by_year": build_tbc_positions_by_year(db),
        "player_counts_by_year_and_country": build_player_counts_by_year_and_country(db),
    }
    report["summary"] = build_summary(report)
    return report


def build_totals(db: Session) -> dict[str, int]:
    return {
        "players": scalar_count(db, Player.id),
        "squad_appearances": scalar_count(db, SquadAppearance.id),
        "spin_pool_records": scalar_count(db, SpinPool.id),
    }


def scalar_count(db: Session, column: Any) -> int:
    return int(db.scalar(select(func.count(column))) or 0)


def find_duplicate_player_name_country_combinations(
    db: Session,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Player.display_name,
            Country.name,
            func.count(Player.id).label("count"),
        )
        .join(Country, Player.country_id == Country.id)
        .group_by(Player.display_name, Country.name)
        .having(func.count(Player.id) > 1)
        .order_by(Country.name, Player.display_name),
    ).all()

    return [
        {
            "player_name": display_name,
            "country": country_name,
            "count": count,
        }
        for display_name, country_name, count in rows
    ]


def find_players_appearing_for_multiple_countries(
    db: Session,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Player.display_name)
        .join(SquadAppearance, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .group_by(Player.display_name)
        .having(func.count(func.distinct(Country.id)) > 1)
        .order_by(Player.display_name),
    ).scalars().all()

    results: list[dict[str, Any]] = []
    for player_name in rows:
        appearances = db.execute(
            select(Country.name, Tournament.year)
            .select_from(SquadAppearance)
            .join(Player, SquadAppearance.player_id == Player.id)
            .join(Country, SquadAppearance.country_id == Country.id)
            .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
            .where(Player.display_name == player_name)
            .group_by(Country.name, Tournament.year)
            .order_by(Country.name, Tournament.year),
        ).all()

        countries: dict[str, list[int]] = {}
        for country_name, year in appearances:
            countries.setdefault(country_name, []).append(year)

        results.append(
            {
                "player_name": player_name,
                "countries": [
                    {"country": country, "years": years}
                    for country, years in sorted(countries.items())
                ],
            },
        )

    return results


def find_squad_appearances_without_spin_pool_rows(
    db: Session,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            SquadAppearance.id,
            Player.display_name,
            Country.name,
            Tournament.year,
        )
        .select_from(SquadAppearance)
        .join(Player, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .outerjoin(SpinPool, SpinPool.squad_appearance_id == SquadAppearance.id)
        .where(SpinPool.id.is_(None))
        .order_by(Tournament.year, Country.name, Player.display_name),
    ).all()

    return [
        {
            "squad_appearance_id": squad_appearance_id,
            "player_name": player_name,
            "country": country,
            "year": year,
        }
        for squad_appearance_id, player_name, country, year in rows
    ]


def find_spin_pool_rows_without_squad_appearances(
    db: Session,
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            SpinPool.id,
            SpinPool.squad_appearance_id,
            Country.name,
            Tournament.year,
        )
        .select_from(SpinPool)
        .join(Country, SpinPool.country_id == Country.id)
        .join(Tournament, SpinPool.tournament_id == Tournament.id)
        .outerjoin(
            SquadAppearance,
            SpinPool.squad_appearance_id == SquadAppearance.id,
        )
        .where(SquadAppearance.id.is_(None))
        .order_by(Tournament.year, Country.name, SpinPool.id),
    ).all()

    return [
        {
            "spin_pool_id": spin_pool_id,
            "squad_appearance_id": squad_appearance_id,
            "country": country,
            "year": year,
        }
        for spin_pool_id, squad_appearance_id, country, year in rows
    ]


def build_tbc_positions_by_year(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Tournament.year,
            func.count(SquadAppearance.id).label("count"),
        )
        .select_from(SquadAppearance)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .join(Position, SquadAppearance.position_id == Position.id)
        .where(Position.code == "TBC")
        .group_by(Tournament.year)
        .order_by(Tournament.year),
    ).all()

    return [
        {
            "year": year,
            "count": count,
        }
        for year, count in rows
    ]


def build_player_counts_by_year_and_country(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            Tournament.year,
            Country.name,
            func.count(SquadAppearance.id).label("count"),
        )
        .select_from(SquadAppearance)
        .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .group_by(Tournament.year, Country.name)
        .order_by(Tournament.year, Country.name),
    ).all()

    return [
        {
            "year": year,
            "country": country,
            "count": count,
        }
        for year, country, count in rows
    ]


def build_summary(report: dict[str, Any]) -> dict[str, int]:
    return {
        "duplicate_player_name_country_combination_count": len(
            report["duplicate_player_name_country_combinations"],
        ),
        "players_appearing_for_multiple_countries_count": len(
            report["players_appearing_for_multiple_countries"],
        ),
        "squad_appearances_without_spin_pool_rows_count": len(
            report["squad_appearances_without_spin_pool_rows"],
        ),
        "spin_pool_rows_without_squad_appearances_count": len(
            report["spin_pool_rows_without_squad_appearances"],
        ),
    }


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    with SessionLocal() as db:
        report = build_audit_report(db)

    write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Audit report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
