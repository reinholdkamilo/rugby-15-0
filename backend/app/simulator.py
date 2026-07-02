from __future__ import annotations

import random
from dataclasses import dataclass

WIN_PROBABILITY_BASE = 0.50
WIN_PROBABILITY_PER_RATING_POINT = 0.03
WIN_PROBABILITY_MIN = 0.10
WIN_PROBABILITY_MAX = 0.90

OPPONENTS = [
    ("New Zealand", 94.0),
    ("South Africa", 93.0),
    ("Australia", 88.0),
    ("England", 89.0),
    ("France", 91.0),
    ("Ireland", 92.0),
    ("Wales", 85.0),
    ("Scotland", 84.0),
    ("Argentina", 86.0),
    ("Fiji", 83.0),
    ("Japan", 82.0),
    ("Italy", 80.0),
    ("Samoa", 79.0),
    ("Tonga", 78.0),
    ("Barbarians", 87.0),
]


@dataclass
class MatchSimulation:
    match_number: int
    opponent_name: str
    opponent_rating: float
    win_probability: float
    result: str
    points_for: int
    points_against: int
    margin: int


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def win_probability(team_rating: float, opponent_rating: float) -> float:
    rating_diff = team_rating - opponent_rating
    probability = (
        WIN_PROBABILITY_BASE + rating_diff * WIN_PROBABILITY_PER_RATING_POINT
    )
    return round(
        clamp(probability, WIN_PROBABILITY_MIN, WIN_PROBABILITY_MAX),
        2,
    )


def simulate_score(
    team_rating: float,
    opponent_rating: float,
    won: bool,
) -> tuple[int, int]:
    rating_edge = team_rating - opponent_rating
    expected_margin = rating_edge * 0.8
    margin = round(random.gauss(expected_margin, 9))

    if won:
        margin = max(1, abs(margin))
    else:
        margin = -max(1, abs(margin))

    total_points = max(24, round(random.gauss(48, 12)))
    points_for = max(0, round((total_points + margin) / 2))
    points_against = max(0, points_for - margin)

    return points_for, points_against


def simulate_match(
    match_number: int,
    opponent_name: str,
    opponent_rating: float,
    team_rating: float,
) -> MatchSimulation:
    probability = win_probability(team_rating, opponent_rating)
    won = random.random() < probability
    points_for, points_against = simulate_score(team_rating, opponent_rating, won)
    margin = points_for - points_against

    return MatchSimulation(
        match_number=match_number,
        opponent_name=opponent_name,
        opponent_rating=opponent_rating,
        win_probability=probability,
        result="W" if won else "L",
        points_for=points_for,
        points_against=points_against,
        margin=margin,
    )


def simulate_season(team_rating: float) -> dict[str, object]:
    matches = [
        simulate_match(
            match_number=match_number,
            opponent_name=opponent_name,
            opponent_rating=opponent_rating,
            team_rating=team_rating,
        )
        for match_number, (opponent_name, opponent_rating) in enumerate(
            OPPONENTS,
            start=1,
        )
    ]
    wins = sum(1 for match in matches if match.result == "W")
    losses = len(matches) - wins

    return {
        "wins": wins,
        "losses": losses,
        "undefeated": losses == 0,
        "team_rating": round(team_rating, 1),
        "matches": [match.__dict__ for match in matches],
    }
