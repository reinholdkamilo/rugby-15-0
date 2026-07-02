from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, PlayerAlias, Position, Rating, SpinPool
from ..models import SquadAppearance, Tournament
from ..rating_generator import build_rating_summary
from .audit import build_audit_report
from .base_importer import ImportReport
from .detect_duplicates import detect_duplicates
from .position_audit import build_position_audit
from .schema_utils import ensure_database_schema
from .validator import validate_database

REPORT_PATH = BACKEND_DIR / "reports" / "phase_a_check.json"


def scalar_count(db: Session, column: Any) -> int:
    return int(db.scalar(select(func.count(column))) or 0)


def build_database_counts(db: Session) -> dict[str, int]:
    return {
        "countries": scalar_count(db, Country.id),
        "tournaments": scalar_count(db, Tournament.id),
        "positions": scalar_count(db, Position.id),
        "players": scalar_count(db, Player.id),
        "squad_appearances": scalar_count(db, SquadAppearance.id),
        "spin_pool_records": scalar_count(db, SpinPool.id),
        "player_aliases": scalar_count(db, PlayerAlias.id),
        "ratings": scalar_count(db, Rating.id),
    }


def build_rating_status(db: Session) -> dict[str, Any]:
    rows = db.execute(
        select(Rating.rating_status, func.count(Rating.id))
        .group_by(Rating.rating_status)
        .order_by(Rating.rating_status),
    ).all()
    return {
        "total_ratings": scalar_count(db, Rating.id),
        "ratings_by_status": {
            str(status or "unknown"): count
            for status, count in rows
        },
        "player_level_ratings": int(
            db.scalar(
                select(func.count(Rating.id)).where(
                    Rating.squad_appearance_id.is_(None),
                ),
            )
            or 0
        ),
        "squad_appearance_ratings": int(
            db.scalar(
                select(func.count(Rating.id)).where(
                    Rating.squad_appearance_id.is_not(None),
                ),
            )
            or 0
        ),
    }


def count_players_without_aliases(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(Player.id))
            .outerjoin(PlayerAlias, PlayerAlias.player_id == Player.id)
            .where(PlayerAlias.id.is_(None)),
        )
        or 0
    )


def build_phase_a_check(db: Session) -> dict[str, Any]:
    validation = validate_database(db, ImportReport(source_name="phase-a-check"))
    audit = build_audit_report(db)
    position_audit = build_position_audit(db)
    duplicate_report = detect_duplicates(db)
    counts = build_database_counts(db)
    rating_status = build_rating_status(db)
    rating_summary = build_rating_summary(db)
    players_without_aliases = count_players_without_aliases(db)

    failures: list[str] = []
    warnings: list[str] = []

    if counts["spin_pool_records"] != counts["squad_appearances"]:
        failures.append(
            "Spin pool count does not match squad appearances: "
            f"{counts['spin_pool_records']} vs {counts['squad_appearances']}",
        )
    if audit["summary"]["squad_appearances_without_spin_pool_rows_count"]:
        failures.append("Some squad appearances do not have spin pool rows.")
    if audit["summary"]["spin_pool_rows_without_squad_appearances_count"]:
        failures.append("Some spin pool rows do not reference valid squad appearances.")
    if players_without_aliases:
        failures.append(f"{players_without_aliases} players do not have aliases.")
    if counts["ratings"] == 0:
        failures.append("No ratings have been imported.")
    if rating_summary["unrated_squad_appearances"]:
        failures.append(
            "Some squad appearances do not have rating coverage: "
            f"{rating_summary['unrated_squad_appearances']}",
        )

    tbc_count = int(position_audit["total_tbc_positions"])
    if tbc_count:
        warnings.append(f"{tbc_count} squad appearances still use TBC positions.")
    if validation.warnings:
        warnings.extend(validation.warnings)

    duplicate_summary = duplicate_report["summary"]
    duplicate_candidate_count = sum(int(value) for value in duplicate_summary.values())
    if duplicate_candidate_count:
        warnings.append(
            f"{duplicate_candidate_count} duplicate candidate groups need review.",
        )

    invalid_positions = position_audit["invalid_position_codes"]
    invalid_position_count = len(invalid_positions["squad_appearances"]) + len(
        invalid_positions["spin_pool_eligible_positions"],
    )
    if invalid_position_count:
        failures.append(f"{invalid_position_count} invalid position references found.")

    status = "pass"
    if warnings:
        status = "warn"
    if failures:
        status = "fail"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "database_counts": counts,
        "import_validation": validation.to_dict(),
        "data_audit_summary": audit["summary"],
        "position_audit_summary": {
            "total_tbc_positions": position_audit["total_tbc_positions"],
            "invalid_position_count": invalid_position_count,
        },
        "alias_summary": {
            "total_aliases": counts["player_aliases"],
            "players_without_aliases": players_without_aliases,
        },
        "duplicate_summary": duplicate_summary,
        "rating_status": rating_status,
        "rating_summary": rating_summary,
    }


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def print_summary(report: dict[str, Any]) -> None:
    print(f"Phase A status: {report['status'].upper()}")
    counts = report["database_counts"]
    print(
        "Counts: "
        f"{counts['players']} players, "
        f"{counts['squad_appearances']} squad appearances, "
        f"{counts['spin_pool_records']} spin pool rows, "
        f"{counts['player_aliases']} aliases, "
        f"{counts['ratings']} ratings",
    )
    for failure in report["failures"]:
        print(f"FAIL: {failure}")
    for warning in report["warnings"][:20]:
        print(f"WARN: {warning}")
    if len(report["warnings"]) > 20:
        print(f"WARN: {len(report['warnings']) - 20} additional warnings in report.")
    print(f"Phase A report written to {REPORT_PATH}")


def main() -> None:
    ensure_database_schema()
    with SessionLocal() as db:
        report = build_phase_a_check(db)
    write_report(report)
    print_summary(report)


if __name__ == "__main__":
    main()
