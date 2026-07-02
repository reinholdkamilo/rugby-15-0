from __future__ import annotations

from sqlalchemy import inspect, text

from ..database import Base, engine
from ..models import Rating, SpinPool


RATING_COLUMNS = {
    "scrum": "FLOAT",
    "lineout": "FLOAT",
    "breakdown": "FLOAT",
    "carry": "FLOAT",
    "passing": "FLOAT",
    "goal_kicking": "FLOAT",
    "strike": "FLOAT",
    "defence": "FLOAT",
    "leadership": "FLOAT",
    "discipline": "FLOAT",
    "big_game": "FLOAT",
    "rugby_iq": "FLOAT",
    "best_position": "VARCHAR(8)",
    "style": "VARCHAR(120)",
    "rating_status": "VARCHAR(32)",
    "notes": "TEXT",
}


def ensure_database_schema() -> None:
    ensure_spin_pool_schema()
    Base.metadata.create_all(bind=engine)
    ensure_ratings_schema()


def ensure_spin_pool_schema() -> None:
    inspector = inspect(engine)
    if "spin_pool" not in inspector.get_table_names():
        return

    column_names = {
        column["name"]
        for column in inspector.get_columns("spin_pool")
    }
    if "squad_appearance_id" not in column_names:
        SpinPool.__table__.drop(bind=engine, checkfirst=True)
        return

    if "eligible_positions" not in column_names:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE spin_pool ADD COLUMN eligible_positions TEXT"),
            )


def ensure_ratings_schema() -> None:
    inspector = inspect(engine)
    if "ratings" not in inspector.get_table_names():
        return

    columns = inspector.get_columns("ratings")
    column_names = {column["name"] for column in columns}
    tournament_column = next(
        (column for column in columns if column["name"] == "tournament_id"),
        None,
    )
    if tournament_column is not None and not tournament_column.get("nullable", True):
        with engine.begin() as connection:
            rating_count = int(
                connection.execute(text("SELECT COUNT(*) FROM ratings")).scalar() or 0,
            )
        if rating_count == 0:
            Rating.__table__.drop(bind=engine, checkfirst=True)
            Base.metadata.create_all(bind=engine)
            ensure_ratings_schema()
            return

    missing_columns = {
        column_name: column_type
        for column_name, column_type in RATING_COLUMNS.items()
        if column_name not in column_names
    }
    if not missing_columns:
        return

    with engine.begin() as connection:
        for column_name, column_type in missing_columns.items():
            connection.execute(
                text(f"ALTER TABLE ratings ADD COLUMN {column_name} {column_type}"),
            )
