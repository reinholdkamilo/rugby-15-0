from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CountryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    flag_emoji: Optional[str] = None


class TournamentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    name: str
    host_country_id: Optional[int] = None


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    unit: str
    jersey_number: Optional[int] = None
    sort_order: int


class PlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: str
    date_of_birth: Optional[date] = None
    country_id: Optional[int] = None
    primary_position_id: Optional[int] = None


class AdminPlayerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    country_id: Optional[int] = None
    primary_position_id: Optional[int] = None


class AdminPlayerDetail(PlayerResponse):
    country: Optional[str] = None
    primary_position: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    squad_appearances: List[Dict[str, Any]] = Field(default_factory=list)


class SquadAppearanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int
    country_id: int
    tournament_id: int
    position_id: Optional[int] = None
    squad_number: Optional[int] = None
    caps_at_tournament: Optional[int] = None
    is_captain: bool
    notes: Optional[str] = None


class SpinResult(BaseModel):
    spin_pool_id: int
    squad_appearance_id: int
    player_name: str
    country: str
    year: int
    tournament: str
    position: Optional[str] = None
    eligible_positions: List[str]
    rating: Optional[float] = None


class SpinSquadPlayer(BaseModel):
    player_id: int
    squad_appearance_id: int
    player_name: str
    position: Optional[str] = None
    eligible_positions: List[str]
    rating: Optional[float] = None


class SpinSquadResult(BaseModel):
    country: str
    year: int
    tournament_id: int
    squad: List[SpinSquadPlayer]


class DraftPickCreate(BaseModel):
    squad_appearance_id: int
    selected_position: str


class DraftAutoSelectCreate(BaseModel):
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    countries: Optional[str] = None
    team_name: Optional[str] = None


class DraftPickResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    draft_session_id: int
    pick_number: int
    player_id: int
    squad_appearance_id: int
    selected_position: str
    created_at: datetime


class DraftSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    status: str
    current_pick_number: int
    max_picks: int
    picks: List[DraftPickResponse]


class DraftSessionRatingResponse(BaseModel):
    overall_rating: float
    pack_rating: float
    backline_rating: float
    spine_rating: float
    set_piece_rating: float
    breakdown_rating: float
    attack_rating: float
    defence_rating: float
    goal_kicking_rating: float
    missing_positions: List[str]
    position_count: Dict[str, int]
    is_complete: bool


class AutoSelectedPick(BaseModel):
    pick_number: int
    slot_number: int
    selected_position: str
    player_id: int
    squad_appearance_id: int
    player_name: str
    country: str
    year: int
    position: Optional[str] = None
    eligible_positions: List[str]
    rating: Optional[float] = None


class DraftAutoSelectResponse(BaseModel):
    draft_session: DraftSessionResponse
    rating: DraftSessionRatingResponse
    picks: List[AutoSelectedPick]
    high_rated_count: int
    below_90_count: int
    average_rating: float
    warnings: List[str] = Field(default_factory=list)


class SimulatedMatchResponse(BaseModel):
    match_number: int
    opponent_name: str
    opponent_rating: float
    win_probability: float
    result: str
    points_for: int
    points_against: int
    margin: int


class SeasonSimulationResponse(BaseModel):
    wins: int
    losses: int
    undefeated: bool
    team_rating: float
    matches: List[SimulatedMatchResponse]


class RatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int
    squad_appearance_id: Optional[int] = None
    tournament_id: Optional[int] = None
    overall: float
    set_piece: Optional[float] = None
    scrum: Optional[float] = None
    lineout: Optional[float] = None
    breakdown: Optional[float] = None
    carry: Optional[float] = None
    passing: Optional[float] = None
    kicking: Optional[float] = None
    goal_kicking: Optional[float] = None
    strike: Optional[float] = None
    defence: Optional[float] = None
    leadership: Optional[float] = None
    discipline: Optional[float] = None
    big_game: Optional[float] = None
    rugby_iq: Optional[float] = None
    best_position: Optional[str] = None
    style: Optional[str] = None
    rating_status: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class RatingUpdate(BaseModel):
    overall: Optional[float] = None
    set_piece: Optional[float] = None
    scrum: Optional[float] = None
    lineout: Optional[float] = None
    breakdown: Optional[float] = None
    carry: Optional[float] = None
    passing: Optional[float] = None
    kicking: Optional[float] = None
    goal_kicking: Optional[float] = None
    strike: Optional[float] = None
    defence: Optional[float] = None
    leadership: Optional[float] = None
    discipline: Optional[float] = None
    big_game: Optional[float] = None
    rugby_iq: Optional[float] = None
    best_position: Optional[str] = None
    style: Optional[str] = None
    rating_status: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class DataQualitySummary(BaseModel):
    players: int
    squad_appearances: int
    spin_pool_records: int
    ratings: int
    player_aliases: int
    tbc_positions: int
    duplicate_same_country: int
    duplicate_cross_country: int


class GeneratedRatingsReport(BaseModel):
    generated_at: str
    source: str
    overwrite_generated_only: bool
    ratings_created: int
    ratings_updated: int
    manual_ratings_preserved: int
    generated_rating_count: int
    ratings_by_band: Dict[str, int]
    ratings_by_country: Dict[str, int]
    ratings_by_year: Dict[str, int]
    unrated_squad_appearances_remaining: int


class RatingSummary(BaseModel):
    total_ratings: int
    manual_ratings: int
    generated_ratings: int
    unrated_squad_appearances: int
    rating_bands: Dict[str, int]
