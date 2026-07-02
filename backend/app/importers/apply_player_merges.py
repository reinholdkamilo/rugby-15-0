from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import DraftPick, Player, PlayerAlias, Rating, SquadAppearance
from .schema_utils import ensure_database_schema

MERGE_PATH = BACKEND_DIR / "reports" / "player_merges.csv"
REPORT_PATH = BACKEND_DIR / "reports" / "player_merge_report.json"
TRUE_VALUES = {"1", "true", "yes", "y", "approved"}


def apply_merges(db: Session, merge_path: Path = MERGE_PATH) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file": str(merge_path),
        "rows_read": 0,
        "rows_skipped": 0,
        "merges_applied": 0,
        "already_merged": 0,
        "warnings": [],
        "updates": [],
    }
    if not merge_path.exists():
        report["warnings"].append(
            "No merge file found. Create reports/player_merges.csv from "
            "reports/player_merge_template.csv.",
        )
        return report

    with merge_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            report["rows_read"] += 1
            if row.get("approved", "").strip().lower() not in TRUE_VALUES:
                report["rows_skipped"] += 1
                continue
            apply_merge_row(db, row, row_number, report)

    db.commit()
    return report


def apply_merge_row(
    db: Session,
    row: dict[str, str],
    row_number: int,
    report: dict[str, Any],
) -> None:
    try:
        source_player_id = int(row.get("source_player_id", "").strip())
        target_player_id = int(row.get("target_player_id", "").strip())
    except ValueError:
        skip(report, row_number, "Invalid source_player_id or target_player_id")
        return

    if source_player_id == target_player_id:
        skip(report, row_number, "Source and target player are the same")
        return

    source_player = db.get(Player, source_player_id)
    target_player = db.get(Player, target_player_id)
    if target_player is None:
        skip(report, row_number, f"Target player not found: {target_player_id}")
        return
    if source_player is None:
        report["already_merged"] += 1
        return

    update_log = {
        "source_player_id": source_player_id,
        "source_player_name": source_player.display_name,
        "target_player_id": target_player_id,
        "target_player_name": target_player.display_name,
        "reason": row.get("reason", "").strip(),
        "squad_appearances_reassigned": 0,
        "squad_appearances_collapsed": 0,
        "ratings_reassigned": 0,
        "aliases_reassigned": 0,
    }

    reassign_squad_appearances(db, source_player, target_player, update_log)
    reassign_ratings(db, source_player, target_player, update_log)
    reassign_aliases(db, source_player, target_player, update_log)
    db.delete(source_player)

    report["merges_applied"] += 1
    report["updates"].append(update_log)


def reassign_squad_appearances(
    db: Session,
    source_player: Player,
    target_player: Player,
    update_log: dict[str, Any],
) -> None:
    source_appearances = list(source_player.squad_appearances)
    for source_appearance in source_appearances:
        target_appearance = db.scalar(
            select(SquadAppearance).where(
                SquadAppearance.player_id == target_player.id,
                SquadAppearance.country_id == source_appearance.country_id,
                SquadAppearance.tournament_id == source_appearance.tournament_id,
            ),
        )
        if target_appearance is None:
            source_appearance.player = target_player
            update_log["squad_appearances_reassigned"] += 1
            continue

        for rating in list(source_appearance.ratings):
            rating.squad_appearance = target_appearance
            rating.player = target_player
            update_log["ratings_reassigned"] += 1
        for draft_pick in db.scalars(
            select(DraftPick).where(
                DraftPick.squad_appearance_id == source_appearance.id,
            ),
        ).all():
            draft_pick.squad_appearance = target_appearance
            draft_pick.player = target_player
        db.delete(source_appearance)
        update_log["squad_appearances_collapsed"] += 1


def reassign_ratings(
    db: Session,
    source_player: Player,
    target_player: Player,
    update_log: dict[str, Any],
) -> None:
    ratings = db.scalars(
        select(Rating).where(Rating.player_id == source_player.id),
    ).all()
    for rating in ratings:
        rating.player = target_player
        update_log["ratings_reassigned"] += 1


def reassign_aliases(
    db: Session,
    source_player: Player,
    target_player: Player,
    update_log: dict[str, Any],
) -> None:
    target_aliases = {
        alias.alias_name
        for alias in target_player.aliases
    }
    for alias in list(source_player.aliases):
        if alias.alias_name in target_aliases:
            db.delete(alias)
            continue
        alias.player = target_player
        target_aliases.add(alias.alias_name)
        update_log["aliases_reassigned"] += 1


def skip(report: dict[str, Any], row_number: int, message: str) -> None:
    report["rows_skipped"] += 1
    report["warnings"].append(f"Row {row_number}: {message}")


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    ensure_database_schema()
    with SessionLocal() as db:
        report = apply_merges(db)
    write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Player merge report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
