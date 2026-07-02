from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Country, Player, Position, SpinPool, SquadAppearance, Tournament
from .normaliser import (
    NameParts,
    has_captain_marker,
    normalise_captain,
    normalise_country,
    normalise_key,
    normalise_player_name,
    normalise_position,
    normalise_positions,
    normalise_replacement,
    split_player_name,
)


@dataclass(frozen=True)
class RawSquadRow:
    year: int
    country: str
    player_name: str
    position: str
    secondary_positions: str = ""
    captain: str = ""
    replacement: str = ""
    replacement_for: str = ""
    source_url: str = ""
    source_name: str = ""
    row_number: int = 0


@dataclass(frozen=True)
class NormalisedSquadRow:
    year: int
    country: str
    player_name: str
    name_parts: NameParts
    position: str
    secondary_positions: list[str]
    captain: bool
    replacement: bool
    replacement_for: str
    source_url: str
    source_name: str
    row_number: int

    @property
    def duplicate_key(self) -> tuple[int, str, str]:
        return (self.year, self.country, normalise_key(self.player_name))


@dataclass
class ImportReport:
    source_name: str = "all"
    files_processed: int = 0
    rows_read: int = 0
    players_imported: int = 0
    players_created: int = 0
    players_updated: int = 0
    countries_imported: int = 0
    squad_appearances_created: int = 0
    squad_appearances_updated: int = 0
    spin_pool_created: int = 0
    spin_pool_existing: int = 0
    duplicates_detected: int = 0
    missing_positions: int = 0
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: "ImportReport") -> None:
        self.files_processed += other.files_processed
        self.rows_read += other.rows_read
        self.players_imported += other.players_imported
        self.players_created += other.players_created
        self.players_updated += other.players_updated
        self.countries_imported += other.countries_imported
        self.squad_appearances_created += other.squad_appearances_created
        self.squad_appearances_updated += other.squad_appearances_updated
        self.spin_pool_created += other.spin_pool_created
        self.spin_pool_existing += other.spin_pool_existing
        self.duplicates_detected += other.duplicates_detected
        self.missing_positions += other.missing_positions
        self.rows_skipped += other.rows_skipped
        self.warnings.extend(other.warnings)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_name": self.source_name,
            "files_processed": self.files_processed,
            "rows_read": self.rows_read,
            "players_imported": self.players_imported,
            "players_created": self.players_created,
            "players_updated": self.players_updated,
            "countries_imported": self.countries_imported,
            "squad_appearances_created": self.squad_appearances_created,
            "squad_appearances_updated": self.squad_appearances_updated,
            "spin_pool_created": self.spin_pool_created,
            "spin_pool_existing": self.spin_pool_existing,
            "duplicates_detected": self.duplicates_detected,
            "missing_positions": self.missing_positions,
            "rows_skipped": self.rows_skipped,
            "warnings": self.warnings,
        }


class SquadRowSource(Protocol):
    source_name: str

    def files_for_year(self, year: int) -> list[Path]:
        ...

    def rows_for_year(self, year: int) -> Iterable[RawSquadRow]:
        ...


class BaseImporter:
    def __init__(self, db: Session, source: SquadRowSource) -> None:
        self.db = db
        self.source = source

    def import_year(self, year: int) -> ImportReport:
        report = ImportReport(source_name=f"{self.source.source_name}:{year}")
        report.files_processed = len(self.source.files_for_year(year))
        seen_keys: set[tuple[int, str, str]] = set()

        for raw_row in self.source.rows_for_year(year):
            report.rows_read += 1
            row = self.normalise_row(raw_row)

            if row.duplicate_key in seen_keys:
                report.duplicates_detected += 1
                report.warn(
                    f"Duplicate row skipped: {row.year} {row.country} "
                    f"{row.player_name}",
                )
                continue
            seen_keys.add(row.duplicate_key)

            self.import_row(row, report)

        return report

    def normalise_row(self, row: RawSquadRow) -> NormalisedSquadRow:
        player_name = normalise_player_name(row.player_name)
        primary_position = normalise_position(row.position)

        return NormalisedSquadRow(
            year=row.year,
            country=normalise_country(row.country),
            player_name=player_name,
            name_parts=split_player_name(player_name),
            position=primary_position,
            secondary_positions=normalise_positions(row.secondary_positions),
            captain=(
                normalise_captain(row.captain)
                or has_captain_marker(row.player_name)
            ),
            replacement=normalise_replacement(row.replacement),
            replacement_for=normalise_player_name(row.replacement_for),
            source_url=row.source_url.strip(),
            source_name=row.source_name,
            row_number=row.row_number,
        )

    def import_row(self, row: NormalisedSquadRow, report: ImportReport) -> None:
        if not row.player_name:
            report.rows_skipped += 1
            report.warn(
                f"Blank player name skipped ({row.source_name}:{row.row_number})",
            )
            return

        country = self.get_country(row, report)
        tournament = self.get_tournament(row, report)
        position = self.get_position(row, report)

        if country is None or tournament is None or position is None:
            report.rows_skipped += 1
            return

        player = self.upsert_player(row, country, position, report)
        squad_appearance = self.upsert_squad_appearance(
            row=row,
            player=player,
            country=country,
            tournament=tournament,
            position=position,
            report=report,
        )
        self.ensure_spin_pool(squad_appearance, country, tournament, report)

    def get_country(
        self,
        row: NormalisedSquadRow,
        report: ImportReport,
    ) -> Optional[Country]:
        country = self.db.scalar(select(Country).where(Country.name == row.country))
        if country is None:
            report.warn(
                f"Missing country: {row.country} "
                f"({row.source_name}:{row.row_number})",
            )
        else:
            report.countries_imported += 1
        return country

    def get_tournament(
        self,
        row: NormalisedSquadRow,
        report: ImportReport,
    ) -> Optional[Tournament]:
        tournament = self.db.scalar(select(Tournament).where(Tournament.year == row.year))
        if tournament is None:
            report.warn(
                f"Missing tournament year: {row.year} "
                f"({row.source_name}:{row.row_number})",
            )
        return tournament

    def get_position(
        self,
        row: NormalisedSquadRow,
        report: ImportReport,
    ) -> Optional[Position]:
        position = self.db.scalar(select(Position).where(Position.code == row.position))
        if position is None:
            report.missing_positions += 1
            report.warn(
                f"Missing position: {row.position} for {row.player_name} "
                f"({row.source_name}:{row.row_number})",
            )
        return position

    def upsert_player(
        self,
        row: NormalisedSquadRow,
        country: Country,
        position: Position,
        report: ImportReport,
    ) -> Player:
        player = self.find_player(country, row.player_name)

        if player is None:
            player = Player(
                first_name=row.name_parts.first_name,
                last_name=row.name_parts.last_name,
                display_name=row.player_name,
                country=country,
                primary_position=position,
            )
            self.db.add(player)
            self.db.flush()
            report.players_created += 1
        else:
            player.first_name = row.name_parts.first_name
            player.last_name = row.name_parts.last_name
            player.primary_position = position
            report.players_updated += 1

        report.players_imported += 1
        return player

    def find_player(self, country: Country, player_name: str) -> Optional[Player]:
        players = self.db.scalars(
            select(Player).where(Player.country_id == country.id),
        ).all()
        requested_name_key = normalise_key(player_name)

        for player in players:
            if normalise_key(player.display_name) == requested_name_key:
                return player
        return None

    def upsert_squad_appearance(
        self,
        row: NormalisedSquadRow,
        player: Player,
        country: Country,
        tournament: Tournament,
        position: Position,
        report: ImportReport,
    ) -> SquadAppearance:
        squad_appearance = self.db.scalar(
            select(SquadAppearance).where(
                SquadAppearance.player_id == player.id,
                SquadAppearance.country_id == country.id,
                SquadAppearance.tournament_id == tournament.id,
            ),
        )
        notes = self.build_notes(row)

        if squad_appearance is None:
            squad_appearance = SquadAppearance(
                player=player,
                country=country,
                tournament=tournament,
                position=position,
                is_captain=row.captain,
                notes=notes,
            )
            self.db.add(squad_appearance)
            report.squad_appearances_created += 1
        else:
            squad_appearance.position = position
            squad_appearance.is_captain = row.captain
            squad_appearance.notes = notes
            report.squad_appearances_updated += 1

        return squad_appearance

    def ensure_spin_pool(
        self,
        squad_appearance: SquadAppearance,
        country: Country,
        tournament: Tournament,
        report: ImportReport,
    ) -> None:
        spin_pool = self.db.scalar(
            select(SpinPool).where(
                SpinPool.squad_appearance_id == squad_appearance.id,
            ),
        )
        if spin_pool is None:
            self.db.add(
                SpinPool(
                    country=country,
                    tournament=tournament,
                    squad_appearance=squad_appearance,
                    eligible_positions=self.build_eligible_positions(squad_appearance),
                ),
            )
            report.spin_pool_created += 1
        else:
            spin_pool.country = country
            spin_pool.tournament = tournament
            spin_pool.squad_appearance = squad_appearance
            spin_pool.is_active = True
            spin_pool.eligible_positions = self.build_eligible_positions(
                squad_appearance,
            )
            report.spin_pool_existing += 1

    def build_eligible_positions(self, squad_appearance: SquadAppearance) -> str:
        position_codes: list[str] = []
        if squad_appearance.position is not None:
            position_codes.append(squad_appearance.position.code)

        prefix = "Secondary positions: "
        if squad_appearance.notes:
            for section in squad_appearance.notes.split(";"):
                section = section.strip()
                if not section.startswith(prefix):
                    continue
                for code in section.removeprefix(prefix).split(","):
                    code = code.strip()
                    if code and code not in position_codes:
                        position_codes.append(code)

        return ",".join(position_codes)

    def build_notes(self, row: NormalisedSquadRow) -> Optional[str]:
        notes: list[str] = []
        if row.secondary_positions:
            notes.append(f"Secondary positions: {', '.join(row.secondary_positions)}")
        if row.replacement:
            replacement_note = "Replacement player"
            if row.replacement_for:
                replacement_note = f"{replacement_note} for {row.replacement_for}"
            notes.append(replacement_note)
        if row.source_url:
            notes.append(f"Source: {row.source_url}")
        return "; ".join(notes) if notes else None


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]
