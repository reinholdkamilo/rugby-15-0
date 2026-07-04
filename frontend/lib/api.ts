const DEFAULT_API_BASE_URL =
  process.env.NODE_ENV === "production"
    ? "https://rugby-15-0.onrender.com"
    : "http://127.0.0.1:8000";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;

const RETRYABLE_FETCH_ATTEMPTS = 3;
const RETRY_DELAY_MS = 800;

async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  fallbackMessage = "Request failed.",
  retryAttempts = 1,
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let lastError: unknown;

  for (let attempt = 1; attempt <= retryAttempts; attempt += 1) {
    try {
      console.info(`[api] ${options.method ?? "GET"} ${url}`);
      const response = await fetch(url, {
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
    } catch (caughtError) {
      lastError = caughtError;
      console.error(`[api] request failed: ${url}`, caughtError);
      if (attempt < retryAttempts) {
        await delay(RETRY_DELAY_MS);
      }
    }
  }

  if (lastError instanceof Error && retryAttempts === 1) {
    throw lastError;
  }

  throw new Error(fallbackMessage);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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
  countries?: string | string[];
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

export type AutoSelectedPick = {
  pick_number: number;
  slot_number: number;
  selected_position: string;
  player_id: number;
  squad_appearance_id: number;
  player_name: string;
  country: string;
  year: number;
  position: string | null;
  eligible_positions: string[];
  rating: number | null;
};

export type DraftAutoSelectResponse = {
  draft_session: DraftSession;
  rating: DraftSessionRating;
  picks: AutoSelectedPick[];
  high_rated_count: number;
  below_90_count: number;
  average_rating: number;
  tbc_players_used: number;
  tbc_players_used_as_fallback: number;
  known_position_players_used: number;
  warnings: string[];
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
    const cleanValue = Array.isArray(value)
      ? value
          .filter((item) => item !== undefined && item !== null && item !== "")
          .join(",")
      : String(value);
    if (!cleanValue) {
      return;
    }
    query.set(key, cleanValue);
  });
  const suffix = query.toString().replaceAll("%2C", ",");
  return suffix ? `?${suffix}` : "";
}

export function buildSpinSquadUrl(
  params: Omit<SpinParams, "position"> = {},
): string {
  return `${API_BASE_URL}/spin-squad${buildQueryString(params)}`;
}

export async function spinPlayer(params: SpinParams = {}): Promise<SpinResult> {
  const suffix = buildQueryString(params);
  return apiRequest<SpinResult>(`/spin${suffix}`, {}, "Unable to spin a player.");
}

export async function spinSquad(
  params: Omit<SpinParams, "position"> = {},
): Promise<SpinSquadResult> {
  const suffix = buildQueryString(params);
  const url = buildSpinSquadUrl(params);
  const startedAt = performance.now();
  console.info(`[spin-squad] request started: ${url}`);
  try {
    const result = await apiRequest<SpinSquadResult>(
      `/spin-squad${suffix}`,
      {},
      "Could not load squad. Please try again.",
      RETRYABLE_FETCH_ATTEMPTS,
    );
    console.info(
      `[spin-squad] response received: ${Math.round(performance.now() - startedAt)}ms`,
    );
    return result;
  } catch (error) {
    console.error(
      `[spin-squad] failed after ${Math.round(performance.now() - startedAt)}ms: ${url}`,
      error,
    );
    throw error;
  }
}

export async function warmupApi(): Promise<{ status: string; warmed: boolean }> {
  return apiRequest<{ status: string; warmed: boolean }>(
    "/warmup",
    {},
    "Warm-up failed.",
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

export async function autoSelectDraftSession(
  sessionId: number,
  payload: {
    year_min?: number;
    year_max?: number;
    countries?: string | string[];
    team_name?: string;
  },
): Promise<DraftAutoSelectResponse> {
  const countries = Array.isArray(payload.countries)
    ? payload.countries.join(",")
    : payload.countries;
  return apiRequest<DraftAutoSelectResponse>(
    `/draft-sessions/${sessionId}/auto-select`,
    {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        countries,
      }),
    },
    "Unable to auto-select a squad.",
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
