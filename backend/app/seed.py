from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from app.database import Base, SessionLocal, engine
    from app.models import Country, Position, Tournament
else:
    from .database import Base, SessionLocal, engine
    from .models import Country, Position, Tournament


COUNTRIES = [
    {"name": "New Zealand", "code": "NZL", "flag_emoji": "🇳🇿"},
    {"name": "Russia", "code": "RUS", "flag_emoji": "🇷🇺"},
    {"name": "South Africa", "code": "RSA", "flag_emoji": "🇿🇦"},
    {"name": "Australia", "code": "AUS", "flag_emoji": "🇦🇺"},
    {"name": "Chile", "code": "CHL", "flag_emoji": "🇨🇱"},
    {"name": "Spain", "code": "ESP", "flag_emoji": "🇪🇸"},
    {"name": "England", "code": "ENG", "flag_emoji": "🏴"},
    {"name": "France", "code": "FRA", "flag_emoji": "🇫🇷"},
    {"name": "Ivory Coast", "code": "CIV", "flag_emoji": "🇨🇮"},
    {"name": "Ireland", "code": "IRE", "flag_emoji": "🇮🇪"},
    {"name": "Wales", "code": "WAL", "flag_emoji": "🏴"},
    {"name": "Scotland", "code": "SCO", "flag_emoji": "🏴"},
    {"name": "Argentina", "code": "ARG", "flag_emoji": "🇦🇷"},
    {"name": "Fiji", "code": "FIJ", "flag_emoji": "🇫🇯"},
    {"name": "Japan", "code": "JPN", "flag_emoji": "🇯🇵"},
    {"name": "Italy", "code": "ITA", "flag_emoji": "🇮🇹"},
    {"name": "Samoa", "code": "SAM", "flag_emoji": "🇼🇸"},
    {"name": "Tonga", "code": "TON", "flag_emoji": "🇹🇴"},
    {"name": "USA", "code": "USA", "flag_emoji": "🇺🇸"},
    {"name": "Canada", "code": "CAN", "flag_emoji": "🇨🇦"},
    {"name": "Uruguay", "code": "URU", "flag_emoji": "🇺🇾"},
    {"name": "Namibia", "code": "NAM", "flag_emoji": "🇳🇦"},
    {"name": "Portugal", "code": "PRT", "flag_emoji": "🇵🇹"},
    {"name": "Georgia", "code": "GEO", "flag_emoji": "🇬🇪"},
    {"name": "Romania", "code": "ROU", "flag_emoji": "🇷🇴"},
    {"name": "Zimbabwe", "code": "ZIM", "flag_emoji": "🇿🇼"},
]

POSITIONS = [
    {"code": "LH", "name": "Loosehead Prop", "unit": "front_row", "jersey_number": 1},
    {"code": "HK", "name": "Hooker", "unit": "front_row", "jersey_number": 2},
    {"code": "TH", "name": "Tighthead Prop", "unit": "front_row", "jersey_number": 3},
    {"code": "LK4", "name": "Lock 4", "unit": "second_row", "jersey_number": 4},
    {"code": "LK5", "name": "Lock 5", "unit": "second_row", "jersey_number": 5},
    {"code": "BSF", "name": "Blindside Flanker", "unit": "back_row", "jersey_number": 6},
    {"code": "OSF", "name": "Openside Flanker", "unit": "back_row", "jersey_number": 7},
    {"code": "N8", "name": "Number 8", "unit": "back_row", "jersey_number": 8},
    {"code": "SH", "name": "Scrum-half", "unit": "half_backs", "jersey_number": 9},
    {"code": "FH", "name": "Fly-half", "unit": "half_backs", "jersey_number": 10},
    {"code": "LW", "name": "Left Wing", "unit": "outside_backs", "jersey_number": 11},
    {"code": "IC", "name": "Inside Centre", "unit": "midfield", "jersey_number": 12},
    {"code": "OC", "name": "Outside Centre", "unit": "midfield", "jersey_number": 13},
    {"code": "RW", "name": "Right Wing", "unit": "outside_backs", "jersey_number": 14},
    {"code": "FB", "name": "Fullback", "unit": "outside_backs", "jersey_number": 15},
    {"code": "UTIL", "name": "Utility", "unit": "utility", "jersey_number": None},
    {"code": "TBC", "name": "TBC", "unit": "tbc", "jersey_number": None},
]

TOURNAMENTS = [
    {"year": 1987, "name": "1987 Rugby World Cup", "host_code": "NZL"},
    {"year": 1991, "name": "1991 Rugby World Cup", "host_code": "ENG"},
    {"year": 1995, "name": "1995 Rugby World Cup", "host_code": "RSA"},
    {"year": 1999, "name": "1999 Rugby World Cup", "host_code": "WAL"},
    {"year": 2003, "name": "2003 Rugby World Cup", "host_code": "AUS"},
    {"year": 2007, "name": "2007 Rugby World Cup", "host_code": "FRA"},
    {"year": 2011, "name": "2011 Rugby World Cup", "host_code": "NZL"},
    {"year": 2015, "name": "2015 Rugby World Cup", "host_code": "ENG"},
    {"year": 2019, "name": "2019 Rugby World Cup", "host_code": "JPN"},
    {"year": 2023, "name": "2023 Rugby World Cup", "host_code": "FRA"},
]


def seed_countries(db: Session) -> dict[str, Country]:
    countries_by_code: dict[str, Country] = {}

    for data in COUNTRIES:
        country = db.scalar(select(Country).where(Country.code == data["code"]))
        if country is None:
            country = Country(**data)
            db.add(country)
        else:
            country.name = data["name"]
            country.flag_emoji = data["flag_emoji"]
        countries_by_code[data["code"]] = country

    db.flush()
    return countries_by_code


def seed_positions(db: Session) -> None:
    for sort_order, data in enumerate(POSITIONS, start=1):
        position = db.scalar(select(Position).where(Position.code == data["code"]))
        payload = {**data, "sort_order": sort_order}

        if position is None:
            db.add(Position(**payload))
        else:
            position.name = payload["name"]
            position.unit = payload["unit"]
            position.jersey_number = payload["jersey_number"]
            position.sort_order = payload["sort_order"]


def seed_tournaments(db: Session, countries_by_code: dict[str, Country]) -> None:
    for data in TOURNAMENTS:
        tournament = db.scalar(select(Tournament).where(Tournament.year == data["year"]))
        host_country = countries_by_code[data["host_code"]]

        if tournament is None:
            db.add(
                Tournament(
                    year=data["year"],
                    name=data["name"],
                    host_country=host_country,
                ),
            )
        else:
            tournament.name = data["name"]
            tournament.host_country = host_country


def run_seed() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        countries_by_code = seed_countries(db)
        seed_positions(db)
        seed_tournaments(db, countries_by_code)
        db.commit()


if __name__ == "__main__":
    run_seed()
    print("Seed data loaded.")
