from __future__ import annotations

import json
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import BACKEND_DIR, SessionLocal
from ..models import Country, Player, PlayerAlias, SquadAppearance, Tournament
from .normaliser import normalise_key
from .schema_utils import ensure_database_schema

REPORT_PATH = BACKEND_DIR / "reports" / "duplicate_detection_report.json"
MERGE_TEMPLATE_PATH = BACKEND_DIR / "reports" / "player_merge_template.csv"


def detect_duplicates(db: Session) -> dict[str, Any]:
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "same_normalised_name_same_country": same_name_same_country(db),
        "same_normalised_name_different_countries": same_name_different_countries(db),
        "highly_similar_names_within_same_country": similar_names_same_country(db),
        "players_appearing_across_multiple_countries": players_across_countries(db),
        "duplicate_aliases_pointing_to_multiple_players": duplicate_aliases(db),
    }
    report["summary"] = {
        key: len(value)
        for key, value in report.items()
        if isinstance(value, list)
    }
    return report


def player_payload(player: Player) -> dict[str, Any]:
    return {
        "player_id": player.id,
        "display_name": player.display_name,
        "country": player.country.name if player.country else None,
    }


def same_name_same_country(db: Session) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int | None], list[Player]] = {}
    for player in db.scalars(select(Player).order_by(Player.display_name)).all():
        groups.setdefault((normalise_key(player.display_name), player.country_id), []).append(
            player,
        )
    return [
        {
            "normalised_name": name_key,
            "country_id": country_id,
            "players": [player_payload(player) for player in players],
        }
        for (name_key, country_id), players in sorted(groups.items())
        if len(players) > 1
    ]


def same_name_different_countries(db: Session) -> list[dict[str, Any]]:
    groups: dict[str, list[Player]] = {}
    for player in db.scalars(select(Player).order_by(Player.display_name)).all():
        groups.setdefault(normalise_key(player.display_name), []).append(player)
    results = []
    for name_key, players in sorted(groups.items()):
        country_ids = {player.country_id for player in players}
        if len(country_ids) <= 1:
            continue
        results.append(
            {
                "normalised_name": name_key,
                "players": [player_payload(player) for player in players],
            },
        )
    return results


def similar_names_same_country(db: Session) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    countries = db.scalars(select(Country).order_by(Country.name)).all()
    for country in countries:
        players = db.scalars(
            select(Player)
            .where(Player.country_id == country.id)
            .order_by(Player.display_name),
        ).all()
        for index, left in enumerate(players):
            left_key = normalise_key(left.display_name)
            if len(left_key) < 6:
                continue
            for right in players[index + 1:]:
                right_key = normalise_key(right.display_name)
                if len(right_key) < 6:
                    continue
                if left_key == right_key:
                    continue
                ratio = SequenceMatcher(None, left_key, right_key).ratio()
                if ratio < 0.92:
                    continue
                results.append(
                    {
                        "country": country.name,
                        "similarity": round(ratio, 3),
                        "players": [player_payload(left), player_payload(right)],
                    },
                )
    return results


def players_across_countries(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Player.display_name)
        .join(SquadAppearance, SquadAppearance.player_id == Player.id)
        .join(Country, SquadAppearance.country_id == Country.id)
        .group_by(Player.display_name)
        .having(func.count(func.distinct(Country.id)) > 1)
        .order_by(Player.display_name),
    ).scalars().all()

    results: list[dict[str, Any]] = []
    for player_name in rows:
        appearances = db.execute(
            select(Country.name, Tournament.year)
            .select_from(SquadAppearance)
            .join(Player, SquadAppearance.player_id == Player.id)
            .join(Country, SquadAppearance.country_id == Country.id)
            .join(Tournament, SquadAppearance.tournament_id == Tournament.id)
            .where(Player.display_name == player_name)
            .group_by(Country.name, Tournament.year)
            .order_by(Country.name, Tournament.year),
        ).all()
        countries: dict[str, list[int]] = {}
        for country_name, year in appearances:
            countries.setdefault(country_name, []).append(year)
        results.append(
            {
                "player_name": player_name,
                "countries": [
                    {"country": country, "years": years}
                    for country, years in sorted(countries.items())
                ],
            },
        )
    return results


def duplicate_aliases(db: Session) -> list[dict[str, Any]]:
    aliases = db.scalars(select(PlayerAlias).order_by(PlayerAlias.alias_name)).all()
    groups: dict[str, list[PlayerAlias]] = {}
    for alias in aliases:
        groups.setdefault(normalise_key(alias.alias_name), []).append(alias)

    results = []
    for alias_key, alias_rows in sorted(groups.items()):
        player_ids = {alias.player_id for alias in alias_rows}
        if len(player_ids) <= 1:
            continue
        results.append(
            {
                "normalised_alias": alias_key,
                "aliases": [
                    {
                        "alias_id": alias.id,
                        "alias_name": alias.alias_name,
                        "player": player_payload(alias.player),
                    }
                    for alias in alias_rows
                ],
            },
        )
    return results


def write_merge_template(path: Path = MERGE_TEMPLATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text("source_player_id,target_player_id,reason,approved\n")


def write_report(report: dict[str, Any], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    ensure_database_schema()
    with SessionLocal() as db:
        report = detect_duplicates(db)
    write_report(report)
    write_merge_template()
    print(json.dumps(report, indent=2))
    print(f"Duplicate detection report written to {REPORT_PATH}")
    print(f"Player merge template written to {MERGE_TEMPLATE_PATH}")


if __name__ == "__main__":
    main()
