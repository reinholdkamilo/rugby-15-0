"use client";

import { useMemo, useState } from "react";

import {
  RugbyFieldLayout,
  type ActivePositionFilter,
  type FieldPick,
} from "@/components/RugbyFieldLayout";
import { SpinRevealAnimation } from "@/components/SpinRevealAnimation";
import {
  addDraftPick,
  buildSpinSquadUrl,
  createDraftSession,
  getDraftSessionRating,
  simulateDraftSession,
  spinSquad,
  type DraftSession,
  type DraftSessionRating,
  type SeasonSimulation,
  type SpinSquadPlayer,
  type SpinSquadResult,
} from "@/lib/api";
import {
  expandPositionEligibilityForDraft,
  isSameGamePosition,
  orderGamePositions,
  toGamePositionCode,
} from "@/lib/positionEligibility";

type SquadPlayer = {
  pickNumber: number;
  slotNumber: number;
  selectedPosition: string;
  player: SpinSquadPlayer;
  country: string;
  year: number;
};

type FieldSlot = {
  slotNumber: number;
  positionCode: string;
  displayCode: string;
  positionName: string;
};

const FIELD_SLOTS: FieldSlot[] = [
  { slotNumber: 1, positionCode: "LH", displayCode: "LH", positionName: "Loosehead Prop" },
  { slotNumber: 2, positionCode: "HK", displayCode: "HK", positionName: "Hooker" },
  { slotNumber: 3, positionCode: "TH", displayCode: "TH", positionName: "Tighthead Prop" },
  { slotNumber: 4, positionCode: "LK4", displayCode: "LK", positionName: "Lock" },
  { slotNumber: 5, positionCode: "LK5", displayCode: "LK", positionName: "Lock" },
  { slotNumber: 6, positionCode: "BSF", displayCode: "BF", positionName: "Blindside Flanker" },
  { slotNumber: 8, positionCode: "N8", displayCode: "NE", positionName: "Number 8" },
  { slotNumber: 7, positionCode: "OSF", displayCode: "OF", positionName: "Openside Flanker" },
  { slotNumber: 9, positionCode: "SH", displayCode: "SH", positionName: "Scrumhalf" },
  { slotNumber: 10, positionCode: "FH", displayCode: "FH", positionName: "Flyhalf" },
  { slotNumber: 11, positionCode: "LW", displayCode: "WG", positionName: "Left Wing" },
  { slotNumber: 12, positionCode: "IC", displayCode: "IC", positionName: "Inside Centre" },
  { slotNumber: 13, positionCode: "OC", displayCode: "OC", positionName: "Outside Centre" },
  { slotNumber: 14, positionCode: "RW", displayCode: "WG", positionName: "Right Wing" },
  { slotNumber: 15, positionCode: "FB", displayCode: "FB", positionName: "Fullback" },
];

const WORLD_CUP_YEARS = [
  1987,
  1991,
  1995,
  1999,
  2003,
  2007,
  2011,
  2015,
  2019,
  2023,
];

const YEAR_PRESETS = [
  { label: "All Time", yearMin: 1987, yearMax: 2023 },
  { label: "Professional Era", yearMin: 1995, yearMax: 2023 },
  { label: "Modern Era", yearMin: 2015, yearMax: 2023 },
  { label: "Early Era", yearMin: 1987, yearMax: 2003 },
];

const MIN_SPIN_REVEAL_MS = 1900;

function getFilledSlots(picks: SquadPlayer[]) {
  return new Set(picks.map((pick) => pick.slotNumber));
}

function isLockPosition(positionCode: string) {
  return toGamePositionCode(positionCode) === "LK";
}

function isPositionSlotFilled(picks: SquadPlayer[], slotNumber: number) {
  return getFilledSlots(picks).has(slotNumber);
}

function slotsForPosition(positionCode: string) {
  const gamePositionCode = toGamePositionCode(positionCode);
  return FIELD_SLOTS.filter((slot) =>
    toGamePositionCode(slot.positionCode) === gamePositionCode,
  );
}

function expandedEligiblePositions(player: SpinSquadPlayer) {
  return expandPositionEligibilityForDraft(player.eligible_positions);
}

function isTbcSpunPlayer(player: SpinSquadPlayer) {
  return (
    toGamePositionCode(player.position) === "TBC" ||
    player.eligible_positions.some(
      (position) => toGamePositionCode(position) === "TBC",
    )
  );
}

function isPlayerEligibleForFieldPosition(
  player: SpinSquadPlayer,
  positionCode: string,
) {
  return expandedEligiblePositions(player).includes(
    toGamePositionCode(positionCode),
  );
}

function isPlayerEligibleForSelectedPosition(
  player: SpinSquadPlayer,
  selectedPosition: string,
) {
  return isPlayerEligibleForFieldPosition(player, selectedPosition);
}

function selectedPositionMatchesSlot(selectedPosition: string, slot: FieldSlot) {
  return isSameGamePosition(selectedPosition, slot.positionCode);
}

function getAvailablePositionsForPlayer(
  player: SpinSquadPlayer,
  picks: SquadPlayer[],
) {
  const filledSlots = getFilledSlots(picks);
  return expandedEligiblePositions(player).filter((position) =>
    slotsForPosition(position).some((slot) => !filledSlots.has(slot.slotNumber)),
  );
}

function orderAvailablePositions(
  positions: string[],
  activePositionFilter: ActivePositionFilter,
) {
  if (!activePositionFilter) {
    return positions;
  }
  return [...positions].sort((left, right) => {
    const leftMatches = isLockPosition(activePositionFilter.positionCode)
      ? isLockPosition(left)
      : isSameGamePosition(left, activePositionFilter.positionCode);
    const rightMatches = isLockPosition(activePositionFilter.positionCode)
      ? isLockPosition(right)
      : isSameGamePosition(right, activePositionFilter.positionCode);
    if (leftMatches === rightMatches) {
      return 0;
    }
    return leftMatches ? -1 : 1;
  });
}

function getLockedPositionsForPlayer(
  player: SpinSquadPlayer,
  picks: SquadPlayer[],
) {
  const available = new Set(getAvailablePositionsForPlayer(player, picks));
  return expandedEligiblePositions(player).filter(
    (position) => !available.has(position),
  );
}

function isPlayerAlreadyPicked(player: SpinSquadPlayer, picks: SquadPlayer[]) {
  return picks.some(
    (pick) => pick.player.squad_appearance_id === player.squad_appearance_id,
  );
}

function isPlayerSelectable(
  player: SpinSquadPlayer,
  picks: SquadPlayer[],
  activePositionFilter: ActivePositionFilter,
) {
  if (isPlayerAlreadyPicked(player, picks)) {
    return false;
  }
  if (activePositionFilter) {
    if (isPositionSlotFilled(picks, activePositionFilter.slotNumber)) {
      return false;
    }
    return isPlayerEligibleForFieldPosition(
      player,
      activePositionFilter.positionCode,
    );
  }
  return getAvailablePositionsForPlayer(player, picks).length > 0;
}

function getSlotForPosition(
  selectedPosition: string,
  activePositionFilter: ActivePositionFilter,
  picks: SquadPlayer[],
) {
  const filledSlots = getFilledSlots(picks);
  if (activePositionFilter) {
    const activeSlot = FIELD_SLOTS.find(
      (slot) => slot.slotNumber === activePositionFilter.slotNumber,
    );
    if (
      activeSlot &&
      selectedPositionMatchesSlot(selectedPosition, activeSlot) &&
      !filledSlots.has(activeSlot.slotNumber)
    ) {
      return activeSlot.slotNumber;
    }
  }

  return (
    slotsForPosition(selectedPosition).find(
      (slot) => !filledSlots.has(slot.slotNumber),
    )?.slotNumber ?? null
  );
}

function sortPlayersByRating(players: SpinSquadPlayer[]) {
  return [...players].sort((left, right) => {
    if (left.rating === null && right.rating === null) {
      return left.player_name.localeCompare(right.player_name);
    }
    if (left.rating === null) {
      return 1;
    }
    if (right.rating === null) {
      return -1;
    }
    return right.rating - left.rating;
  });
}

function getRemainingNeededPositions(picks: SquadPlayer[]) {
  const filledSlots = getFilledSlots(picks);
  return orderGamePositions(
    FIELD_SLOTS.filter((slot) => !filledSlots.has(slot.slotNumber)).map((slot) =>
      toGamePositionCode(slot.positionCode),
    ),
  );
}

function backendPositionForSlot(selectedPosition: string, slotNumber: number) {
  const slot = FIELD_SLOTS.find((fieldSlot) => fieldSlot.slotNumber === slotNumber);
  if (slot && isSameGamePosition(selectedPosition, slot.positionCode)) {
    return isLockPosition(slot.positionCode) ? "LK" : slot.positionCode;
  }

  const gamePositionCode = toGamePositionCode(selectedPosition);
  if (gamePositionCode === "BF") {
    return "BSF";
  }
  if (gamePositionCode === "OF") {
    return "OSF";
  }
  if (gamePositionCode === "NE") {
    return "N8";
  }
  if (gamePositionCode === "WG") {
    return "LW";
  }
  return gamePositionCode;
}

function positionNameForCode(positionCode: string) {
  return (
    FIELD_SLOTS.find((slot) => slot.positionCode === positionCode)?.positionName ??
    positionCode
  );
}

function getMainActionLabel(
  draftSession: DraftSession | null,
  picksMade: number,
  loadingAction: string | null,
) {
  if (loadingAction === "start") {
    return "Starting...";
  }
  if (loadingAction === "spin") {
    return "Spinning...";
  }
  if (loadingAction === "simulate") {
    return "Starting World Cup...";
  }
  if (!draftSession) {
    return "Start Draft";
  }
  if (picksMade >= 15) {
    return "Start World Cup";
  }
  return "Spin";
}

export default function Home() {
  const [draftSession, setDraftSession] = useState<DraftSession | null>(null);
  const [spunSquad, setSpunSquad] = useState<SpinSquadResult | null>(null);
  const [spinRevealTarget, setSpinRevealTarget] = useState<{
    country: string;
    year: number;
  } | null>(null);
  const [spinRevealActive, setSpinRevealActive] = useState(false);
  const [lastSpinSquadUrl, setLastSpinSquadUrl] = useState<string | null>(null);
  const [expandedPlayerId, setExpandedPlayerId] = useState<number | null>(null);
  const [squad, setSquad] = useState<SquadPlayer[]>([]);
  const [rating, setRating] = useState<DraftSessionRating | null>(null);
  const [simulation, setSimulation] = useState<SeasonSimulation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [yearMin, setYearMin] = useState(1987);
  const [yearMax, setYearMax] = useState(2023);
  const [activePositionFilter, setActivePositionFilter] =
    useState<ActivePositionFilter>(null);

  const picksMade = draftSession?.picks.length ?? 0;
  const activeFilledPick = activePositionFilter
    ? squad.find((pick) => pick.slotNumber === activePositionFilter.slotNumber)
    : null;
  const fieldPicks: FieldPick[] = squad.map((pick) => ({
    country: pick.country,
    slotNumber: pick.slotNumber,
    positionCode: pick.selectedPosition,
    player_name: pick.player.player_name,
    position: pick.selectedPosition,
    year: pick.year,
    rating: pick.player.rating,
  }));

  const visibleSquadPlayers = useMemo(() => {
    const players = sortPlayersByRating(spunSquad?.squad ?? []);
    if (!activePositionFilter || activeFilledPick) {
      return players;
    }
    return players.filter((player) =>
      isPlayerEligibleForFieldPosition(player, activePositionFilter.positionCode),
    );
  }, [activeFilledPick, activePositionFilter, spunSquad]);

  async function runAction(action: string, callback: () => Promise<void>) {
    setLoadingAction(action);
    setError(null);
    setWarning(null);

    try {
      await callback();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Something went wrong.",
      );
    } finally {
      setLoadingAction(null);
    }
  }

  async function handleStartDraftAndSpin() {
    if (yearMin > yearMax) {
      setError("Year From must be earlier than or equal to Year To.");
      return;
    }

    await runAction("start", async () => {
      const startedAt = Date.now();
      const spinParams = {
        year_min: yearMin,
        year_max: yearMax,
        needed_positions: getRemainingNeededPositions([]),
      };
      const spinUrl = buildSpinSquadUrl(spinParams);
      setLastSpinSquadUrl(spinUrl);
      console.info(`[spin-squad] ${spinUrl}`);
      setSpinRevealTarget(null);
      setSpinRevealActive(true);
      setSpunSquad(null);
      setExpandedPlayerId(null);
      setActivePositionFilter(null);
      setSquad([]);
      setRating(null);
      setSimulation(null);
      try {
        const session = await createDraftSession();
        setDraftSession(session);
        const squadResult = await spinSquad(spinParams);
        setSpinRevealTarget({
          country: squadResult.country,
          year: squadResult.year,
        });
        const elapsed = Date.now() - startedAt;
        if (elapsed < MIN_SPIN_REVEAL_MS) {
          await new Promise((resolve) => {
            window.setTimeout(resolve, MIN_SPIN_REVEAL_MS - elapsed);
          });
        }
        setSpunSquad(squadResult);
      } finally {
        setSpinRevealActive(false);
        setSpinRevealTarget(null);
      }
    });
  }

  async function handleSpin() {
    if (!draftSession) {
      setError("Start a draft before spinning a squad.");
      return;
    }
    if (yearMin > yearMax) {
      setError("Year From must be earlier than or equal to Year To.");
      return;
    }
    const neededPositions = getRemainingNeededPositions(squad);
    if (!neededPositions.length) {
      setError("Your XV is complete. Start the World Cup.");
      return;
    }

    await runAction("spin", async () => {
      const startedAt = Date.now();
      const spinParams = {
        year_min: yearMin,
        year_max: yearMax,
        needed_positions: neededPositions,
      };
      const spinUrl = buildSpinSquadUrl(spinParams);
      setLastSpinSquadUrl(spinUrl);
      console.info(`[spin-squad] ${spinUrl}`);
      setSpinRevealTarget(null);
      setSpinRevealActive(true);
      setExpandedPlayerId(null);
      setActivePositionFilter(null);
      setSimulation(null);
      try {
        const squadResult = await spinSquad(spinParams);
        setSpinRevealTarget({
          country: squadResult.country,
          year: squadResult.year,
        });
        const elapsed = Date.now() - startedAt;
        if (elapsed < MIN_SPIN_REVEAL_MS) {
          await new Promise((resolve) => {
            window.setTimeout(resolve, MIN_SPIN_REVEAL_MS - elapsed);
          });
        }
        setSpunSquad(squadResult);
      } finally {
        setSpinRevealActive(false);
        setSpinRevealTarget(null);
      }
    });
  }

  function handleFieldPositionClick(positionCode: string, slotNumber: number) {
    const clickedSameSlot = activePositionFilter?.slotNumber === slotNumber;
    if (clickedSameSlot) {
      setActivePositionFilter(null);
      setWarning(null);
      return;
    }

    setActivePositionFilter({ positionCode, slotNumber });
    const filledPick = squad.find((pick) => pick.slotNumber === slotNumber);
    if (filledPick) {
      setWarning(
        `Slot ${slotNumber} is filled by ${filledPick.player.player_name}. Replacement is not available yet.`,
      );
      return;
    }

    setWarning(null);
  }

  async function handleSelectSquadPlayer(player: SpinSquadPlayer) {
    if (!isPlayerSelectable(player, squad, activePositionFilter)) {
      return;
    }

    setError(null);
    setWarning(null);
    const availablePositions = orderAvailablePositions(
      getAvailablePositionsForPlayer(player, squad),
      activePositionFilter,
    );
    if (!availablePositions.length) {
      return;
    }
    if (activePositionFilter && isTbcSpunPlayer(player)) {
      const filteredPosition = toGamePositionCode(
        activePositionFilter.positionCode,
      );
      if (availablePositions.includes(filteredPosition)) {
        await addPlayerToXV(player, filteredPosition);
        return;
      }
    }
    if (availablePositions.length === 1) {
      await addPlayerToXV(player, availablePositions[0]);
      return;
    }
    setExpandedPlayerId(player.squad_appearance_id);
  }

  async function addPlayerToXV(player: SpinSquadPlayer, selectedPosition: string) {
    if (!draftSession || !spunSquad) {
      setError("Spin a squad before adding to the XV.");
      return;
    }
    if (!selectedPosition) {
      setError("Choose a position before adding to the XV.");
      return;
    }
    if (!isPlayerEligibleForSelectedPosition(player, selectedPosition)) {
      setError("Selected player is not eligible for that position.");
      return;
    }
    const slotNumber = getSlotForPosition(
      selectedPosition,
      activePositionFilter,
      squad,
    );
    if (slotNumber === null) {
      setError("That position slot is already filled.");
      return;
    }
    const backendSelectedPosition = backendPositionForSlot(
      selectedPosition,
      slotNumber,
    );

    await runAction("pick", async () => {
      const updatedSession = await addDraftPick(
        draftSession.id,
        player.squad_appearance_id,
        backendSelectedPosition,
      );
      const nextPick = updatedSession.picks.at(-1);
      const updatedRating = await getDraftSessionRating(updatedSession.id);
      setDraftSession(updatedSession);
      setSquad((players) => [
        ...players,
        {
          pickNumber: nextPick?.pick_number ?? players.length + 1,
          slotNumber,
          selectedPosition: backendSelectedPosition,
          player,
          country: spunSquad.country,
          year: spunSquad.year,
        },
      ]);
      setRating(updatedRating);
      setSpunSquad(null);
      setExpandedPlayerId(null);
      setActivePositionFilter(null);
      setSimulation(null);
    });
  }

  async function handleSimulate() {
    if (!draftSession) {
      return;
    }
    await runAction("simulate", async () => {
      setSimulation(await simulateDraftSession(draftSession.id));
    });
  }

  async function handleMainAction() {
    if (loadingAction !== null) {
      return;
    }
    if (!draftSession) {
      await handleStartDraftAndSpin();
      return;
    }
    if (picksMade >= 15) {
      await handleSimulate();
      return;
    }
    await handleSpin();
  }

  return (
    <main className="min-h-screen bg-neutral-950 px-4 py-6 text-neutral-50 sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <header className="border-b border-emerald-800/60 pb-5">
          <div>
            <p className="text-sm font-semibold uppercase text-emerald-300">
              Rugby World Cup Draft
            </p>
            <h1 className="mt-1 text-4xl font-bold tracking-normal text-white sm:text-5xl">
              Rugby 15-0
            </h1>
          </div>
        </header>

        {error ? (
          <div className="rounded-md border border-red-400/50 bg-red-950 px-4 py-3 text-sm text-red-100">
            {error}
          </div>
        ) : null}
        {warning ? (
          <div className="rounded-md border border-yellow-300/50 bg-yellow-950 px-4 py-3 text-sm text-yellow-100">
            {warning}
          </div>
        ) : null}

        <section className="grid gap-6 xl:grid-cols-[minmax(640px,1fr)_430px]">
          <div className="flex flex-col gap-6">
            <RatingPanel rating={rating} />
            {simulation ? <SeasonResult simulation={simulation} /> : null}
            <RugbyFieldLayout
              picks={fieldPicks}
              activePositionFilter={activePositionFilter}
              onPositionClick={handleFieldPositionClick}
            />
          </div>

          <DraftRoom
            activeFilledPick={activeFilledPick}
            activePositionFilter={activePositionFilter}
            draftSession={draftSession}
            finalSpinTarget={spinRevealTarget}
            lastSpinSquadUrl={lastSpinSquadUrl}
            loadingAction={loadingAction}
            picks={squad}
            picksMade={picksMade}
            spinRevealActive={spinRevealActive}
            expandedPlayerId={expandedPlayerId}
            spunSquad={spunSquad}
            visiblePlayers={visibleSquadPlayers}
            yearMax={yearMax}
            yearMin={yearMin}
            onChoosePlayerPosition={addPlayerToXV}
            onSelectPlayer={handleSelectSquadPlayer}
            onMainAction={handleMainAction}
            onYearMaxChange={setYearMax}
            onYearMinChange={setYearMin}
            onClearError={() => setError(null)}
          />
        </section>
      </div>
    </main>
  );
}

function DraftRoom({
  activeFilledPick,
  activePositionFilter,
  draftSession,
  finalSpinTarget,
  lastSpinSquadUrl,
  loadingAction,
  picks,
  picksMade,
  spinRevealActive,
  expandedPlayerId,
  spunSquad,
  visiblePlayers,
  yearMax,
  yearMin,
  onChoosePlayerPosition,
  onClearError,
  onMainAction,
  onSelectPlayer,
  onYearMaxChange,
  onYearMinChange,
}: {
  activeFilledPick: SquadPlayer | null | undefined;
  activePositionFilter: ActivePositionFilter;
  draftSession: DraftSession | null;
  finalSpinTarget: { country: string; year: number } | null;
  lastSpinSquadUrl: string | null;
  loadingAction: string | null;
  picks: SquadPlayer[];
  picksMade: number;
  spinRevealActive: boolean;
  expandedPlayerId: number | null;
  spunSquad: SpinSquadResult | null;
  visiblePlayers: SpinSquadPlayer[];
  yearMax: number;
  yearMin: number;
  onChoosePlayerPosition: (
    player: SpinSquadPlayer,
    position: string,
  ) => void;
  onClearError: () => void;
  onMainAction: () => void;
  onSelectPlayer: (player: SpinSquadPlayer) => void;
  onYearMaxChange: (year: number) => void;
  onYearMinChange: (year: number) => void;
}) {
  const mainActionLabel = getMainActionLabel(
    draftSession,
    picksMade,
    loadingAction,
  );

  return (
    <aside className="rounded-lg border border-neutral-800 bg-neutral-900 p-5 shadow-sm">
      <div className="flex flex-col gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">Draft room</h2>
          <p className="mt-1 text-sm text-neutral-400">
            {draftSession
              ? `Session #${draftSession.id} · ${picksMade}/15 picks`
              : "Start a draft to begin."}
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <YearSelect
            id="year-min"
            label="Year From"
            value={yearMin}
            onChange={onYearMinChange}
          />
          <YearSelect
            id="year-max"
            label="Year To"
            value={yearMax}
            onChange={onYearMaxChange}
          />
        </div>

        <div>
          <p className="text-sm font-medium text-neutral-300">Era</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {YEAR_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  onYearMinChange(preset.yearMin);
                  onYearMaxChange(preset.yearMax);
                  onClearError();
                }}
                className="rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs font-semibold text-neutral-200 transition hover:border-emerald-400 hover:text-emerald-200"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={onMainAction}
          disabled={loadingAction !== null}
          className="inline-flex h-11 items-center justify-center rounded-md bg-emerald-500 px-5 text-sm font-semibold text-neutral-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
        >
          {mainActionLabel}
        </button>

        {process.env.NODE_ENV === "development" && lastSpinSquadUrl ? (
          <div className="break-all rounded-md border border-cyan-400/30 bg-cyan-950/30 px-3 py-2 text-xs text-cyan-100">
            API URL: {lastSpinSquadUrl}
          </div>
        ) : null}

        {activeFilledPick ? (
          <div className="rounded-md border border-yellow-300/40 bg-yellow-950 px-3 py-2 text-sm text-yellow-100">
            Slot {activeFilledPick.slotNumber} is filled by{" "}
            {activeFilledPick.player.player_name}.
          </div>
        ) : null}

        <SquadSelection
          activeFilledPick={activeFilledPick}
          activePositionFilter={activePositionFilter}
          expandedPlayerId={expandedPlayerId}
          finalSpinTarget={finalSpinTarget}
          loadingAction={loadingAction}
          picks={picks}
          spinRevealActive={spinRevealActive}
          spunSquad={spunSquad}
          visiblePlayers={visiblePlayers}
          onChoosePlayerPosition={onChoosePlayerPosition}
          onSelectPlayer={onSelectPlayer}
        />
      </div>
    </aside>
  );
}

function SquadSelection({
  activeFilledPick,
  activePositionFilter,
  expandedPlayerId,
  finalSpinTarget,
  loadingAction,
  picks,
  spinRevealActive,
  spunSquad,
  visiblePlayers,
  onChoosePlayerPosition,
  onSelectPlayer,
}: {
  activeFilledPick: SquadPlayer | null | undefined;
  activePositionFilter: ActivePositionFilter;
  expandedPlayerId: number | null;
  finalSpinTarget: { country: string; year: number } | null;
  loadingAction: string | null;
  picks: SquadPlayer[];
  spinRevealActive: boolean;
  spunSquad: SpinSquadResult | null;
  visiblePlayers: SpinSquadPlayer[];
  onChoosePlayerPosition: (
    player: SpinSquadPlayer,
    position: string,
  ) => void;
  onSelectPlayer: (player: SpinSquadPlayer) => void;
}) {
  if (spinRevealActive) {
    return (
      <SpinRevealAnimation
        isSpinning
        finalCountry={finalSpinTarget?.country}
        finalYear={finalSpinTarget?.year}
      />
    );
  }

  if (!spunSquad) {
    return (
      <div className="rounded-md border border-dashed border-neutral-700 bg-neutral-950 px-4 py-8 text-center text-sm text-neutral-400">
        Spin a World Cup squad to choose your next pick.
      </div>
    );
  }

  if (activeFilledPick) {
    return (
      <div className="rounded-md border border-neutral-800 bg-neutral-950 p-4">
        <p className="text-sm font-medium text-neutral-400">Current squad</p>
        <h3 className="mt-1 text-2xl font-bold text-white">
          {spunSquad.country} {spunSquad.year}
        </h3>
        <div className="mt-4 rounded-md border border-dashed border-neutral-700 px-4 py-8 text-sm text-neutral-400">
          This field position is already filled. Replacement is not available yet.
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-neutral-800 bg-neutral-950 p-4">
      <p className="text-sm font-medium text-neutral-400">Current squad</p>
      <h3 className="mt-1 text-2xl font-bold text-white">
        {spunSquad.country} {spunSquad.year}
      </h3>
      <p className="mt-1 text-sm text-neutral-400">
        {activePositionFilter
          ? `Showing ${positionNameForCode(activePositionFilter.positionCode)} eligible players.`
          : "Choose one player from this World Cup squad."}
      </p>

      <div className="mt-4 flex max-h-[620px] flex-col gap-2 overflow-y-auto pr-1">
        {visiblePlayers.length ? (
          visiblePlayers.map((player) => {
            const selectable = isPlayerSelectable(player, picks, activePositionFilter);
            const isSelected =
              expandedPlayerId === player.squad_appearance_id;
            const isTbcPlayer = isTbcSpunPlayer(player);
            const availablePositions = orderAvailablePositions(
              getAvailablePositionsForPlayer(player, picks),
              activePositionFilter,
            );
            return (
              <div
                key={player.squad_appearance_id}
                className={playerRowClassName(isSelected, selectable)}
              >
                <button
                  type="button"
                  onClick={() => onSelectPlayer(player)}
                  disabled={!selectable}
                  className="block w-full text-left disabled:cursor-not-allowed"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">
                        {player.player_name}
                      </span>
                      <span className="mt-1 block text-xs opacity-75">
                        {isTbcPlayer
                          ? "TBC / Any Open Position"
                          : player.position ?? "TBC"}{" "}
                        ·{" "}
                        {player.rating === null
                          ? "Unrated"
                          : player.rating.toFixed(1)}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs font-bold">
                      {player.rating === null ? "--" : player.rating.toFixed(1)}
                    </span>
                  </span>
                  <AvailabilityLine player={player} picks={picks} />
                </button>
                {isSelected ? (
                  <InlinePositionChoices
                    loadingAction={loadingAction}
                    player={player}
                    positions={availablePositions}
                    onChoose={onChoosePlayerPosition}
                  />
                ) : null}
              </div>
            );
          })
        ) : (
          <div className="rounded-md border border-dashed border-neutral-700 px-4 py-8 text-sm text-neutral-400">
            No players in this squad are eligible for this position.
          </div>
        )}
      </div>
    </div>
  );
}

function InlinePositionChoices({
  loadingAction,
  player,
  positions,
  onChoose,
}: {
  loadingAction: string | null;
  player: SpinSquadPlayer;
  positions: string[];
  onChoose: (player: SpinSquadPlayer, position: string) => void;
}) {
  return (
    <span className="mt-3 block rounded-md border border-yellow-700/40 bg-yellow-950/60 p-2">
      <span className="block text-xs font-semibold text-yellow-100">
        Choose position
      </span>
      <span className="mt-2 flex flex-wrap gap-2">
        {positions.map((position) => (
          <button
            key={position}
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onChoose(player, position);
            }}
            disabled={loadingAction === "pick"}
            className="inline-flex h-8 cursor-pointer items-center rounded-md bg-yellow-300 px-3 text-xs font-black text-neutral-950 transition hover:bg-yellow-200 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
          >
            {position}
          </button>
        ))}
      </span>
    </span>
  );
}

function AvailabilityLine({
  player,
  picks,
}: {
  player: SpinSquadPlayer;
  picks: SquadPlayer[];
}) {
  const available = getAvailablePositionsForPlayer(player, picks);
  const locked = getLockedPositionsForPlayer(player, picks);
  const isTbcPlayer = isTbcSpunPlayer(player);

  if (!available.length) {
    return (
      <span className="mt-2 block text-xs text-neutral-500">
        All eligible positions already filled
      </span>
    );
  }

  if (isTbcPlayer) {
    return (
      <span className="mt-2 block text-xs font-semibold text-cyan-200">
        TBC / Any Open Position
      </span>
    );
  }

  return (
    <span className="mt-2 flex flex-wrap gap-1">
      {available.map((position) => (
        <span
          key={`available-${position}`}
          className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-200"
        >
          {position}
        </span>
      ))}
      {locked.map((position) => (
        <span
          key={`locked-${position}`}
          className="rounded bg-neutral-800 px-2 py-0.5 text-xs font-semibold text-neutral-500 line-through"
        >
          {position}
        </span>
      ))}
    </span>
  );
}

function YearSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      <span className="text-xs font-semibold uppercase text-neutral-500">
        {label}
      </span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-11 rounded-md border border-neutral-700 bg-neutral-950 px-3 text-sm font-medium text-white outline-none focus:border-emerald-500"
      >
        {WORLD_CUP_YEARS.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </label>
  );
}

function RatingPanel({ rating }: { rating: DraftSessionRating | null }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-5 shadow-sm">
      <h2 className="text-xl font-semibold text-white">Team rating</h2>
      {rating ? (
        <div className="mt-4 grid grid-cols-3 gap-3">
          <Metric label="Overall" value={rating.overall_rating} highlight />
          <Metric label="Pack" value={rating.pack_rating} />
          <Metric label="Backline" value={rating.backline_rating} />
          <Metric label="Attack" value={rating.attack_rating} />
          <Metric label="Defence" value={rating.defence_rating} />
          <Metric label="Set piece" value={rating.set_piece_rating} />
        </div>
      ) : (
        <p className="mt-4 rounded-md border border-dashed border-neutral-700 bg-neutral-950 px-4 py-6 text-sm text-neutral-400">
          Add a player to calculate your first team rating.
        </p>
      )}
    </section>
  );
}

function SeasonResult({ simulation }: { simulation: SeasonSimulation }) {
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-900 p-5 shadow-sm">
      <div className="rounded-md bg-emerald-500 px-4 py-3 text-neutral-950">
        <p className="text-sm font-semibold text-emerald-950">Season result</p>
        <p className="mt-1 text-2xl font-bold">
          {simulation.wins}-{simulation.losses}
          {simulation.undefeated ? " undefeated" : ""}
        </p>
        <p className="mt-1 text-sm text-emerald-950">
          Team rating {simulation.team_rating.toFixed(1)}
        </p>
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div
      className={
        highlight
          ? "col-span-3 rounded-md bg-emerald-500 px-4 py-3 text-neutral-950"
          : "rounded-md border border-neutral-800 bg-neutral-950 px-3 py-2 text-white"
      }
    >
      <p
        className={
          highlight
            ? "text-xs font-semibold uppercase text-emerald-950"
            : "text-xs font-semibold uppercase text-neutral-500"
        }
      >
        {label}
      </p>
      <p className="mt-1 text-xl font-bold">{value.toFixed(1)}</p>
    </div>
  );
}

function playerRowClassName(isSelected: boolean, isSelectable: boolean) {
  if (!isSelectable) {
    return "rounded-md border border-neutral-800 bg-neutral-900/50 px-3 py-2 text-left text-sm text-neutral-500 opacity-60";
  }
  if (isSelected) {
    return "rounded-md border border-yellow-300 bg-yellow-300 px-3 py-2 text-left text-sm text-neutral-950 shadow-sm";
  }
  return "rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2 text-left text-sm text-neutral-100 transition hover:border-emerald-400 hover:bg-neutral-800";
}
