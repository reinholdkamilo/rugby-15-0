from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Country(TimestampMixin, Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(3), unique=True, index=True)
    flag_emoji: Mapped[Optional[str]] = mapped_column(String(8))

    hosted_tournaments: Mapped[List["Tournament"]] = relationship(
        back_populates="host_country",
        foreign_keys="Tournament.host_country_id",
    )
    players: Mapped[List["Player"]] = relationship(back_populates="country")
    squad_appearances: Mapped[List["SquadAppearance"]] = relationship(
        back_populates="country",
        cascade="all, delete-orphan",
    )
    spin_pool_entries: Mapped[List["SpinPool"]] = relationship(
        back_populates="country",
        cascade="all, delete-orphan",
    )


class Tournament(TimestampMixin, Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    year: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    host_country_id: Mapped[Optional[int]] = mapped_column(ForeignKey("countries.id"))

    host_country: Mapped[Optional[Country]] = relationship(
        back_populates="hosted_tournaments",
        foreign_keys=[host_country_id],
    )
    squad_appearances: Mapped[List["SquadAppearance"]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
    )
    ratings: Mapped[List["Rating"]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
    )
    spin_pool_entries: Mapped[List["SpinPool"]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("year >= 1987", name="ck_tournaments_year_min"),
    )


class Position(TimestampMixin, Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    unit: Mapped[str] = mapped_column(String(24), index=True)
    jersey_number: Mapped[Optional[int]] = mapped_column(Integer, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, unique=True)

    players: Mapped[List["Player"]] = relationship(back_populates="primary_position")
    squad_appearances: Mapped[List["SquadAppearance"]] = relationship(
        back_populates="position",
    )
    ratings: Mapped[List["Rating"]] = relationship(back_populates="position")

    __table_args__ = (
        CheckConstraint(
            "unit IN ('front_row', 'second_row', 'back_row', 'half_backs', "
            "'midfield', 'outside_backs', 'utility', 'tbc')",
            name="ck_positions_unit",
        ),
        CheckConstraint(
            "jersey_number IS NULL OR (jersey_number >= 1 AND jersey_number <= 15)",
            name="ck_positions_jersey_number_range",
        ),
    )


class Player(TimestampMixin, Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(80))
    last_name: Mapped[Optional[str]] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(160), index=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    country_id: Mapped[Optional[int]] = mapped_column(ForeignKey("countries.id"))
    primary_position_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("positions.id"),
    )

    country: Mapped[Optional[Country]] = relationship(back_populates="players")
    primary_position: Mapped[Optional[Position]] = relationship(back_populates="players")
    squad_appearances: Mapped[List["SquadAppearance"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
    )
    ratings: Mapped[List["Rating"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
    )
    aliases: Mapped[List["PlayerAlias"]] = relationship(
        back_populates="player",
        cascade="all, delete-orphan",
    )
    draft_picks: Mapped[List["DraftPick"]] = relationship(back_populates="player")


class PlayerAlias(Base):
    __tablename__ = "player_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    alias_name: Mapped[str] = mapped_column(String(160), index=True)
    source: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    player: Mapped[Player] = relationship(back_populates="aliases")

    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "alias_name",
            name="uq_player_aliases_player_alias",
        ),
    )


class SquadAppearance(TimestampMixin, Base):
    __tablename__ = "squad_appearances"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    position_id: Mapped[Optional[int]] = mapped_column(ForeignKey("positions.id"))
    squad_number: Mapped[Optional[int]] = mapped_column(Integer)
    caps_at_tournament: Mapped[Optional[int]] = mapped_column(Integer)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    player: Mapped[Player] = relationship(back_populates="squad_appearances")
    country: Mapped[Country] = relationship(back_populates="squad_appearances")
    tournament: Mapped[Tournament] = relationship(back_populates="squad_appearances")
    position: Mapped[Optional[Position]] = relationship(
        back_populates="squad_appearances",
    )
    ratings: Mapped[List["Rating"]] = relationship(
        back_populates="squad_appearance",
        cascade="all, delete-orphan",
    )
    draft_picks: Mapped[List["DraftPick"]] = relationship(
        back_populates="squad_appearance",
    )
    spin_pool_entries: Mapped[List["SpinPool"]] = relationship(
        back_populates="squad_appearance",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "country_id",
            "tournament_id",
            name="uq_squad_appearances_player_country_tournament",
        ),
        CheckConstraint(
            "squad_number IS NULL OR squad_number > 0",
            name="ck_squad_appearances_squad_number_positive",
        ),
        CheckConstraint(
            "caps_at_tournament IS NULL OR caps_at_tournament >= 0",
            name="ck_squad_appearances_caps_non_negative",
        ),
    )


class Rating(TimestampMixin, Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    tournament_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tournaments.id"),
        index=True,
    )
    position_id: Mapped[Optional[int]] = mapped_column(ForeignKey("positions.id"))
    squad_appearance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("squad_appearances.id"),
        index=True,
    )
    overall: Mapped[float] = mapped_column(Float, nullable=False)
    attack: Mapped[Optional[float]] = mapped_column(Float)
    defense: Mapped[Optional[float]] = mapped_column(Float)
    set_piece: Mapped[Optional[float]] = mapped_column(Float)
    scrum: Mapped[Optional[float]] = mapped_column(Float)
    lineout: Mapped[Optional[float]] = mapped_column(Float)
    breakdown: Mapped[Optional[float]] = mapped_column(Float)
    carry: Mapped[Optional[float]] = mapped_column(Float)
    passing: Mapped[Optional[float]] = mapped_column(Float)
    kicking: Mapped[Optional[float]] = mapped_column(Float)
    goal_kicking: Mapped[Optional[float]] = mapped_column(Float)
    strike: Mapped[Optional[float]] = mapped_column(Float)
    defence: Mapped[Optional[float]] = mapped_column(Float)
    leadership: Mapped[Optional[float]] = mapped_column(Float)
    discipline: Mapped[Optional[float]] = mapped_column(Float)
    big_game: Mapped[Optional[float]] = mapped_column(Float)
    rugby_iq: Mapped[Optional[float]] = mapped_column(Float)
    best_position: Mapped[Optional[str]] = mapped_column(String(8))
    style: Mapped[Optional[str]] = mapped_column(String(120))
    rating_status: Mapped[Optional[str]] = mapped_column(String(32))
    pace: Mapped[Optional[float]] = mapped_column(Float)
    stamina: Mapped[Optional[float]] = mapped_column(Float)
    source: Mapped[Optional[str]] = mapped_column(String(120))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    player: Mapped[Player] = relationship(back_populates="ratings")
    tournament: Mapped[Tournament] = relationship(back_populates="ratings")
    position: Mapped[Optional[Position]] = relationship(back_populates="ratings")
    squad_appearance: Mapped[Optional[SquadAppearance]] = relationship(
        back_populates="ratings",
    )

    __table_args__ = (
        UniqueConstraint(
            "player_id",
            "tournament_id",
            "position_id",
            name="uq_ratings_player_tournament_position",
        ),
        CheckConstraint("overall >= 0 AND overall <= 100", name="ck_ratings_overall"),
        CheckConstraint("attack >= 0 AND attack <= 100", name="ck_ratings_attack"),
        CheckConstraint("defense >= 0 AND defense <= 100", name="ck_ratings_defense"),
        CheckConstraint(
            "set_piece >= 0 AND set_piece <= 100",
            name="ck_ratings_set_piece",
        ),
        CheckConstraint("kicking >= 0 AND kicking <= 100", name="ck_ratings_kicking"),
        CheckConstraint("pace >= 0 AND pace <= 100", name="ck_ratings_pace"),
        CheckConstraint("stamina >= 0 AND stamina <= 100", name="ck_ratings_stamina"),
    )


class SpinPool(TimestampMixin, Base):
    __tablename__ = "spin_pool"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), index=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    squad_appearance_id: Mapped[int] = mapped_column(
        ForeignKey("squad_appearances.id"),
        unique=True,
        index=True,
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    eligible_positions: Mapped[Optional[str]] = mapped_column(Text)

    country: Mapped[Country] = relationship(back_populates="spin_pool_entries")
    tournament: Mapped[Tournament] = relationship(back_populates="spin_pool_entries")
    squad_appearance: Mapped[SquadAppearance] = relationship(
        back_populates="spin_pool_entries",
    )

    __table_args__ = (
        CheckConstraint("weight > 0", name="ck_spin_pool_weight_positive"),
    )


class DraftSession(Base):
    __tablename__ = "draft_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    current_pick_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_picks: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    picks: Mapped[List["DraftPick"]] = relationship(
        back_populates="draft_session",
        cascade="all, delete-orphan",
        order_by="DraftPick.pick_number",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed')",
            name="ck_draft_sessions_status",
        ),
        CheckConstraint(
            "current_pick_number >= 1",
            name="ck_draft_sessions_current_pick_number_positive",
        ),
        CheckConstraint("max_picks > 0", name="ck_draft_sessions_max_picks_positive"),
    )


class DraftPick(Base):
    __tablename__ = "draft_picks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    draft_session_id: Mapped[int] = mapped_column(
        ForeignKey("draft_sessions.id"),
        index=True,
    )
    pick_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    squad_appearance_id: Mapped[int] = mapped_column(
        ForeignKey("squad_appearances.id"),
        index=True,
    )
    selected_position: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    draft_session: Mapped[DraftSession] = relationship(back_populates="picks")
    player: Mapped[Player] = relationship(back_populates="draft_picks")
    squad_appearance: Mapped[SquadAppearance] = relationship(
        back_populates="draft_picks",
    )

    __table_args__ = (
        UniqueConstraint(
            "draft_session_id",
            "pick_number",
            name="uq_draft_picks_session_pick_number",
        ),
        UniqueConstraint(
            "draft_session_id",
            "squad_appearance_id",
            name="uq_draft_picks_session_squad_appearance",
        ),
        CheckConstraint("pick_number >= 1", name="ck_draft_picks_pick_number_positive"),
    )
