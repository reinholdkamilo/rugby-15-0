from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..database import BACKEND_DIR, SessionLocal
from ..rating_generator import generate_baseline_ratings
from .schema_utils import ensure_database_schema

REPORT_PATH = BACKEND_DIR / "reports" / "generated_ratings_report.json"


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic baseline ratings for squad appearances.",
    )
    parser.add_argument(
        "--overwrite-generated-only",
        action="store_true",
        help="Recalculate existing generated ratings while preserving manual ratings.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_database_schema()
    with SessionLocal() as db:
        report = generate_baseline_ratings(
            db,
            overwrite_generated_only=args.overwrite_generated_only,
        )
    write_report(report)
    print(json.dumps(report, indent=2))
    print(f"Generated ratings report written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
