from __future__ import annotations

import json

from ..database import SessionLocal
from ..seed import seed_countries, seed_positions, seed_tournaments
from .base_importer import BaseImporter, ImportReport
from .csv_importer import CsvSquadSource
from .normaliser import WORLD_CUP_YEARS
from .schema_utils import ensure_database_schema
from .validator import validate_database
from .wikipedia_importer import WikipediaCachedSquadSource


def import_all() -> dict[str, object]:
    ensure_database_schema()
    aggregate_report = ImportReport(source_name="rwc-all")

    with SessionLocal() as db:
        countries_by_code = seed_countries(db)
        seed_positions(db)
        seed_tournaments(db, countries_by_code)
        db.flush()

        sources = [
            CsvSquadSource(),
            WikipediaCachedSquadSource(),
        ]

        for year in WORLD_CUP_YEARS:
            year_had_source = False
            for source in sources:
                if not source.files_for_year(year):
                    continue

                year_had_source = True
                report = BaseImporter(db, source).import_year(year)
                aggregate_report.merge(report)

            if not year_had_source:
                aggregate_report.warn(
                    f"No offline source file found for Rugby World Cup {year}",
                )

        db.commit()
        validation_report = validate_database(db, aggregate_report)

    return {
        "import": aggregate_report.to_dict(),
        "validation": validation_report.to_dict(),
    }

def main() -> None:
    print(json.dumps(import_all(), indent=2))


if __name__ == "__main__":
    main()
