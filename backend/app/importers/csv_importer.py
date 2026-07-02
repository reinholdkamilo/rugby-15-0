from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .base_importer import RawSquadRow, project_root


class CsvSquadSource:
    source_name = "csv"

    def __init__(self, source_dirs: list[Path] | None = None) -> None:
        root = project_root()
        self.source_dirs = source_dirs or [
            root / "data" / "squads",
            root / "data" / "imports" / "rwc",
        ]

    def files_for_year(self, year: int) -> list[Path]:
        files: list[Path] = []
        patterns = [
            f"rwc_{year}_squads.csv",
            f"{year}_squads.csv",
            f"*{year}*squad*.csv",
        ]

        for source_dir in self.source_dirs:
            if not source_dir.exists():
                continue
            for pattern in patterns:
                files.extend(source_dir.glob(pattern))

        return sorted(set(files))

    def rows_for_year(self, year: int) -> Iterable[RawSquadRow]:
        for path in self.files_for_year(year):
            yield from self.rows_from_file(path, year)

    def rows_from_file(self, path: Path, expected_year: int) -> Iterable[RawSquadRow]:
        with path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            for row_number, row in enumerate(reader, start=2):
                raw_year = row.get("year") or str(expected_year)
                yield RawSquadRow(
                    year=int(raw_year),
                    country=row.get("country", ""),
                    player_name=row.get("player_name", "") or row.get("player", ""),
                    position=row.get("position", ""),
                    secondary_positions=row.get("secondary_positions", ""),
                    captain=row.get("captain", ""),
                    replacement=row.get("replacement", ""),
                    replacement_for=row.get("replacement_for", ""),
                    source_url=row.get("source_url", ""),
                    source_name=str(path),
                    row_number=row_number,
                )
