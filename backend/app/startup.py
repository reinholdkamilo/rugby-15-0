from __future__ import annotations

import logging

from sqlalchemy import func, select

from . import models
from .database import SessionLocal
from .importers.import_all import import_all
from .importers.schema_utils import ensure_database_schema
from .rating_generator import count_unrated_appearances, generate_baseline_ratings
from .seed import run_seed

logger = logging.getLogger(__name__)


def initialise_database_on_startup() -> None:
    """Create and populate the SQLite database when a fresh deployment starts."""
    logger.info("Initialising database schema")
    ensure_database_schema()

    logger.info("Ensuring base seed data exists")
    run_seed()

    squad_appearance_count = _count_squad_appearances()
    if squad_appearance_count == 0:
        logger.info("No squad appearances found; importing Rugby World Cup squads")
        import_all()
        squad_appearance_count = _count_squad_appearances()
    else:
        logger.info(
            "Database already populated with %s squad appearances",
            squad_appearance_count,
        )

    if squad_appearance_count == 0:
        logger.warning("No squad appearances available after startup import")
        return

    unrated_count = _count_unrated_squad_appearances()
    if unrated_count > 0:
        logger.info(
            "Generating baseline ratings for %s unrated squad appearances",
            unrated_count,
        )
        with SessionLocal() as db:
            report = generate_baseline_ratings(db)
        logger.info(
            "Generated baseline ratings: created=%s updated=%s unrated_remaining=%s",
            report.get("ratings_created", 0),
            report.get("ratings_updated", 0),
            report.get("unrated_squad_appearances_remaining", 0),
        )
    else:
        logger.info("Ratings already populated for all squad appearances")


def _count_squad_appearances() -> int:
    with SessionLocal() as db:
        return int(
            db.scalar(select(func.count(models.SquadAppearance.id))) or 0,
        )


def _count_unrated_squad_appearances() -> int:
    with SessionLocal() as db:
        return count_unrated_appearances(db)
