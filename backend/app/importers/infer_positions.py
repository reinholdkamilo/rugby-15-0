from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import BACKEND_DIR, SessionLocal
from ..models import Player, Position, SpinPool, SquadAppearance
from .schema_utils import ensure_spin_pool_schema

REPORT_PATH = BACKEND_DIR / "reports" / "position_inference_report.json"


def infer_positions(db: Session, dry_run: bool = False) -> dict[str, Any]:
    positions_by_id = {
        position.id: position
        for position in db.scalars(select(Position)).all()
    }
    positions_by_code = {
        position.code: position
        for position in positions_by_id.values()
    }

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "summary": {
            "squad_appearance_positions_inferred": 0,
            "spin_pool_eligible_positions_updated": 0,
            "players_with_known_history": 0,
            "players_with_multiple_known_positions": 0,
        },
        "updates": [],
        "warnings": [],
    }

    tbc_position = positions_by_code.get("TBC")
    if tbc_position is None:
        report["warnings"].append("TBC position is not seeded; inference skipped.")
        return report

    infer_tbc_squad_appearances(
        db=db,
        positions_by_id=positions_by_id,
        tbc_position=tbc_position,
        report=report,
        dry_run=dry_run,
    )
    sync_spin_pool_eligible_positions(
        db=db,
        report=report,
        dry_run=dry_run,
    )

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return report


def infer_tbc_squad_appearances(
    db: Session,
    positions_by_id: dict[int, Position],
    tbc_position: Position,
    report: dict[str, Any],
    dry_run: bool,
) -> None:
    players = db.scalars(
        select(Player)
        .options(
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.position),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.country),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.tournament),
            selectinload(Player.squad_appearances)
            .selectinload(SquadAppearance.spin_pool_entries),
        )
        .order_by(Player.display_name, Player.id),
    ).all()

    for player in players:
        inferred_position = infer_player_position(player, positions_by_id)
        if inferred_position is None:
            continue

        report["summary"]["players_with_known_history"] += 1
        known_codes = [
            appearance.position.code
            for appearance in player.squad_appearances
            if appearance.position is not None
            and appearance.position.code != tbc_position.code
        ]
        if len(set(known_codes)) > 1:
            report["summary"]["players_with_multiple_known_positions"] += 1

        for appearance in player.squad_appearances:
            if appearance.position_id != tbc_position.id:
                continue
            log_squad_appearance_update(
                report=report,
                player=player,
                appearance=appearance,
                inferred_position=inferred_position,
                known_codes=known_codes,
            )
            if not dry_run:
                appearance.position = inferred_position
                update_spin_pool_entries(appearance, inferred_position.code)
            report["summary"]["squad_appearance_positions_inferred"] += 1


def infer_player_position(
    player: Player,
    positions_by_id: dict[int, Position],
) -> Optional[Position]:
    known_positions: list[Position] = []
    for appearance in player.squad_appearances:
        if appearance.position_id is None:
            continue
        position = positions_by_id.get(appearance.position_id)
        if position is None or position.code == "TBC":
            continue
        known_positions.append(position)

    if not known_positions:
        return None

    counts = Counter(position.code for position in known_positions)
    positions_by_code = {position.code: position for position in known_positions}
    return sorted(
        positions_by_code.values(),
        key=lambda position: (
            -counts[position.code],
            position.sort_order,
            position.code,
        ),
    )[0]


def log_squad_appearance_update(
    report: dict[str, Any],
    player: Player,
    appearance: SquadAppearance,
    inferred_position: Position,
    known_codes: list[str],
) -> None:
    report["updates"].append(
        {
            "type": "squad_appearance_position_inferred",
            "player_id": player.id,
            "player_name": player.display_name,
            "squad_appearance_id": appearance.id,
            "country": appearance.country.name,
            "year": appearance.tournament.year,
            "from_position": "TBC",
            "to_position": inferred_position.code,
            "known_position_counts": dict(sorted(Counter(known_codes).items())),
        },
    )


def sync_spin_pool_eligible_positions(
    db: Session,
    report: dict[str, Any],
    dry_run: bool,
) -> None:
    spin_pool_rows = db.scalars(
        select(SpinPool)
        .options(
            selectinload(SpinPool.squad_appearance)
            .selectinload(SquadAppearance.position),
            selectinload(SpinPool.squad_appearance)
            .selectinload(SquadAppearance.player),
            selectinload(SpinPool.squad_appearance)
            .selectinload(SquadAppearance.country),
            selectinload(SpinPool.squad_appearance)
            .selectinload(SquadAppearance.tournament),
        )
        .order_by(SpinPool.id),
    ).all()

    for spin_pool in spin_pool_rows:
        appearance = spin_pool.squad_appearance
        position = appearance.position
        if position is None or position.code == "TBC":
            continue
        if not eligible_positions_needs_sync(spin_pool.eligible_positions):
            continue

        report["updates"].append(
            {
                "type": "spin_pool_eligible_positions_updated",
                "spin_pool_id": spin_pool.id,
                "squad_appearance_id": appearance.id,
                "player_name": appearance.player.display_name,
                "country": appearance.country.name,
                "year": appearance.tournament.year,
                "from_eligible_positions": spin_pool.eligible_positions,
                "to_eligible_positions": position.code,
            },
        )
        if not dry_run:
            spin_pool.eligible_positions = position.code
        report["summary"]["spin_pool_eligible_positions_updated"] += 1


def eligible_positions_needs_sync(raw_positions: Optional[str]) -> bool:
    if raw_positions is None:
        return True
    positions = [
        position.strip().upper()
        for position in raw_positions.split(",")
        if position.strip()
    ]
    return not positions or positions == ["TBC"]


def update_spin_pool_entries(
    appearance: SquadAppearance,
    position_code: str,
) -> None:
    for spin_pool in appearance.spin_pool_entries:
        spin_pool.eligible_positions = position_code


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer missing Rugby 15-0 positions.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the inference report without committing updates.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_spin_pool_schema()
    with SessionLocal() as db:
        report = infer_positions(db, dry_run=args.dry_run)

    write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Position inference report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
