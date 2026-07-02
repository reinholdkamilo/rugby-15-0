from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Country, Player, Position, SpinPool, SquadAppearance, Tournament
from .base_importer import ImportReport
from .normaliser import WORLD_CUP_YEARS


@dataclass
class ValidationReport:
    total_players: int = 0
    total_squad_appearances: int = 0
    total_spin_pool_records: int = 0
    players_imported: int = 0
    countries_imported: int = 0
    countries_imported_1987: list[str] = field(default_factory=list)
    countries_imported_1991: list[str] = field(default_factory=list)
    countries_imported_1995: list[str] = field(default_factory=list)
    countries_imported_1999: list[str] = field(default_factory=list)
    countries_imported_2003: list[str] = field(default_factory=list)
    countries_imported_2007: list[str] = field(default_factory=list)
    countries_imported_2011: list[str] = field(default_factory=list)
    countries_imported_2015: list[str] = field(default_factory=list)
    countries_imported_2019: list[str] = field(default_factory=list)
    countries_imported_2023: list[str] = field(default_factory=list)
    players_per_1987_country: dict[str, int] = field(default_factory=dict)
    players_per_1991_country: dict[str, int] = field(default_factory=dict)
    players_per_1995_country: dict[str, int] = field(default_factory=dict)
    players_per_1999_country: dict[str, int] = field(default_factory=dict)
    players_per_2003_country: dict[str, int] = field(default_factory=dict)
    players_per_2007_country: dict[str, int] = field(default_factory=dict)
    players_per_2011_country: dict[str, int] = field(default_factory=dict)
    players_per_2015_country: dict[str, int] = field(default_factory=dict)
    players_per_country: dict[str, int] = field(default_factory=dict)
    players_per_2023_country: dict[str, int] = field(default_factory=dict)
    duplicates_detected: int = 0
    missing_positions: int = 0
    rows_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_players": self.total_players,
            "total_squad_appearances": self.total_squad_appearances,
            "total_spin_pool_records": self.total_spin_pool_records,
            "players_imported": self.players_imported,
            "countries_imported": self.countries_imported,
            "countries_imported_1987": self.countries_imported_1987,
            "countries_imported_1991": self.countries_imported_1991,
            "countries_imported_1995": self.countries_imported_1995,
            "countries_imported_1999": self.countries_imported_1999,
            "countries_imported_2003": self.countries_imported_2003,
            "countries_imported_2007": self.countries_imported_2007,
            "countries_imported_2011": self.countries_imported_2011,
            "countries_imported_2015": self.countries_imported_2015,
            "countries_imported_2019": self.countries_imported_2019,
            "countries_imported_2023": self.countries_imported_2023,
            "players_per_1987_country": self.players_per_1987_country,
            "players_per_1991_country": self.players_per_1991_country,
            "players_per_1995_country": self.players_per_1995_country,
            "players_per_1999_country": self.players_per_1999_country,
            "players_per_2003_country": self.players_per_2003_country,
            "players_per_2007_country": self.players_per_2007_country,
            "players_per_2011_country": self.players_per_2011_country,
            "players_per_2015_country": self.players_per_2015_country,
            "players_per_country": self.players_per_country,
            "players_per_2023_country": self.players_per_2023_country,
            "duplicates_detected": self.duplicates_detected,
            "missing_positions": self.missing_positions,
            "rows_skipped": self.rows_skipped,
            "warnings": self.warnings,
        }


def validate_database(db: Session, import_report: ImportReport) -> ValidationReport:
    total_players = len(db.scalars(select(Player.id)).all())
    total_squad_appearances = len(db.scalars(select(SquadAppearance.id)).all())
    total_spin_pool_records = len(db.scalars(select(SpinPool.id)).all())

    report = ValidationReport(
        total_players=total_players,
        total_squad_appearances=total_squad_appearances,
        total_spin_pool_records=total_spin_pool_records,
        players_imported=total_players,
        countries_imported=len(db.scalars(select(Country.id)).all()),
        duplicates_detected=import_report.duplicates_detected,
        missing_positions=import_report.missing_positions,
        rows_skipped=import_report.rows_skipped,
        warnings=list(import_report.warnings),
    )

    validate_world_cup_years(db, report)
    validate_squad_positions(db, report)
    validate_duplicate_squad_appearances(db, report)
    validate_spin_pool_coverage(report)
    add_year_breakdown(db, report, 1987)
    add_year_breakdown(db, report, 1991)
    add_year_breakdown(db, report, 1995)
    add_year_breakdown(db, report, 1999)
    add_year_breakdown(db, report, 2003)
    add_year_breakdown(db, report, 2007)
    add_year_breakdown(db, report, 2011)
    add_year_breakdown(db, report, 2015)
    add_year_breakdown(db, report, 2019)
    add_year_breakdown(db, report, 2023)
    return report


def validate_world_cup_years(db: Session, report: ValidationReport) -> None:
    existing_years = set(db.scalars(select(Tournament.year)).all())
    for year in WORLD_CUP_YEARS:
        if year not in existing_years:
            report.warnings.append(f"Missing tournament seed for Rugby World Cup {year}")


def validate_squad_positions(db: Session, report: ValidationReport) -> None:
    position_ids = set(db.scalars(select(Position.id)).all())
    squad_appearances = db.scalars(select(SquadAppearance)).all()

    for squad_appearance in squad_appearances:
        if squad_appearance.position_id not in position_ids:
            report.missing_positions += 1
            report.warnings.append(
                "Squad appearance has missing position: "
                f"id={squad_appearance.id}",
            )


def validate_duplicate_squad_appearances(
    db: Session,
    report: ValidationReport,
) -> None:
    seen: set[tuple[int, int, int]] = set()
    squad_appearances = db.scalars(select(SquadAppearance)).all()

    for squad_appearance in squad_appearances:
        key = (
            squad_appearance.player_id,
            squad_appearance.country_id,
            squad_appearance.tournament_id,
        )
        if key in seen:
            report.duplicates_detected += 1
            report.warnings.append(
                "Duplicate squad appearance detected in database: "
                f"id={squad_appearance.id}",
            )
        seen.add(key)


def validate_spin_pool_coverage(report: ValidationReport) -> None:
    if report.total_spin_pool_records != report.total_squad_appearances:
        report.warnings.append(
            "Spin pool count does not match squad appearances: "
            f"{report.total_spin_pool_records} spin pool rows for "
            f"{report.total_squad_appearances} squad appearances",
        )


def add_year_breakdown(db: Session, report: ValidationReport, year: int) -> None:
    tournament = db.scalar(select(Tournament).where(Tournament.year == year))
    if tournament is None:
        report.warnings.append(f"Cannot build {year} breakdown; tournament is missing")
        return

    squad_appearances = db.scalars(
        select(SquadAppearance).where(SquadAppearance.tournament_id == tournament.id),
    ).all()
    players_per_country: dict[str, int] = {}

    for squad_appearance in squad_appearances:
        country_name = squad_appearance.country.name
        players_per_country[country_name] = players_per_country.get(country_name, 0) + 1

    if year == 1987:
        report.countries_imported_1987 = sorted(players_per_country)
        report.players_per_1987_country = dict(sorted(players_per_country.items()))
    elif year == 1991:
        report.countries_imported_1991 = sorted(players_per_country)
        report.players_per_1991_country = dict(sorted(players_per_country.items()))
    elif year == 1995:
        report.countries_imported_1995 = sorted(players_per_country)
        report.players_per_1995_country = dict(sorted(players_per_country.items()))
    elif year == 1999:
        report.countries_imported_1999 = sorted(players_per_country)
        report.players_per_1999_country = dict(sorted(players_per_country.items()))
    elif year == 2003:
        report.countries_imported_2003 = sorted(players_per_country)
        report.players_per_2003_country = dict(sorted(players_per_country.items()))
    elif year == 2007:
        report.countries_imported_2007 = sorted(players_per_country)
        report.players_per_2007_country = dict(sorted(players_per_country.items()))
    elif year == 2011:
        report.countries_imported_2011 = sorted(players_per_country)
        report.players_per_2011_country = dict(sorted(players_per_country.items()))
    elif year == 2015:
        report.countries_imported_2015 = sorted(players_per_country)
        report.players_per_2015_country = dict(sorted(players_per_country.items()))
    elif year == 2019:
        report.countries_imported_2019 = sorted(players_per_country)
        report.players_per_country = dict(sorted(players_per_country.items()))
    elif year == 2023:
        report.countries_imported_2023 = sorted(players_per_country)
        report.players_per_2023_country = dict(sorted(players_per_country.items()))
