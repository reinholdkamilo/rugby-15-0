import logging
import os
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .database import get_db
from .importers.detect_duplicates import detect_duplicates
from .position_eligibility import (
    expand_position_codes,
    expand_position_codes_for_draft,
    parse_needed_positions,
    PLAYABLE_POSITION_CODES,
    to_game_position_code,
    to_storage_position_code,
)
from .rating_generator import build_rating_summary, generate_baseline_ratings
from .rating_engine import calculate_draft_session_rating
from .simulator import simulate_season

router = APIRouter()
logger = logging.getLogger(__name__)

DRAFT_POSITION_SLOTS = [
    "LH",
    "HK",
    "TH",
    "LK",
    "LK",
    "BF",
    "OF",
    "NE",
    "SH",
    "FH",
    "WG",
    "IC",
    "OC",
    "WG",
    "FB",
]


def normalize_position_code(value: str) -> str:
    return to_storage_position_code(value)


def secondary_positions_from_notes(notes: Optional[str]) -> List[str]:
    if not notes:
        return []

    prefix = "Secondary positions: "
    for section in notes.split(";"):
        section = section.strip()
        if section.startswith(prefix):
            raw_codes = section.removeprefix(prefix)
            return [
                normalize_position_code(code)
                for code in raw_codes.split(",")
                if code.strip()
            ]

    return []


def eligible_position_codes(
    squad_appearance: models.SquadAppearance,
    allow_tbc_any: bool = True,
) -> List[str]:
    cache_name = (
        "_eligible_position_codes_cache"
        if allow_tbc_any
        else "_eligible_position_codes_strict_cache"
    )
    cached = getattr(squad_appearance, cache_name, None)
    if cached is not None:
        return cached

    position_codes: List[str] = []
    if squad_appearance.position is not None:
        position_codes.append(squad_appearance.position.code)

    for code in secondary_positions_from_notes(squad_appearance.notes):
        if code not in position_codes:
            position_codes.append(code)

    if allow_tbc_any:
        expanded = expand_position_codes_for_draft(position_codes)
    else:
        expanded = expand_position_codes(position_codes)
    setattr(squad_appearance, cache_name, expanded)
    return expanded


def primary_position_code(
    squad_appearance: models.SquadAppearance,
) -> Optional[str]:
    if squad_appearance.position is None:
        return None
    return to_game_position_code(squad_appearance.position.code)


def rating_for_squad_appearance(
    db: Session,
    squad_appearance: models.SquadAppearance,
) -> Optional[float]:
    rating = db.scalar(
        select(models.Rating)
        .where(
            models.Rating.player_id == squad_appearance.player_id,
            models.Rating.tournament_id == squad_appearance.tournament_id,
        )
        .order_by(models.Rating.id),
    )
    return rating.overall if rating is not None else None


def parse_requested_countries(raw_countries: Optional[str]) -> set[str]:
    if not raw_countries:
        return set()
    return {
        country.strip().lower()
        for country in raw_countries.split(",")
        if country.strip()
    }


def country_matches(country: models.Country, requested_countries: set[str]) -> bool:
    if not requested_countries:
        return True
    return bool(
        requested_countries.intersection(
            {country.name.lower(), country.code.lower()},
        ),
    )


def spin_pool_rating(db: Session, spin_pool: models.SpinPool) -> float:
    return float(rating_for_squad_appearance(db, spin_pool.squad_appearance) or 80)


def spin_pool_rating_map(
    db: Session,
    spin_pools: List[models.SpinPool],
) -> dict[int, float]:
    ratings = db.scalars(select(models.Rating)).all()
    rating_by_appearance_id = {
        rating.squad_appearance_id: float(rating.overall)
        for rating in ratings
        if rating.squad_appearance_id is not None
    }
    rating_by_player_tournament = {
        (rating.player_id, rating.tournament_id): float(rating.overall)
        for rating in ratings
        if rating.tournament_id is not None
    }
    return {
        spin_pool.id: rating_by_appearance_id.get(
            spin_pool.squad_appearance_id,
            rating_by_player_tournament.get(
                (
                    spin_pool.squad_appearance.player_id,
                    spin_pool.squad_appearance.tournament_id,
                ),
                80,
            ),
        )
        for spin_pool in spin_pools
    }


def spin_pool_best_position_map(
    db: Session,
    spin_pools: List[models.SpinPool],
) -> dict[int, str]:
    ratings = db.scalars(select(models.Rating)).all()
    position_by_appearance_id = {
        rating.squad_appearance_id: rating.best_position
        for rating in ratings
        if rating.squad_appearance_id is not None and rating.best_position
    }
    position_by_player_tournament = {
        (rating.player_id, rating.tournament_id): rating.best_position
        for rating in ratings
        if rating.tournament_id is not None and rating.best_position
    }
    return {
        spin_pool.id: position_by_appearance_id.get(
            spin_pool.squad_appearance_id,
            position_by_player_tournament.get(
                (
                    spin_pool.squad_appearance.player_id,
                    spin_pool.squad_appearance.tournament_id,
                ),
                "",
            ),
        )
        for spin_pool in spin_pools
    }


def admin_player_detail(player: models.Player) -> schemas.AdminPlayerDetail:
    return schemas.AdminPlayerDetail(
        id=player.id,
        first_name=player.first_name,
        last_name=player.last_name,
        display_name=player.display_name,
        date_of_birth=player.date_of_birth,
        country_id=player.country_id,
        primary_position_id=player.primary_position_id,
        country=player.country.name if player.country else None,
        primary_position=(
            player.primary_position.code
            if player.primary_position is not None
            else None
        ),
        aliases=[alias.alias_name for alias in player.aliases],
        squad_appearances=[
            {
                "id": appearance.id,
                "country": appearance.country.name,
                "year": appearance.tournament.year,
                "position": (
                    appearance.position.code
                    if appearance.position is not None
                    else None
                ),
            }
            for appearance in player.squad_appearances
        ],
    )


def get_draft_session_or_404(
    db: Session,
    session_id: int,
) -> models.DraftSession:
    draft_session = db.scalar(
        select(models.DraftSession)
        .options(selectinload(models.DraftSession.picks))
        .where(models.DraftSession.id == session_id),
    )
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session not found.")
    return draft_session


def refresh_draft_session(
    db: Session,
    draft_session: models.DraftSession,
) -> models.DraftSession:
    db.commit()
    return get_draft_session_or_404(db, draft_session.id)


def validate_selected_position(
    selected_position: str,
    squad_appearance: models.SquadAppearance,
    draft_session: models.DraftSession,
) -> str:
    normalized_position = validate_selected_position_for_open_positions(
        selected_position,
        squad_appearance,
        draft_open_positions(draft_session),
    )
    return normalized_position


def validate_selected_position_for_open_positions(
    selected_position: str,
    squad_appearance: models.SquadAppearance,
    open_positions: List[str],
) -> str:
    normalized_position = normalize_position_code(selected_position)
    if not normalized_position:
        raise HTTPException(
            status_code=400,
            detail="selected_position is required.",
        )

    normalized_game_position = to_game_position_code(selected_position)
    if normalized_game_position not in set(PLAYABLE_POSITION_CODES):
        raise HTTPException(
            status_code=400,
            detail="selected_position must be a valid XV position.",
        )

    if normalized_game_position not in open_positions:
        raise HTTPException(
            status_code=400,
            detail="selected_position must be one of the currently open positions.",
        )

    eligible_positions = eligible_position_codes(squad_appearance)
    if "TBC" not in eligible_positions and normalized_game_position not in eligible_positions:
        raise HTTPException(
            status_code=400,
            detail=(
                "selected_position must be one of this player's eligible "
                f"positions: {', '.join(eligible_positions)}."
            ),
        )

    return normalized_position


def can_select_position_for_open_positions(
    selected_position: str,
    squad_appearance: models.SquadAppearance,
    open_positions: List[str],
) -> bool:
    try:
        validate_selected_position_for_open_positions(
            selected_position,
            squad_appearance,
            open_positions,
        )
    except HTTPException:
        return False
    return True


def can_auto_select_known_position_for_open_positions(
    selected_position: str,
    squad_appearance: models.SquadAppearance,
    open_positions: List[str],
    best_position: str = "",
) -> bool:
    normalized_game_position = to_game_position_code(selected_position)
    if normalized_game_position not in open_positions:
        return False

    return normalized_game_position in auto_select_known_position_codes(
        squad_appearance,
        best_position,
    )


def auto_select_known_position_codes(
    squad_appearance: models.SquadAppearance,
    best_position: str = "",
) -> List[str]:
    strict_positions = eligible_position_codes(
        squad_appearance,
        allow_tbc_any=False,
    )
    known_positions = [position for position in strict_positions if position != "TBC"]
    best_position_code = to_game_position_code(best_position)
    if best_position_code and best_position_code != "TBC":
        known_positions.append(best_position_code)
    return expand_position_codes(known_positions)


def is_tbc_squad_appearance(
    squad_appearance: models.SquadAppearance,
    best_position: str = "",
) -> bool:
    strict_positions = auto_select_known_position_codes(
        squad_appearance,
        best_position,
    )
    return not strict_positions or strict_positions == ["TBC"]


def draft_open_positions(draft_session: models.DraftSession) -> List[str]:
    selected_positions = [
        to_game_position_code(pick.selected_position)
        for pick in draft_session.picks
    ]
    return open_positions_from_selected_positions(selected_positions)


def open_positions_from_selected_positions(selected_positions: List[str]) -> List[str]:
    remaining = list(DRAFT_POSITION_SLOTS)
    for position in selected_positions:
        if position in remaining:
            remaining.remove(position)
    return remaining


def storage_position_for_draft_slot(game_position: str, slot_number: int) -> str:
    if to_game_position_code(game_position) == "WG":
        return "RW" if slot_number == 14 else "LW"
    return normalize_position_code(game_position)


def auto_select_debug_enabled() -> bool:
    return (
        os.getenv("RUGBY_AUTO_SELECT_DEBUG") == "1"
        or os.getenv("APP_ENV") == "development"
    )


def log_auto_select_validation(
    slot_number: int,
    required_position: str,
    spin_pool: models.SpinPool,
    selected_position: str,
    passed: bool,
) -> None:
    if not auto_select_debug_enabled():
        return
    logger.info(
        "Auto-Select Validation | Slot: %s | Required Position: %s | "
        "Player: %s | Eligible: %s | %s",
        slot_number,
        required_position,
        spin_pool.squad_appearance.player.display_name,
        ", ".join(eligible_position_codes(spin_pool.squad_appearance)),
        "PASS" if passed else "FAIL",
    )


def log_auto_select_filter_audit(
    spin_pool: models.SpinPool,
    year_min: Optional[int],
    year_max: Optional[int],
    requested_countries: set[str],
    passed: bool,
) -> None:
    if not auto_select_debug_enabled():
        return
    era = f"{year_min or 'any'}-{year_max or 'any'}"
    region = "filtered" if requested_countries else "all"
    logger.info(
        "Auto-Select Filter Audit | Player: %s | Country: %s | Year: %s | "
        "Era: %s | Region: %s | %s",
        spin_pool.squad_appearance.player.display_name,
        spin_pool.country.name,
        spin_pool.tournament.year,
        era,
        region,
        "PASS" if passed else "FAIL",
    )


def validate_auto_select_filters(
    selected: list[tuple[int, str, models.SpinPool]],
    year_min: Optional[int],
    year_max: Optional[int],
    requested_countries: set[str],
) -> bool:
    passed_all = True
    for _slot_number, _selected_position, spin_pool in selected:
        passed = True
        if year_min is not None and spin_pool.tournament.year < year_min:
            passed = False
        if year_max is not None and spin_pool.tournament.year > year_max:
            passed = False
        if requested_countries and not country_matches(
            spin_pool.country,
            requested_countries,
        ):
            passed = False
        log_auto_select_filter_audit(
            spin_pool=spin_pool,
            year_min=year_min,
            year_max=year_max,
            requested_countries=requested_countries,
            passed=passed,
        )
        if not passed:
            passed_all = False
    return passed_all


def build_auto_selected_xv(
    db: Session,
    candidates: List[models.SpinPool],
    target_high: int,
    target_low: int,
    rating_by_spin_pool_id: Optional[dict[int, float]] = None,
    best_position_by_spin_pool_id: Optional[dict[int, str]] = None,
) -> Optional[list[tuple[int, str, models.SpinPool]]]:
    if rating_by_spin_pool_id is None:
        rating_by_spin_pool_id = spin_pool_rating_map(db, candidates)
    if best_position_by_spin_pool_id is None:
        best_position_by_spin_pool_id = spin_pool_best_position_map(db, candidates)
    for _attempt in range(100):
        shuffled_candidates = candidates.copy()
        random.shuffle(shuffled_candidates)
        selected = backtrack_auto_select(
            candidates=shuffled_candidates,
            selected=[],
            used_squad_appearance_ids=set(),
            target_high=target_high,
            target_low=target_low,
            rating_by_spin_pool_id=rating_by_spin_pool_id,
            best_position_by_spin_pool_id=best_position_by_spin_pool_id,
        )
        if selected and validate_auto_selected_xv(
            selected,
            best_position_by_spin_pool_id,
        ):
            return selected
    return None


def backtrack_auto_select(
    candidates: List[models.SpinPool],
    selected: list[tuple[int, str, models.SpinPool]],
    used_squad_appearance_ids: set[int],
    target_high: int,
    target_low: int,
    rating_by_spin_pool_id: dict[int, float],
    best_position_by_spin_pool_id: dict[int, str],
) -> Optional[list[tuple[int, str, models.SpinPool]]]:
    if len(selected) == len(DRAFT_POSITION_SLOTS):
        return selected

    slot_number = len(selected) + 1
    required_position = DRAFT_POSITION_SLOTS[slot_number - 1]
    selected_position = storage_position_for_draft_slot(
        required_position,
        slot_number,
    )
    open_positions = open_positions_from_selected_positions(
        [to_game_position_code(position) for _, position, _ in selected],
    )
    high_rated = sum(
        1
        for _, _, spin_pool in selected
        if rating_by_spin_pool_id.get(spin_pool.id, 80) >= 90
    )
    below_ninety = len(selected) - high_rated

    slot_candidates = [
        candidate
        for candidate in candidates
        if candidate.squad_appearance_id not in used_squad_appearance_ids
        and can_select_position_for_open_positions(
            selected_position,
            candidate.squad_appearance,
            open_positions,
        )
    ]
    if not slot_candidates:
        return None

    known_position_candidates = [
        candidate
        for candidate in slot_candidates
        if can_auto_select_known_position_for_open_positions(
            selected_position,
            candidate.squad_appearance,
            open_positions,
            best_position_by_spin_pool_id.get(candidate.id, ""),
        )
    ]
    fallback_tbc_candidates = [
        candidate
        for candidate in slot_candidates
        if candidate not in known_position_candidates
        and is_tbc_squad_appearance(
            candidate.squad_appearance,
            best_position_by_spin_pool_id.get(candidate.id, ""),
        )
    ]

    candidate_groups = (
        (known_position_candidates, 300),
        (fallback_tbc_candidates, 80),
    )
    for candidate_group, candidate_limit in candidate_groups:
        result = try_auto_select_candidates_for_slot(
            candidates=candidates,
            slot_candidates=candidate_group,
            selected=selected,
            used_squad_appearance_ids=used_squad_appearance_ids,
            slot_number=slot_number,
            selected_position=selected_position,
            high_rated=high_rated,
            below_ninety=below_ninety,
            target_high=target_high,
            target_low=target_low,
            rating_by_spin_pool_id=rating_by_spin_pool_id,
            best_position_by_spin_pool_id=best_position_by_spin_pool_id,
            candidate_limit=candidate_limit,
        )
        if result is not None:
            return result
    return None


def try_auto_select_candidates_for_slot(
    candidates: List[models.SpinPool],
    slot_candidates: List[models.SpinPool],
    selected: list[tuple[int, str, models.SpinPool]],
    used_squad_appearance_ids: set[int],
    slot_number: int,
    selected_position: str,
    high_rated: int,
    below_ninety: int,
    target_high: int,
    target_low: int,
    rating_by_spin_pool_id: dict[int, float],
    best_position_by_spin_pool_id: dict[int, str],
    candidate_limit: int,
) -> Optional[list[tuple[int, str, models.SpinPool]]]:
    if not slot_candidates:
        return None

    random.shuffle(slot_candidates)
    slot_candidates.sort(
        key=lambda candidate: auto_select_candidate_score(
            candidate,
            high_rated,
            below_ninety,
            target_high,
            target_low,
            rating_by_spin_pool_id,
        ),
        reverse=True,
    )

    for candidate in slot_candidates[:candidate_limit]:
        next_selected = [
            *selected,
            (slot_number, selected_position, candidate),
        ]
        result = backtrack_auto_select(
            candidates=candidates,
            selected=next_selected,
            used_squad_appearance_ids={
                *used_squad_appearance_ids,
                candidate.squad_appearance_id,
            },
            target_high=target_high,
            target_low=target_low,
            rating_by_spin_pool_id=rating_by_spin_pool_id,
            best_position_by_spin_pool_id=best_position_by_spin_pool_id,
        )
        if result is not None:
            return result
    return None


def auto_select_candidate_score(
    candidate: models.SpinPool,
    high_rated: int,
    below_ninety: int,
    target_high: int,
    target_low: int,
    rating_by_spin_pool_id: dict[int, float],
) -> float:
    rating = rating_by_spin_pool_id.get(candidate.id, 80)
    if high_rated < target_high and rating >= 90:
        return rating + 1000
    if below_ninety < target_low and rating < 90:
        return rating + 900
    return rating + random.random()


def auto_select_tbc_usage(
    selected: list[tuple[int, str, models.SpinPool]],
    best_position_by_spin_pool_id: dict[int, str],
) -> tuple[int, int, int]:
    tbc_players_used = 0
    tbc_players_used_as_fallback = 0
    known_position_players_used = 0

    for _slot_number, selected_position, spin_pool in selected:
        squad_appearance = spin_pool.squad_appearance
        best_position = best_position_by_spin_pool_id.get(spin_pool.id, "")
        if is_tbc_squad_appearance(squad_appearance, best_position):
            tbc_players_used += 1
            tbc_players_used_as_fallback += 1
            continue

        if can_auto_select_known_position_for_open_positions(
            selected_position,
            squad_appearance,
            PLAYABLE_POSITION_CODES,
            best_position,
        ):
            known_position_players_used += 1

    return (
        tbc_players_used,
        tbc_players_used_as_fallback,
        known_position_players_used,
    )


def validate_auto_selected_xv(
    selected: list[tuple[int, str, models.SpinPool]],
    best_position_by_spin_pool_id: Optional[dict[int, str]] = None,
) -> bool:
    if best_position_by_spin_pool_id is None:
        best_position_by_spin_pool_id = {}
    if len(selected) != len(DRAFT_POSITION_SLOTS):
        return False
    if len({spin_pool.squad_appearance_id for _, _, spin_pool in selected}) != 15:
        return False

    selected_positions: list[str] = []
    for slot_number, selected_position, spin_pool in selected:
        required_position = DRAFT_POSITION_SLOTS[slot_number - 1]
        open_positions = open_positions_from_selected_positions(selected_positions)
        passed = (
            to_game_position_code(selected_position)
            == to_game_position_code(required_position)
            and can_select_position_for_open_positions(
                selected_position,
                spin_pool.squad_appearance,
                open_positions,
            )
        )
        log_auto_select_validation(
            slot_number=slot_number,
            required_position=required_position,
            spin_pool=spin_pool,
            selected_position=selected_position,
            passed=passed,
        )
        if not passed:
            return False
        selected_positions.append(to_game_position_code(selected_position))
    return True


@router.get("/countries", response_model=List[schemas.CountryResponse])
def list_countries(db: Session = Depends(get_db)):
    return db.scalars(select(models.Country).order_by(models.Country.name)).all()


@router.get("/tournaments", response_model=List[schemas.TournamentResponse])
def list_tournaments(db: Session = Depends(get_db)):
    return db.scalars(select(models.Tournament).order_by(models.Tournament.year)).all()


@router.get("/positions", response_model=List[schemas.PositionResponse])
def list_positions(db: Session = Depends(get_db)):
    return db.scalars(select(models.Position).order_by(models.Position.sort_order)).all()


@router.get("/players", response_model=List[schemas.PlayerResponse])
def list_players(db: Session = Depends(get_db)):
    return db.scalars(select(models.Player).order_by(models.Player.display_name)).all()


@router.get(
    "/squad-appearances",
    response_model=List[schemas.SquadAppearanceResponse],
)
def list_squad_appearances(db: Session = Depends(get_db)):
    return db.scalars(
        select(models.SquadAppearance).order_by(models.SquadAppearance.id),
    ).all()


@router.post("/draft-sessions", response_model=schemas.DraftSessionResponse)
def create_draft_session(db: Session = Depends(get_db)):
    draft_session = models.DraftSession()
    db.add(draft_session)
    db.commit()
    return get_draft_session_or_404(db, draft_session.id)


@router.get(
    "/draft-sessions/{session_id}",
    response_model=schemas.DraftSessionResponse,
)
def get_draft_session(session_id: int, db: Session = Depends(get_db)):
    return get_draft_session_or_404(db, session_id)


@router.get(
    "/draft-sessions/{session_id}/rating",
    response_model=schemas.DraftSessionRatingResponse,
)
def get_draft_session_rating(session_id: int, db: Session = Depends(get_db)):
    draft_session = get_draft_session_or_404(db, session_id)
    return calculate_draft_session_rating(draft_session)


@router.post(
    "/draft-sessions/{session_id}/simulate",
    response_model=schemas.SeasonSimulationResponse,
)
def simulate_draft_session(session_id: int, db: Session = Depends(get_db)):
    draft_session = get_draft_session_or_404(db, session_id)
    rating = calculate_draft_session_rating(draft_session)
    return simulate_season(float(rating["overall_rating"]))


@router.post(
    "/draft-sessions/{session_id}/picks",
    response_model=schemas.DraftSessionResponse,
)
def create_draft_pick(
    session_id: int,
    payload: schemas.DraftPickCreate,
    db: Session = Depends(get_db),
):
    draft_session = get_draft_session_or_404(db, session_id)

    if draft_session.status == "completed":
        raise HTTPException(status_code=400, detail="Draft session is completed.")

    if len(draft_session.picks) >= draft_session.max_picks:
        draft_session.status = "completed"
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Cannot pick more than 15 players.",
        )

    squad_appearance = db.get(
        models.SquadAppearance,
        payload.squad_appearance_id,
    )
    if squad_appearance is None:
        raise HTTPException(status_code=404, detail="Squad appearance not found.")

    already_picked = any(
        pick.squad_appearance_id == payload.squad_appearance_id
        for pick in draft_session.picks
    )
    if already_picked:
        raise HTTPException(
            status_code=400,
            detail="This squad appearance has already been picked in this session.",
        )

    selected_position = validate_selected_position(
        payload.selected_position,
        squad_appearance,
        draft_session,
    )
    pick_number = len(draft_session.picks) + 1

    db.add(
        models.DraftPick(
            draft_session=draft_session,
            pick_number=pick_number,
            player=squad_appearance.player,
            squad_appearance=squad_appearance,
            selected_position=selected_position,
        ),
    )

    next_pick_number = pick_number + 1
    draft_session.current_pick_number = min(
        next_pick_number,
        draft_session.max_picks,
    )
    if pick_number >= draft_session.max_picks:
        draft_session.status = "completed"

    return refresh_draft_session(db, draft_session)


@router.post(
    "/draft-sessions/{session_id}/auto-select",
    response_model=schemas.DraftAutoSelectResponse,
)
def auto_select_draft_session(
    session_id: int,
    payload: schemas.DraftAutoSelectCreate,
    db: Session = Depends(get_db),
):
    draft_session = get_draft_session_or_404(db, session_id)
    if draft_session.picks:
        raise HTTPException(
            status_code=400,
            detail="Auto-select requires an empty draft session.",
        )

    requested_countries = parse_requested_countries(payload.countries)
    candidates = db.scalars(
        select(models.SpinPool)
        .join(models.SpinPool.country)
        .join(models.SpinPool.tournament)
        .join(models.SpinPool.squad_appearance)
        .options(
            selectinload(models.SpinPool.country),
            selectinload(models.SpinPool.tournament),
            selectinload(models.SpinPool.squad_appearance)
            .selectinload(models.SquadAppearance.player),
            selectinload(models.SpinPool.squad_appearance)
            .selectinload(models.SquadAppearance.position),
        )
        .where(models.SpinPool.is_active.is_(True))
        .order_by(models.SpinPool.id),
    ).all()

    if payload.year_min is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.tournament.year >= payload.year_min
        ]
    if payload.year_max is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.tournament.year <= payload.year_max
        ]
    if requested_countries:
        candidates = [
            candidate
            for candidate in candidates
            if country_matches(candidate.country, requested_countries)
        ]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No players found for the selected draft setup.",
        )

    rating_by_spin_pool_id = spin_pool_rating_map(db, candidates)
    best_position_by_spin_pool_id = spin_pool_best_position_map(db, candidates)
    warnings: list[str] = []
    available_high = {
        candidate.squad_appearance_id
        for candidate in candidates
        if rating_by_spin_pool_id.get(candidate.id, 80) >= 90
    }
    available_low = {
        candidate.squad_appearance_id
        for candidate in candidates
        if rating_by_spin_pool_id.get(candidate.id, 80) < 90
    }
    target_high = min(4, len(available_high))
    target_low = min(5, len(available_low))
    if target_high < 4:
        warnings.append("Fewer than 4 players rated 90+ were available.")
    if target_low < 5:
        warnings.append("Fewer than 5 players rated below 90 were available.")

    selected = None
    for _attempt in range(5):
        possible_selection = build_auto_selected_xv(
            db=db,
            candidates=candidates,
            target_high=target_high,
            target_low=target_low,
            rating_by_spin_pool_id=rating_by_spin_pool_id,
            best_position_by_spin_pool_id=best_position_by_spin_pool_id,
        )
        if possible_selection is None:
            break
        if validate_auto_select_filters(
            possible_selection,
            payload.year_min,
            payload.year_max,
            requested_countries,
        ):
            selected = possible_selection
            break
    if selected is None:
        raise HTTPException(
            status_code=404,
            detail="Unable to auto-select a valid XV for the selected filters.",
        )
    rating_values = [
        rating_by_spin_pool_id.get(spin_pool.id, 80)
        for _, _, spin_pool in selected
    ]
    high_rated = sum(1 for rating in rating_values if rating >= 90)
    below_ninety = len(rating_values) - high_rated
    (
        tbc_players_used,
        tbc_players_used_as_fallback,
        known_position_players_used,
    ) = auto_select_tbc_usage(selected, best_position_by_spin_pool_id)
    if tbc_players_used_as_fallback:
        warnings.append(
            f"Auto-select used {tbc_players_used_as_fallback} TBC player(s) "
            "as fallback because known-position candidates could not complete "
            "the XV.",
        )

    for pick_number, (slot_number, selected_position, chosen) in enumerate(
        selected,
        start=1,
    ):
        db.add(
            models.DraftPick(
                draft_session=draft_session,
                pick_number=pick_number,
                player=chosen.squad_appearance.player,
                squad_appearance=chosen.squad_appearance,
                selected_position=selected_position,
            ),
        )

    draft_session.current_pick_number = draft_session.max_picks
    draft_session.status = "completed"
    db.commit()
    refreshed = get_draft_session_or_404(db, draft_session.id)
    rating = calculate_draft_session_rating(refreshed)

    return schemas.DraftAutoSelectResponse(
        draft_session=refreshed,
        rating=rating,
        picks=[
            schemas.AutoSelectedPick(
                pick_number=pick_number,
                slot_number=slot_number,
                selected_position=selected_position,
                player_id=spin_pool.squad_appearance.player_id,
                squad_appearance_id=spin_pool.squad_appearance_id,
                player_name=spin_pool.squad_appearance.player.display_name,
                country=spin_pool.country.name,
                year=spin_pool.tournament.year,
                position=primary_position_code(spin_pool.squad_appearance),
                eligible_positions=eligible_position_codes(
                    spin_pool.squad_appearance,
                ),
                rating=rating_for_squad_appearance(
                    db,
                    spin_pool.squad_appearance,
                ),
            )
            for pick_number, (slot_number, selected_position, spin_pool)
            in enumerate(selected, start=1)
        ],
        high_rated_count=high_rated,
        below_90_count=below_ninety,
        average_rating=(
            sum(rating_values) / len(rating_values)
            if rating_values
            else 0
        ),
        tbc_players_used=tbc_players_used,
        tbc_players_used_as_fallback=tbc_players_used_as_fallback,
        known_position_players_used=known_position_players_used,
        warnings=warnings,
    )


@router.get("/spin", response_model=schemas.SpinResult)
def spin(
    year_min: Optional[int] = Query(default=None),
    year_max: Optional[int] = Query(default=None),
    country: Optional[str] = Query(default=None),
    position: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    spin_pools = db.scalars(
        select(models.SpinPool)
        .join(models.SpinPool.country)
        .join(models.SpinPool.tournament)
        .join(models.SpinPool.squad_appearance)
        .where(models.SpinPool.is_active.is_(True))
        .order_by(models.SpinPool.id),
    ).all()

    if year_min is not None:
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if spin_pool.tournament.year >= year_min
        ]
    if year_max is not None:
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if spin_pool.tournament.year <= year_max
        ]
    if country is not None:
        requested_country = country.strip().lower()
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if requested_country
            in {spin_pool.country.name.lower(), spin_pool.country.code.lower()}
        ]
    if position is not None:
        requested_position = to_game_position_code(position)
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if requested_position
            in eligible_position_codes(spin_pool.squad_appearance)
        ]

    if not spin_pools:
        raise HTTPException(
            status_code=404,
            detail="No matching players found for the requested spin filters.",
        )

    spin_pool = random.choice(spin_pools)
    squad_appearance = spin_pool.squad_appearance

    return schemas.SpinResult(
        spin_pool_id=spin_pool.id,
        squad_appearance_id=squad_appearance.id,
        player_name=squad_appearance.player.display_name,
        country=spin_pool.country.name,
        year=spin_pool.tournament.year,
        tournament=spin_pool.tournament.name,
        position=primary_position_code(squad_appearance),
        eligible_positions=eligible_position_codes(squad_appearance),
        rating=rating_for_squad_appearance(db, squad_appearance),
    )


@router.get("/spin-squad", response_model=schemas.SpinSquadResult)
def spin_squad(
    year_min: Optional[int] = Query(default=None),
    year_max: Optional[int] = Query(default=None),
    country: Optional[str] = Query(default=None),
    countries: Optional[str] = Query(default=None),
    needed_positions: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    spin_pools = db.scalars(
        select(models.SpinPool)
        .join(models.SpinPool.country)
        .join(models.SpinPool.tournament)
        .join(models.SpinPool.squad_appearance)
        .where(models.SpinPool.is_active.is_(True))
        .order_by(models.SpinPool.id),
    ).all()

    if year_min is not None:
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if spin_pool.tournament.year >= year_min
        ]
    if year_max is not None:
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if spin_pool.tournament.year <= year_max
        ]
    if country is not None:
        requested_country = country.strip().lower()
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if requested_country
            in {spin_pool.country.name.lower(), spin_pool.country.code.lower()}
        ]
    requested_countries = parse_requested_countries(countries)
    if requested_countries:
        spin_pools = [
            spin_pool
            for spin_pool in spin_pools
            if country_matches(spin_pool.country, requested_countries)
        ]

    requested_needed_positions = set(parse_needed_positions(needed_positions))
    squad_keys = sorted(
        {
            (spin_pool.country_id, spin_pool.tournament_id)
            for spin_pool in spin_pools
            if not requested_needed_positions
            or requested_needed_positions.intersection(
                eligible_position_codes(spin_pool.squad_appearance),
            )
        },
    )
    if not squad_keys:
        raise HTTPException(
            status_code=404,
            detail=(
                "No available squads can fill your remaining positions for "
                "this era."
            )
            if requested_needed_positions
            else "No matching squads found for the requested spin filters.",
        )

    country_id, tournament_id = random.choice(squad_keys)
    squad_spin_pools = [
        spin_pool
        for spin_pool in spin_pools
        if spin_pool.country_id == country_id
        and spin_pool.tournament_id == tournament_id
    ]
    squad_spin_pools.sort(key=lambda spin_pool: spin_pool.squad_appearance.player.display_name)

    first_spin_pool = squad_spin_pools[0]
    return schemas.SpinSquadResult(
        country=first_spin_pool.country.name,
        year=first_spin_pool.tournament.year,
        tournament_id=first_spin_pool.tournament_id,
        squad=[
            schemas.SpinSquadPlayer(
                player_id=spin_pool.squad_appearance.player_id,
                squad_appearance_id=spin_pool.squad_appearance_id,
                player_name=spin_pool.squad_appearance.player.display_name,
                position=primary_position_code(spin_pool.squad_appearance),
                eligible_positions=eligible_position_codes(
                    spin_pool.squad_appearance,
                ),
                rating=rating_for_squad_appearance(
                    db,
                    spin_pool.squad_appearance,
                ),
            )
            for spin_pool in squad_spin_pools
        ],
    )


@router.get("/admin/players", response_model=List[schemas.AdminPlayerDetail])
def admin_list_players(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    players = db.scalars(
        select(models.Player)
        .options(
            selectinload(models.Player.country),
            selectinload(models.Player.primary_position),
            selectinload(models.Player.aliases),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.country),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.tournament),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.position),
        )
        .order_by(models.Player.display_name)
        .offset(offset)
        .limit(limit),
    ).all()
    return [admin_player_detail(player) for player in players]


@router.get("/admin/players/search", response_model=List[schemas.AdminPlayerDetail])
def admin_search_players(
    query: str = Query(min_length=1),
    db: Session = Depends(get_db),
):
    requested = f"%{query.strip()}%"
    players = db.scalars(
        select(models.Player)
        .options(
            selectinload(models.Player.country),
            selectinload(models.Player.primary_position),
            selectinload(models.Player.aliases),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.country),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.tournament),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.position),
        )
        .where(models.Player.display_name.ilike(requested))
        .order_by(models.Player.display_name)
        .limit(100),
    ).all()
    return [admin_player_detail(player) for player in players]


@router.get("/admin/players/{player_id}", response_model=schemas.AdminPlayerDetail)
def admin_get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.scalar(
        select(models.Player)
        .options(
            selectinload(models.Player.country),
            selectinload(models.Player.primary_position),
            selectinload(models.Player.aliases),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.country),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.tournament),
            selectinload(models.Player.squad_appearances)
            .selectinload(models.SquadAppearance.position),
        )
        .where(models.Player.id == player_id),
    )
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")
    return admin_player_detail(player)


@router.patch("/admin/players/{player_id}", response_model=schemas.AdminPlayerDetail)
def admin_update_player(
    player_id: int,
    payload: schemas.AdminPlayerUpdate,
    db: Session = Depends(get_db),
):
    player = db.get(models.Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(player, field, value)
    db.commit()
    return admin_get_player(player_id, db)


@router.get("/admin/duplicates")
def admin_duplicates(db: Session = Depends(get_db)):
    return detect_duplicates(db)


@router.get("/admin/ratings", response_model=List[schemas.RatingResponse])
def admin_list_ratings(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(models.Rating)
        .order_by(models.Rating.id)
        .offset(offset)
        .limit(limit),
    ).all()


@router.post(
    "/admin/ratings/generate",
    response_model=schemas.GeneratedRatingsReport,
)
def admin_generate_ratings(
    overwrite_generated_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return generate_baseline_ratings(
        db,
        overwrite_generated_only=overwrite_generated_only,
    )


@router.get("/admin/rating-summary", response_model=schemas.RatingSummary)
def admin_rating_summary(db: Session = Depends(get_db)):
    return build_rating_summary(db)


@router.get("/admin/ratings/{player_id}", response_model=List[schemas.RatingResponse])
def admin_get_player_ratings(player_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(models.Rating)
        .where(models.Rating.player_id == player_id)
        .order_by(models.Rating.id),
    ).all()


@router.patch("/admin/ratings/{rating_id}", response_model=schemas.RatingResponse)
def admin_update_rating(
    rating_id: int,
    payload: schemas.RatingUpdate,
    db: Session = Depends(get_db),
):
    rating = db.get(models.Rating, rating_id)
    if rating is None:
        raise HTTPException(status_code=404, detail="Rating not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rating, field, value)
    db.commit()
    db.refresh(rating)
    return rating


@router.get(
    "/admin/data-quality-summary",
    response_model=schemas.DataQualitySummary,
)
def admin_data_quality_summary(db: Session = Depends(get_db)):
    tbc_position = db.scalar(
        select(models.Position).where(models.Position.code == "TBC"),
    )
    tbc_count = 0
    if tbc_position is not None:
        tbc_count = int(
            db.scalar(
                select(func.count(models.SquadAppearance.id)).where(
                    models.SquadAppearance.position_id == tbc_position.id,
                ),
            )
            or 0
        )
    duplicate_report = detect_duplicates(db)
    return schemas.DataQualitySummary(
        players=int(db.scalar(select(func.count(models.Player.id))) or 0),
        squad_appearances=int(
            db.scalar(select(func.count(models.SquadAppearance.id))) or 0,
        ),
        spin_pool_records=int(db.scalar(select(func.count(models.SpinPool.id))) or 0),
        ratings=int(db.scalar(select(func.count(models.Rating.id))) or 0),
        player_aliases=int(db.scalar(select(func.count(models.PlayerAlias.id))) or 0),
        tbc_positions=tbc_count,
        duplicate_same_country=len(
            duplicate_report["same_normalised_name_same_country"],
        ),
        duplicate_cross_country=len(
            duplicate_report["same_normalised_name_different_countries"],
        ),
    )
