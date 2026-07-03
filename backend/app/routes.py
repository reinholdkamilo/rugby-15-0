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
    position_codes: List[str] = []
    if squad_appearance.position is not None:
        position_codes.append(squad_appearance.position.code)

    for code in secondary_positions_from_notes(squad_appearance.notes):
        if code not in position_codes:
            position_codes.append(code)

    if allow_tbc_any:
        return expand_position_codes_for_draft(position_codes)
    return expand_position_codes(position_codes)


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

    if normalized_game_position not in draft_open_positions(draft_session):
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


def draft_open_positions(draft_session: models.DraftSession) -> List[str]:
    remaining = list(DRAFT_POSITION_SLOTS)
    selected_positions = [to_game_position_code(pick.selected_position) for pick in draft_session.picks]
    for position in selected_positions:
        if position in remaining:
            remaining.remove(position)
    return remaining


def storage_position_for_draft_slot(game_position: str, slot_number: int) -> str:
    if to_game_position_code(game_position) == "WG":
        return "RW" if slot_number == 14 else "LW"
    return normalize_position_code(game_position)


def spin_pool_can_fill_slot(
    spin_pool: models.SpinPool,
    game_position: str,
) -> bool:
    return to_game_position_code(game_position) in eligible_position_codes(
        spin_pool.squad_appearance,
    )


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

    used_squad_appearance_ids: set[int] = set()
    high_rated = 0
    below_ninety = 0
    rating_values: list[float] = []
    warnings: list[str] = []
    selected: list[tuple[int, str, models.SpinPool]] = []
    available_high = {
        candidate.squad_appearance_id
        for candidate in candidates
        if spin_pool_rating(db, candidate) >= 90
    }
    available_low = {
        candidate.squad_appearance_id
        for candidate in candidates
        if spin_pool_rating(db, candidate) < 90
    }
    target_high = min(4, len(available_high))
    target_low = min(5, len(available_low))
    if target_high < 4:
        warnings.append("Fewer than 4 players rated 90+ were available.")
    if target_low < 5:
        warnings.append("Fewer than 5 players rated below 90 were available.")

    for slot_number, game_position in enumerate(DRAFT_POSITION_SLOTS, start=1):
        slot_candidates = [
            candidate
            for candidate in candidates
            if candidate.squad_appearance_id not in used_squad_appearance_ids
            and spin_pool_can_fill_slot(candidate, game_position)
        ]
        if not slot_candidates:
            raise HTTPException(
                status_code=404,
                detail=f"No eligible players available for {game_position}.",
            )

        preferred = slot_candidates
        if high_rated < target_high:
            high_candidates = [
                candidate
                for candidate in slot_candidates
                if spin_pool_rating(db, candidate) >= 90
            ]
            if high_candidates:
                preferred = high_candidates
        elif below_ninety < target_low:
            lower_candidates = [
                candidate
                for candidate in slot_candidates
                if spin_pool_rating(db, candidate) < 90
            ]
            if lower_candidates:
                preferred = lower_candidates

        random.shuffle(preferred)
        preferred.sort(
            key=lambda candidate: spin_pool_rating(db, candidate),
            reverse=True,
        )
        top_window = preferred[: min(18, len(preferred))]
        chosen = random.choice(top_window[: max(4, len(top_window) // 2)])
        rating = spin_pool_rating(db, chosen)
        if rating >= 90:
            high_rated += 1
        else:
            below_ninety += 1
        rating_values.append(rating)
        used_squad_appearance_ids.add(chosen.squad_appearance_id)
        selected_position = storage_position_for_draft_slot(
            game_position,
            slot_number,
        )
        if to_game_position_code(selected_position) != to_game_position_code(game_position):
            raise HTTPException(
                status_code=500,
                detail="Auto-select generated a mismatched position.",
            )
        selected.append((slot_number, selected_position, chosen))

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
