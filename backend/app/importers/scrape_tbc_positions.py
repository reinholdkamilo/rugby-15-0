from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import BACKEND_DIR, SessionLocal
from ..models import Player, Position, SquadAppearance
from ..position_eligibility import expand_position_codes
from .schema_utils import ensure_spin_pool_schema
from .sources import allrugby, rugbypass, theanalyst
from .sources.common import ScrapeContext, ScrapeResult, storage_position_code

REPORT_PATH = BACKEND_DIR / "reports" / "tbc_position_scrape_report.json"
REVIEW_PATH = BACKEND_DIR / "reports" / "tbc_position_scrape_review.csv"
CACHE_DIR = BACKEND_DIR / "cache" / "position_scrape"
CSV_COLUMNS = [
    "player_name",
    "country",
    "current_position",
    "suggested_position",
    "confidence",
    "source_url",
    "source_name",
    "notes",
]
HIGH_CONFIDENCE_THRESHOLD = 0.9


def scrape_tbc_positions(
    db: Session,
    *,
    dry_run: bool = False,
    refresh: bool = False,
    limit: Optional[int] = None,
    delay_seconds: float = 1.0,
) -> dict[str, Any]:
    positions_by_code = {
        position.code: position for position in db.scalars(select(Position)).all()
    }
    tbc_position = positions_by_code.get("TBC")
    if tbc_position is None:
        report = build_empty_report(dry_run)
        report["warnings"].append("TBC position is not seeded; scraping skipped.")
        write_report(report)
        write_review_csv([])
        return report

    context = ScrapeContext(
        cache_dir=CACHE_DIR,
        refresh=refresh,
        delay_seconds=delay_seconds,
    )
    allrugby.set_context(context)
    rugbypass.set_context(context)
    theanalyst.set_context(context)

    appearances = load_tbc_appearances(db, tbc_position.id)
    grouped = group_tbc_appearances(appearances)
    grouped_items = list(grouped.items())
    if limit is not None:
        grouped_items = grouped_items[:limit]

    report: dict[str, Any] = build_empty_report(dry_run)
    report["summary"]["tbc_before"] = len(appearances)
    report["summary"]["players_checked"] = len(grouped_items)

    source_counter: Counter[str] = Counter()
    review_rows: list[dict[str, Any]] = []
    high_confidence_matches = 0
    low_confidence_matches = 0
    failed_lookups = 0

    for key, player_appearances in grouped_items:
        player = player_appearances[0].player
        if player is None or player.country is None:
            failed_lookups += 1
            continue

        result = lookup_player_position(player.display_name, player.country.name)
        if result is None:
            failed_lookups += 1
            review_rows.append(
                build_review_row(player_appearances, None, "No trusted source match found"),
            )
            continue

        if result.confidence < HIGH_CONFIDENCE_THRESHOLD:
            low_confidence_matches += 1
            review_rows.append(
                build_review_row(
                    player_appearances,
                    result,
                    "Confidence below threshold",
                ),
            )
            continue

        high_confidence_matches += 1
        source_counter[result.source_name] += 1
        for appearance in player_appearances:
            report["updates"].append(
                {
                    "player_id": appearance.player_id,
                    "player_name": appearance.player.display_name if appearance.player else "",
                    "country": appearance.country.name if appearance.country else "",
                    "year": appearance.tournament.year if appearance.tournament else None,
                    "squad_appearance_id": appearance.id,
                    "from_position": "TBC",
                    "to_position": result.position_code,
                    "source_url": result.source_url,
                    "source_name": result.source_name,
                    "confidence": result.confidence,
                    "notes": result.notes,
                },
            )
            if not dry_run:
                apply_update(appearance, result, positions_by_code)
            report["summary"]["positions_updated"] += 1

    report["summary"]["high_confidence_matches"] = high_confidence_matches
    report["summary"]["low_confidence_matches"] = low_confidence_matches
    report["summary"]["failed_lookups"] = failed_lookups
    report["summary"]["still_tbc"] = report["summary"]["tbc_before"] - report["summary"][
        "positions_updated"
    ]
    report["source_counts"] = dict(source_counter)
    report["warnings"].extend(context.warnings)

    if report["summary"]["positions_updated"] == 0:
        report["warnings"].append(
            "No high-confidence source matches were found during scraping.",
        )

    if dry_run:
        db.rollback()
    else:
        db.commit()

    write_report(report)
    write_review_csv(review_rows)
    return report


def load_tbc_appearances(db: Session, tbc_position_id: int) -> list[SquadAppearance]:
    return db.scalars(
        select(SquadAppearance)
        .options(
            selectinload(SquadAppearance.player).selectinload(Player.country),
            selectinload(SquadAppearance.country),
            selectinload(SquadAppearance.tournament),
            selectinload(SquadAppearance.position),
            selectinload(SquadAppearance.spin_pool_entries),
        )
        .where(SquadAppearance.position_id == tbc_position_id)
        .order_by(SquadAppearance.country_id, SquadAppearance.player_id, SquadAppearance.tournament_id),
    ).all()


def group_tbc_appearances(
    appearances: list[SquadAppearance],
) -> dict[tuple[str, str], list[SquadAppearance]]:
    grouped: dict[tuple[str, str], list[SquadAppearance]] = defaultdict(list)
    for appearance in appearances:
        if appearance.player is None or appearance.country is None:
            continue
        key = (
            appearance.player.display_name.strip().lower(),
            appearance.country.name.strip().lower(),
        )
        grouped[key].append(appearance)
    return grouped


def lookup_player_position(player_name: str, country: str) -> Optional[ScrapeResult]:
    for adapter in (allrugby, rugbypass, theanalyst):
        try:
            result = adapter.find_player_position(player_name, country)
        except Exception:
            continue
        if result is not None:
            return result
    return None


def apply_update(
    appearance: SquadAppearance,
    result: ScrapeResult,
    positions_by_code: dict[str, Position],
) -> None:
    storage_code = storage_position_code(result.position_code)
    position = positions_by_code.get(storage_code)
    if position is None:
        return

    appearance.position = position
    appearance.notes = merge_notes(
        appearance.notes,
        (
            f"TBC position scraped: {result.position_code} "
            f"(source: {result.source_name}, confidence: {result.confidence:.2f})"
        ),
    )
    eligible_positions = ",".join(expand_position_codes([result.position_code]))
    for spin_pool in appearance.spin_pool_entries:
        spin_pool.eligible_positions = eligible_positions


def merge_notes(existing_notes: Optional[str], new_note: str) -> str:
    if not existing_notes:
        return new_note
    if new_note in existing_notes:
        return existing_notes
    return f"{existing_notes}; {new_note}"


def build_review_row(
    appearances: list[SquadAppearance],
    result: Optional[ScrapeResult],
    notes: str,
) -> dict[str, Any]:
    first = appearances[0]
    years = ", ".join(
        str(appearance.tournament.year)
        for appearance in appearances
        if appearance.tournament is not None
    )
    return {
        "player_name": first.player.display_name if first.player else "",
        "country": first.country.name if first.country else "",
        "current_position": "TBC",
        "suggested_position": result.position_code if result else "",
        "confidence": f"{result.confidence:.2f}" if result else "",
        "source_url": result.source_url if result else "",
        "source_name": result.source_name if result else "",
        "notes": "; ".join(part for part in [notes, result.notes if result else "", f"years: {years}" if years else ""] if part),
    }


def build_empty_report(dry_run: bool) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "summary": {
            "tbc_before": 0,
            "players_checked": 0,
            "positions_updated": 0,
            "still_tbc": 0,
            "high_confidence_matches": 0,
            "low_confidence_matches": 0,
            "failed_lookups": 0,
        },
        "source_counts": {},
        "updates": [],
        "warnings": [],
    }


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


def write_review_csv(rows: list[dict[str, Any]], path: Path = REVIEW_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Scrape trusted rugby profile sites for remaining TBC positions.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached pages and search results.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N deduplicated player-country groups.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Delay in seconds between outbound requests.",
    )
    args = parser.parse_args(argv)

    ensure_spin_pool_schema()
    with SessionLocal() as db:
        report = scrape_tbc_positions(
            db,
            dry_run=args.dry_run,
            refresh=args.refresh,
            limit=args.limit,
            delay_seconds=args.delay,
        )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Scrape report written to {REPORT_PATH}")
    print(f"Review CSV written to {REVIEW_PATH}")


if __name__ == "__main__":
    main()
