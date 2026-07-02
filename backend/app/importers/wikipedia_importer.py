from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .base_importer import RawSquadRow, project_root
from .csv_importer import CsvSquadSource


class WikipediaCachedSquadSource:
    """Offline adapter for future Wikipedia-derived squad snapshots.

    This class intentionally does not fetch live pages. Cached exports can be
    stored as CSV files under data/imports/wikipedia and imported through the
    same row contract as every other source.
    """

    source_name = "wikipedia-cache"

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or project_root() / "data" / "imports" / "wikipedia"
        self.csv_source = CsvSquadSource(source_dirs=[self.cache_dir])

    def files_for_year(self, year: int) -> list[Path]:
        return self.csv_source.files_for_year(year)

    def rows_for_year(self, year: int) -> Iterable[RawSquadRow]:
        return self.csv_source.rows_for_year(year)
