export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  fallbackMessage = "Request failed.",
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = fallbackMessage;

    try {
      const body = (await response.json()) as { detail?: string };
      message = body.detail ?? message;
    } catch {
      message = response.statusText || message;
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export type SpinResult = {
  spin_pool_id: number;
  squad_appearance_id: number;
  player_name: string;
  country: string;
  year: number;
  tournament: string;
  position: string | null;
  eligible_positions: string[];
  rating: number | null;
};

export type SpinParams = {
  year_min?: number;
  year_max?: number;
  country?: string;
  position?: string;
  needed_positions?: string | string[];
};

export type SpinSquadPlayer = {
  player_id: number;
  squad_appearance_id: number;
  player_name: string;
  position: string | null;
  eligible_positions: string[];
  rating: number | null;
};

export type SpinSquadResult = {
  country: string;
  year: number;
  tournament_id: number;
  squad: SpinSquadPlayer[];
};

export type DraftPick = {
  id: number;
  draft_session_id: number;
  pick_number: number;
  player_id: number;
  squad_appearance_id: number;
  selected_position: string;
  created_at: string;
};

export type DraftSession = {
  id: number;
  created_at: string;
  status: "active" | "completed";
  current_pick_number: number;
  max_picks: number;
  picks: DraftPick[];
};

export type DraftSessionRating = {
  overall_rating: number;
  pack_rating: number;
  backline_rating: number;
  spine_rating: number;
  set_piece_rating: number;
  breakdown_rating: number;
  attack_rating: number;
  defence_rating: number;
  goal_kicking_rating: number;
  missing_positions: string[];
  position_count: Record<string, number>;
  is_complete: boolean;
};

export type SimulatedMatch = {
  match_number: number;
  opponent_name: string;
  opponent_rating: number;
  win_probability: number;
  result: "W" | "L";
  points_for: number;
  points_against: number;
  margin: number;
};

export type SeasonSimulation = {
  wins: number;
  losses: number;
  undefeated: boolean;
  team_rating: number;
  matches: SimulatedMatch[];
};

function buildQueryString(params: SpinParams): string {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") {
      return;
    }
    query.set(key, Array.isArray(value) ? value.join(",") : String(value));
  });
  return query.toString() ? `?${query.toString()}` : "";
}

export async function spinPlayer(params: SpinParams = {}): Promise<SpinResult> {
  const suffix = buildQueryString(params);
  return apiRequest<SpinResult>(`/spin${suffix}`, {}, "Unable to spin a player.");
}

export async function spinSquad(
  params: Omit<SpinParams, "position"> = {},
): Promise<SpinSquadResult> {
  const suffix = buildQueryString(params);
  return apiRequest<SpinSquadResult>(
    `/spin-squad${suffix}`,
    {},
    "Unable to spin a squad.",
  );
}

export async function createDraftSession(): Promise<DraftSession> {
  return apiRequest<DraftSession>(
    "/draft-sessions",
    { method: "POST" },
    "Unable to start a draft.",
  );
}

export async function getDraftSession(sessionId: number): Promise<DraftSession> {
  return apiRequest<DraftSession>(
    `/draft-sessions/${sessionId}`,
    {},
    "Unable to load draft session.",
  );
}

export async function addDraftPick(
  sessionId: number,
  squadAppearanceId: number,
  selectedPosition: string,
): Promise<DraftSession> {
  return apiRequest<DraftSession>(
    `/draft-sessions/${sessionId}/picks`,
    {
      method: "POST",
      body: JSON.stringify({
        squad_appearance_id: squadAppearanceId,
        selected_position: selectedPosition,
      }),
    },
    "Unable to add player to squad.",
  );
}

export async function getDraftSessionRating(
  sessionId: number,
): Promise<DraftSessionRating> {
  return apiRequest<DraftSessionRating>(
    `/draft-sessions/${sessionId}/rating`,
    {},
    "Unable to load team rating.",
  );
}

export async function simulateDraftSession(
  sessionId: number,
): Promise<SeasonSimulation> {
  return apiRequest<SeasonSimulation>(
    `/draft-sessions/${sessionId}/simulate`,
    { method: "POST" },
    "Unable to simulate season.",
  );
}
