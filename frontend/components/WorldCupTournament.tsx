"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";

type DraftPlayer = {
  pickNumber: number;
  selectedPosition: string;
  playerName: string;
  country: string;
  year: number;
  rating: number | null;
};

type Team = {
  name: string;
  rating: number;
  pool: string;
  isUser?: boolean;
};

type Match = {
  id: string;
  stage: string;
  pool?: string;
  home: string;
  away: string;
  homeRating: number;
  awayRating: number;
  played: boolean;
  homeScore?: number;
  awayScore?: number;
  winner?: string;
};

type Standing = {
  team: Team;
  played: number;
  wins: number;
  losses: number;
  pointsFor: number;
  pointsAgainst: number;
  points: number;
};

type StageView =
  | "pool"
  | "pool-complete"
  | "quarter-final"
  | "quarter-final-complete"
  | "semi-final"
  | "semi-final-complete"
  | "final"
  | "final-complete"
  | "summary-ready"
  | "summary";

const POOLS: Team[][] = [
  [
    { name: "Your XV", rating: 80, pool: "A", isUser: true },
    { name: "New Zealand", rating: 94, pool: "A" },
    { name: "Italy", rating: 81, pool: "A" },
    { name: "Georgia", rating: 78, pool: "A" },
  ],
  [
    { name: "South Africa", rating: 94, pool: "B" },
    { name: "Scotland", rating: 86, pool: "B" },
    { name: "Romania", rating: 74, pool: "B" },
    { name: "Tonga", rating: 79, pool: "B" },
  ],
  [
    { name: "Argentina", rating: 86, pool: "C" },
    { name: "Fiji", rating: 84, pool: "C" },
    { name: "Wales", rating: 85, pool: "C" },
    { name: "Canada", rating: 72, pool: "C" },
  ],
  [
    { name: "Ireland", rating: 92, pool: "D" },
    { name: "Australia", rating: 88, pool: "D" },
    { name: "Japan", rating: 82, pool: "D" },
    { name: "Uruguay", rating: 76, pool: "D" },
  ],
  [
    { name: "France", rating: 91, pool: "E" },
    { name: "England", rating: 89, pool: "E" },
    { name: "Samoa", rating: 80, pool: "E" },
    { name: "United States", rating: 75, pool: "E" },
  ],
  [
    { name: "Portugal", rating: 77, pool: "F" },
    { name: "Spain", rating: 73, pool: "F" },
    { name: "Namibia", rating: 73, pool: "F" },
    { name: "Chile", rating: 71, pool: "F" },
  ],
];

const POOL_ACCENTS = [
  "from-orange-500 to-rose-500",
  "from-cyan-400 to-blue-500",
  "from-yellow-300 to-orange-400",
  "from-emerald-400 to-teal-500",
  "from-pink-500 to-fuchsia-500",
  "from-violet-500 to-indigo-500",
];

export function WorldCupTournament({
  teamRating,
  teamName,
  draftedPlayers,
  onStartNewDraft,
}: {
  teamRating: number;
  teamName: string;
  draftedPlayers: DraftPlayer[];
  onStartNewDraft: () => void;
}) {
  const userTeamName = teamName.trim() || "Your XV";
  const teams = useMemo(
    () => createTeams(teamRating, userTeamName),
    [teamRating, userTeamName],
  );
  const [poolMatches, setPoolMatches] = useState(() => createPoolMatches(teams));
  const [knockoutMatches, setKnockoutMatches] = useState<Match[]>([]);
  const [message, setMessage] = useState("Pool stage ready.");
  const [eliminated, setEliminated] = useState<Match | null>(null);
  const [championMatch, setChampionMatch] = useState<Match | null>(null);
  const [autoPlaying, setAutoPlaying] = useState(false);
  const [stageView, setStageView] = useState<StageView>("pool");

  const standings = useMemo(
    () => calculateStandings(teams, poolMatches),
    [poolMatches, teams],
  );
  const qualifiers = useMemo(() => getQualifiers(standings), [standings]);
  const poolComplete = poolMatches.every((match) => match.played);
  const nextPoolMatch = poolMatches.find((match) => !match.played);
  const latestResult = [...poolMatches, ...knockoutMatches]
    .filter((match) => match.played)
    .at(-1);
  const playedMatches = [...poolMatches, ...knockoutMatches].filter(
    (match) => match.played,
  );
  const userMatches = playedMatches.filter((match) =>
    isUserMatch(match, userTeamName),
  );
  const tournamentEnded = Boolean(eliminated || championMatch);
  const currentKnockoutStage = stageToMatchStage(stageView);
  const nextStageMatch = currentKnockoutStage
    ? knockoutMatches.find(
        (match) => match.stage === currentKnockoutStage && !match.played,
      )
    : undefined;
  const stageGateLabel = continueLabel(stageView, eliminated, championMatch);

  function playNextMatch() {
    if (autoPlaying || stageGateLabel) {
      return;
    }
    if (stageView === "pool" && nextPoolMatch) {
      playPoolMatch(nextPoolMatch.id);
      return;
    }
    if (nextStageMatch) {
      playKnockoutMatch(nextStageMatch.id);
      return;
    }
  }

  async function autoPlayPoolStage() {
    if (autoPlaying || tournamentEnded || poolComplete || stageView !== "pool") {
      return;
    }
    setAutoPlaying(true);
    setMessage("Auto-playing pool stage...");
    let updated = poolMatches;
    try {
      for (const match of poolMatches.filter((item) => !item.played)) {
        updated = updated.map((item) =>
          item.id === match.id ? simulateMatch(item) : item,
        );
        setPoolMatches(updated);
        const played = updated.find((item) => item.id === match.id);
        setMessage(played ? resultText(played) : "Pool match played.");
        await sleep(520);
      }
    } finally {
      setAutoPlaying(false);
    }
    const nextStandings = calculateStandings(teams, updated);
    const nextQualifiers = getQualifiers(nextStandings);
    if (!nextQualifiers.some((team) => team.isUser)) {
      setEliminated({
        id: "pool-elimination",
        stage: "Pool Stage",
        home: userTeamName,
        away: "Top 8 qualification",
        homeRating: teamRating,
        awayRating: 0,
        played: true,
        homeScore: 0,
        awayScore: 0,
        winner: "Top 8 qualification",
      });
      setMessage(`${userTeamName} has been eliminated in the pool stage.`);
      setStageView("summary-ready");
      return;
    }
    setStageView("pool-complete");
    setMessage("Pool stage complete. Review qualifiers before continuing.");
  }

  async function autoPlayRound(round: string) {
    if (autoPlaying || tournamentEnded || stageGateLabel) {
      return;
    }
    const activeRound = stageToMatchStage(stageView);
    if (!activeRound || activeRound !== round) {
      return;
    }
    setAutoPlaying(true);
    setMessage("Auto-playing current knockout round...");
    const roundMatches = knockoutMatches.filter(
      (match) => match.stage === round && !match.played,
    );
    let nextMatches = knockoutMatches;
    try {
      for (const match of roundMatches) {
        nextMatches = playKnockoutMatchInList(nextMatches, match.id);
        commitKnockoutMatches(nextMatches);
        const played = nextMatches.find((item) => item.id === match.id);
        setMessage(played ? resultText(played) : "Knockout match played.");
        await sleep(520);
        if (userLost(played, userTeamName)) {
          break;
        }
      }
    } finally {
      setAutoPlaying(false);
    }
  }

  async function autoPlayRemaining() {
    if (autoPlaying || tournamentEnded || stageGateLabel) {
      return;
    }
    if (stageView === "pool") {
      await autoPlayPoolStage();
      return;
    }
    const activeRound = stageToMatchStage(stageView);
    if (activeRound) {
      await autoPlayRound(activeRound);
    }
  }

  function playPoolMatch(matchId: string) {
    const updated = poolMatches.map((match) =>
      match.id === matchId ? simulateMatch(match) : match,
    );
    setPoolMatches(updated);
    const played = updated.find((match) => match.id === matchId);
    if (updated.every((match) => match.played)) {
      const nextStandings = calculateStandings(teams, updated);
      const nextQualifiers = getQualifiers(nextStandings);
    if (!nextQualifiers.some((team) => team.isUser)) {
        setEliminated({
          id: "pool-elimination",
          stage: "Pool Stage",
          home: userTeamName,
          away: "Top 8 qualification",
          homeRating: teamRating,
          awayRating: 0,
          played: true,
          homeScore: 0,
          awayScore: 0,
          winner: "Top 8 qualification",
        });
        setMessage(`${userTeamName} has been eliminated in the pool stage.`);
        setStageView("summary-ready");
        return;
      }
      setStageView("pool-complete");
      setMessage("Pool stage complete. Review qualifiers before continuing.");
      return;
    }
    setMessage(played ? resultText(played) : "Pool match played.");
  }

  function playKnockoutMatch(matchId: string) {
    commitKnockoutMatches(playKnockoutMatchInList(knockoutMatches, matchId));
  }

  function commitKnockoutMatches(matches: Match[]) {
    setKnockoutMatches(matches);
    const justPlayed = matches.filter((match) => match.played).at(-1);
    if (userLost(justPlayed, userTeamName)) {
      setEliminated(justPlayed ?? null);
      setMessage(`${userTeamName} has been eliminated.`);
      setStageView("summary-ready");
      return;
    }
    const final = matches.find((match) => match.stage === "Final" && match.played);
    if (final?.winner === userTeamName) {
      setChampionMatch(final);
      setMessage("World Cup Champions.");
      setStageView("final-complete");
      return;
    }
    const roundComplete = currentKnockoutStage
      ? matches
          .filter((match) => match.stage === currentKnockoutStage)
          .every((match) => match.played)
      : false;
    if (currentKnockoutStage && roundComplete) {
      setStageView(completedStageForMatchStage(currentKnockoutStage));
      setMessage(`${currentKnockoutStage} complete. Review results before continuing.`);
      return;
    }
    setMessage(justPlayed ? resultText(justPlayed) : "Knockout match played.");
  }

  function continueTournament() {
    if (stageView === "pool-complete") {
      setKnockoutMatches(createQuarterFinals(qualifiers));
      setStageView("quarter-final");
      setMessage("Quarter-finals ready.");
      return;
    }
    if (stageView === "quarter-final-complete") {
      setKnockoutMatches((matches) => addSemiFinals(matches, userTeamName));
      setStageView("semi-final");
      setMessage("Semi-finals ready.");
      return;
    }
    if (stageView === "semi-final-complete") {
      setKnockoutMatches((matches) => addFinal(matches, userTeamName));
      setStageView("final");
      setMessage("Final ready.");
      return;
    }
    if (stageView === "final-complete" || stageView === "summary-ready") {
      setStageView("summary");
    }
  }

  return (
    <section className="overflow-hidden rounded-xl border border-cyan-300/20 bg-[#070b1a] text-white shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
      <div className="relative overflow-hidden px-5 py-6 sm:px-7">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_12%,rgba(34,211,238,0.2),transparent_26%),radial-gradient(circle_at_84%_8%,rgba(249,115,22,0.18),transparent_22%),linear-gradient(135deg,rgba(255,255,255,0.04)_0_1px,transparent_1px_22px)]" />
        <div className="relative flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.22em] text-cyan-200">
              Rugby 15-0 World Cup
            </p>
            <h2 className="mt-2 text-3xl font-black uppercase tracking-normal text-white sm:text-4xl">
              Tournament Mode
            </h2>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/10 px-4 py-3">
            <p className="text-xs font-bold uppercase text-white/60">
              {userTeamName}
            </p>
            <p className="text-2xl font-black text-yellow-300">
              {teamRating.toFixed(1)}
            </p>
          </div>
        </div>
      </div>

      {stageView === "summary" && championMatch ? (
          <ChampionScreen
            draftedPlayers={draftedPlayers}
            finalMatch={championMatch}
            matches={userMatches}
            teamRating={teamRating}
            teamName={userTeamName}
            onStartNewDraft={onStartNewDraft}
          />
      ) : stageView === "summary" && eliminated ? (
        <EliminatedScreen
          match={eliminated}
          matches={userMatches}
          teamName={userTeamName}
          teamRating={teamRating}
          onStartNewDraft={onStartNewDraft}
        />
      ) : (
        <div className="grid gap-5 p-5 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="flex flex-col gap-5">
            <TournamentControls
              message={message}
              poolComplete={poolComplete}
              nextPoolMatch={nextPoolMatch}
              nextKnockoutMatch={nextStageMatch}
              autoPlaying={autoPlaying}
              stageGateLabel={stageGateLabel}
              onPlayNext={playNextMatch}
              onAutoPool={autoPlayPoolStage}
              onAutoRound={autoPlayRound}
              onAutoRemaining={autoPlayRemaining}
              onContinue={continueTournament}
            />
            <PoolGrid standings={standings} />
          </div>

          <div className="flex flex-col gap-5">
            <LatestResult match={latestResult} />
            <KnockoutBracket
              qualifiers={qualifiers}
              knockoutMatches={knockoutMatches}
              poolComplete={poolComplete}
              stageView={stageView}
            />
          </div>
        </div>
      )}
    </section>
  );
}

function TournamentControls({
  message,
  poolComplete,
  nextPoolMatch,
  nextKnockoutMatch,
  autoPlaying,
  stageGateLabel,
  onPlayNext,
  onAutoPool,
  onAutoRound,
  onAutoRemaining,
  onContinue,
}: {
  message: string;
  poolComplete: boolean;
  nextPoolMatch?: Match;
  nextKnockoutMatch?: Match;
  autoPlaying: boolean;
  stageGateLabel: string | null;
  onPlayNext: () => void;
  onAutoPool: () => void;
  onAutoRound: (round: string) => void;
  onAutoRemaining: () => void;
  onContinue: () => void;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.06] p-4">
      <p className="text-sm font-semibold text-cyan-100">
        {autoPlaying ? "Auto-playing..." : message}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {stageGateLabel ? (
          <ActionButton disabled={autoPlaying} variant="yellow" onClick={onContinue}>
            {stageGateLabel}
          </ActionButton>
        ) : null}
        <ActionButton disabled={autoPlaying || Boolean(stageGateLabel)} onClick={onPlayNext}>
          {poolComplete ? "Play Next Knockout Match" : "Play Next Match"}
        </ActionButton>
        {!poolComplete ? (
          <ActionButton disabled={autoPlaying || Boolean(stageGateLabel)} variant="orange" onClick={onAutoPool}>
            Auto Play Pool Stage
          </ActionButton>
        ) : (
          <>
            <ActionButton
              disabled={autoPlaying || Boolean(stageGateLabel) || !nextKnockoutMatch}
              variant="orange"
              onClick={() => onAutoRound(nextKnockoutMatch?.stage ?? "Quarter-Final")}
            >
              Auto Play Current Knockout Round
            </ActionButton>
            <ActionButton
              disabled={autoPlaying || Boolean(stageGateLabel) || !nextKnockoutMatch}
              variant="teal"
              onClick={onAutoRemaining}
            >
              Auto Play Remaining Tournament
            </ActionButton>
          </>
        )}
      </div>
      <p className="mt-3 text-xs text-white/50">
        Next:{" "}
        {nextPoolMatch
          ? `${nextPoolMatch.home} v ${nextPoolMatch.away}`
          : nextKnockoutMatch
            ? `${nextKnockoutMatch.stage}: ${nextKnockoutMatch.home} v ${nextKnockoutMatch.away}`
            : "Bracket being prepared"}
      </p>
    </div>
  );
}

function PoolGrid({ standings }: { standings: Record<string, Standing[]> }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {Object.entries(standings).map(([pool, rows], index) => (
        <div
          key={pool}
          className="overflow-hidden rounded-xl border border-white/10 bg-[#10162a]"
        >
          <div className={`bg-gradient-to-r ${POOL_ACCENTS[index]} px-4 py-3`}>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-black/60">
              Pool {pool}
            </p>
          </div>
          <div className="p-3">
            <div className="grid grid-cols-[minmax(120px,1fr)_28px_28px_38px_38px_38px] gap-2 px-2 pb-2 text-[10px] font-bold uppercase text-white/45">
              <span>Team</span>
              <span>W</span>
              <span>L</span>
              <span>PF</span>
              <span>PA</span>
              <span>Pts</span>
            </div>
            {rows.map((row) => (
              <div
                key={row.team.name}
                className={
                  row.team.isUser
                    ? "grid grid-cols-[minmax(120px,1fr)_28px_28px_38px_38px_38px] gap-2 rounded-lg bg-yellow-300 px-2 py-2 text-sm font-black text-neutral-950"
                    : "grid grid-cols-[minmax(120px,1fr)_28px_28px_38px_38px_38px] gap-2 rounded-lg px-2 py-2 text-sm font-semibold text-white/86"
                }
              >
                <span className="min-w-0 whitespace-normal break-words leading-tight">
                  {row.team.name}
                </span>
                <span>{row.wins}</span>
                <span>{row.losses}</span>
                <span>{row.pointsFor}</span>
                <span>{row.pointsAgainst}</span>
                <span>{row.points}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function LatestResult({ match }: { match?: Match }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.06] p-4">
      <p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-200">
        Latest Result
      </p>
      {match ? (
        <div className="mt-3">
          <p className="text-sm font-semibold text-white/60">{match.stage}</p>
          <p className="mt-1 text-xl font-black text-white">
            {match.home} {match.homeScore} - {match.awayScore} {match.away}
          </p>
          <p className="mt-1 text-sm font-semibold text-yellow-300">
            Winner: {match.winner}
          </p>
        </div>
      ) : (
        <p className="mt-3 text-sm text-white/50">No matches played yet.</p>
      )}
    </div>
  );
}

function KnockoutBracket({
  qualifiers,
  knockoutMatches,
  poolComplete,
  stageView,
}: {
  qualifiers: Team[];
  knockoutMatches: Match[];
  poolComplete: boolean;
  stageView: StageView;
}) {
  const visibleRounds = visibleKnockoutRounds(knockoutMatches, stageView);
  return (
    <div className="rounded-xl border border-white/10 bg-[#10162a] p-4">
      <p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-200">
        Knockout Bracket
      </p>
      {!poolComplete ? (
        <p className="mt-3 text-sm text-white/50">
          Top 8 teams qualify after the pool stage.
        </p>
      ) : !knockoutMatches.length ? (
        <div className="mt-3 grid gap-2">
          {qualifiers.map((team, index) => (
            <div
              key={team.name}
              className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm font-semibold"
            >
              {index + 1}. {team.name}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 grid gap-3">
          {visibleRounds.map((round) => (
            <div key={round}>
              <p className="mb-2 text-xs font-bold uppercase text-white/45">
                {round}
              </p>
              <div className="grid gap-2">
                {knockoutMatches
                  .filter((match) => match.stage === round)
                  .map((match) => (
                    <BracketMatch key={match.id} match={match} />
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function BracketMatch({ match }: { match: Match }) {
  return (
    <div className="rounded-lg border border-cyan-300/15 bg-black/20 px-3 py-2">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className={match.winner === match.home ? "font-black text-yellow-300" : "text-white"}>
          {match.home}
        </span>
        <span className="font-black text-white/80">
          {match.played ? `${match.homeScore}-${match.awayScore}` : "v"}
        </span>
        <span className={match.winner === match.away ? "font-black text-yellow-300" : "text-white"}>
          {match.away}
        </span>
      </div>
    </div>
  );
}

function ChampionScreen({
  draftedPlayers,
  finalMatch,
  matches,
  teamRating,
  teamName,
  onStartNewDraft,
}: {
  draftedPlayers: DraftPlayer[];
  finalMatch: Match;
  matches: Match[];
  teamRating: number;
  teamName: string;
  onStartNewDraft: () => void;
}) {
  const record = tournamentRecord(matches, teamName);
  return (
    <div className="p-5">
      <div className="rounded-2xl border border-yellow-300/40 bg-gradient-to-br from-yellow-300 via-orange-400 to-pink-500 p-6 text-neutral-950 shadow-[0_24px_80px_rgba(249,115,22,0.28)]">
        <div className="mx-auto h-24 w-24 rounded-b-full rounded-t-xl border-4 border-neutral-950/80 bg-yellow-100 shadow-xl" />
        <h3 className="mt-5 text-center text-4xl font-black uppercase">
          World Cup Champions
        </h3>
        <p className="mt-2 text-center text-2xl font-black">{teamName}</p>
        <p className="mt-2 text-center text-lg font-bold">
          Final: {finalMatch.home} {finalMatch.homeScore} - {finalMatch.awayScore}{" "}
          {finalMatch.away}
        </p>
        <p className="mt-1 text-center text-sm font-bold">
          Record {record.wins}-{record.losses} · PF {record.pointsFor} · PA{" "}
          {record.pointsAgainst} · Diff {record.pointsDifference > 0 ? "+" : ""}
          {record.pointsDifference} · Team rating {teamRating.toFixed(1)}
        </p>
      </div>
      <UserRecordPanel record={record} teamRating={teamRating} />
      <UserMatchJourney matches={matches} teamName={teamName} />
      <WinningXV players={draftedPlayers} />
      <div className="mt-5 text-center">
        <ActionButton onClick={onStartNewDraft}>Start New Draft</ActionButton>
      </div>
    </div>
  );
}

function EliminatedScreen({
  match,
  matches,
  teamName,
  teamRating,
  onStartNewDraft,
}: {
  match: Match;
  matches: Match[];
  teamName: string;
  teamRating: number;
  onStartNewDraft: () => void;
}) {
  const record = tournamentRecord(matches, teamName);
  const outcome = eliminationOutcome(match);
  return (
    <div className="p-5">
      <div className="rounded-2xl border border-rose-300/30 bg-[radial-gradient(circle_at_top,rgba(244,63,94,0.28),rgba(76,5,25,0.58))] p-6 text-center shadow-[0_24px_80px_rgba(0,0,0,0.36)]">
        <p className="text-xs font-black uppercase tracking-[0.18em] text-rose-200">
          Tournament Over
        </p>
        <h3 className="mt-2 text-3xl font-black text-white">{outcome}</h3>
        <p className="mt-2 text-xl font-black text-rose-100">{teamName}</p>
        <p className="mt-3 text-lg font-bold text-white">
          {match.home} {match.homeScore} - {match.awayScore} {match.away}
        </p>
        <p className="mt-1 text-sm text-rose-100">Winner: {match.winner}</p>
        <p className="mt-1 text-sm text-rose-100">
          Record {record.wins}-{record.losses} · PF {record.pointsFor} · PA{" "}
          {record.pointsAgainst} · Diff {record.pointsDifference > 0 ? "+" : ""}
          {record.pointsDifference} · Team rating {teamRating.toFixed(1)}
        </p>
        <div className="mt-5">
          <ActionButton onClick={onStartNewDraft}>Start New Draft</ActionButton>
        </div>
      </div>
      <UserRecordPanel record={record} teamRating={teamRating} />
      <UserMatchJourney matches={matches} teamName={teamName} />
    </div>
  );
}

function WinningXV({ players }: { players: DraftPlayer[] }) {
  return (
    <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.06] p-4">
      <p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-200">
        Winning Starting XV
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {players.map((player) => (
          <div
            key={`${player.pickNumber}-${player.playerName}`}
            className="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-sm"
          >
            <span className="font-black text-yellow-300">
              {player.pickNumber}. {player.selectedPosition}
            </span>{" "}
            <span className="font-semibold text-white">{player.playerName}</span>
            <span className="block text-xs text-white/50">
              {player.country} {player.year}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function UserRecordPanel({
  record,
  teamRating,
}: {
  record: ReturnType<typeof tournamentRecord>;
  teamRating: number;
}) {
  const metrics = [
    ["Wins", record.wins],
    ["Losses", record.losses],
    ["PF", record.pointsFor],
    ["PA", record.pointsAgainst],
    ["Diff", record.pointsDifference],
    ["Rating", Number(teamRating.toFixed(1))],
  ];
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {metrics.map(([label, value]) => (
        <div
          key={label}
          className="rounded-xl border border-cyan-300/15 bg-white/[0.06] px-4 py-3 text-center"
        >
          <p className="text-xs font-black uppercase tracking-[0.14em] text-cyan-200/70">
            {label}
          </p>
          <p className="mt-1 text-2xl font-black text-white">{value}</p>
        </div>
      ))}
    </div>
  );
}

function UserMatchJourney({
  matches,
  teamName,
}: {
  matches: Match[];
  teamName: string;
}) {
  return (
    <div className="mt-5 rounded-xl border border-white/10 bg-white/[0.06] p-4">
      <p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-200">
        Tournament Journey
      </p>
      <div className="mt-3 grid gap-2">
        {matches.map((match) => (
          <div
            key={match.id}
            className="grid gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-3 text-sm text-white sm:grid-cols-[110px_1fr_90px]"
          >
            <span className="font-bold text-white/55">{match.stage}</span>
            <span className="font-semibold">
              vs {opponentForMatch(match, teamName)}
            </span>
            <span
              className={
                match.winner === teamName
                  ? "font-black text-emerald-300"
                  : "font-black text-rose-300"
              }
            >
              {match.winner === teamName ? "W" : "L"}{" "}
              {userScoreLine(match, teamName)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActionButton({
  children,
  disabled = false,
  onClick,
  variant = "cyan",
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick: () => void;
  variant?: "cyan" | "orange" | "pink" | "yellow" | "teal";
}) {
  const classes = {
    cyan: "bg-cyan-300 text-neutral-950 hover:bg-cyan-200",
    orange: "bg-orange-400 text-neutral-950 hover:bg-orange-300",
    pink: "bg-pink-500 text-white hover:bg-pink-400",
    yellow: "bg-yellow-300 text-neutral-950 hover:bg-yellow-200",
    teal: "bg-teal-300 text-neutral-950 hover:bg-teal-200",
  };
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md px-3 py-2 text-xs font-black uppercase tracking-normal transition disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500 ${classes[variant]}`}
    >
      {children}
    </button>
  );
}

function createTeams(teamRating: number, teamName: string) {
  return POOLS.flat().map((team) =>
    team.isUser ? { ...team, name: teamName, rating: teamRating } : team,
  );
}

function createPoolMatches(teams: Team[]) {
  const matches: Match[] = [];
  for (const pool of ["A", "B", "C", "D", "E", "F"]) {
    const poolTeams = teams.filter((team) => team.pool === pool);
    for (let left = 0; left < poolTeams.length; left += 1) {
      for (let right = left + 1; right < poolTeams.length; right += 1) {
        matches.push({
          id: `pool-${pool}-${left}-${right}`,
          stage: `Pool ${pool}`,
          pool,
          home: poolTeams[left].name,
          away: poolTeams[right].name,
          homeRating: poolTeams[left].rating,
          awayRating: poolTeams[right].rating,
          played: false,
        });
      }
    }
  }
  return matches;
}

function calculateStandings(teams: Team[], matches: Match[]) {
  const byPool: Record<string, Standing[]> = {};
  for (const team of teams) {
    byPool[team.pool] ??= [];
    byPool[team.pool].push({
      team,
      played: 0,
      wins: 0,
      losses: 0,
      pointsFor: 0,
      pointsAgainst: 0,
      points: 0,
    });
  }
  const byTeam = new Map<string, Standing>();
  Object.values(byPool).flat().forEach((row) => byTeam.set(row.team.name, row));

  for (const match of matches) {
    if (!match.played || match.homeScore === undefined || match.awayScore === undefined) {
      continue;
    }
    applyResult(byTeam.get(match.home), match.homeScore, match.awayScore);
    applyResult(byTeam.get(match.away), match.awayScore, match.homeScore);
  }

  for (const pool of Object.keys(byPool)) {
    byPool[pool] = byPool[pool].sort(compareStandings);
  }
  return byPool;
}

function applyResult(row: Standing | undefined, pointsFor: number, pointsAgainst: number) {
  if (!row) {
    return;
  }
  row.played += 1;
  row.pointsFor += pointsFor;
  row.pointsAgainst += pointsAgainst;
  if (pointsFor > pointsAgainst) {
    row.wins += 1;
    row.points += 4;
  } else {
    row.losses += 1;
  }
}

function compareStandings(left: Standing, right: Standing) {
  const leftDiff = left.pointsFor - left.pointsAgainst;
  const rightDiff = right.pointsFor - right.pointsAgainst;
  return (
    right.points - left.points ||
    rightDiff - leftDiff ||
    right.pointsFor - left.pointsFor ||
    right.team.rating - left.team.rating
  );
}

function getQualifiers(standings: Record<string, Standing[]>) {
  // MVP qualification rule for six pools: top 8 overall by points, differential,
  // points scored, then rating. This keeps the bracket deterministic and clear.
  return Object.values(standings)
    .flatMap((rows) => rows)
    .sort(compareStandings)
    .slice(0, 8)
    .map((row) => row.team);
}

function createQuarterFinals(qualifiers: Team[]) {
  const pairings = [
    [0, 7],
    [3, 4],
    [1, 6],
    [2, 5],
  ];
  return pairings.map(([homeIndex, awayIndex], index) =>
    createKnockoutMatch(
      "Quarter-Final",
      index + 1,
      qualifiers[homeIndex],
      qualifiers[awayIndex],
    ),
  );
}

function addSemiFinals(matches: Match[], userTeamName: string) {
  const quarterFinals = matches.filter((match) => match.stage === "Quarter-Final");
  const hasSemiFinals = matches.some((match) => match.stage === "Semi-Final");
  if (hasSemiFinals) {
    return matches;
  }
  const winners = quarterFinals.map((match) =>
    teamFromWinner(match, userTeamName),
  );
  return [
    ...matches,
    createKnockoutMatch("Semi-Final", 1, winners[0], winners[1]),
    createKnockoutMatch("Semi-Final", 2, winners[2], winners[3]),
  ];
}

function addFinal(matches: Match[], userTeamName: string) {
  const semiFinals = matches.filter((match) => match.stage === "Semi-Final");
  const hasFinal = matches.some((match) => match.stage === "Final");
  if (hasFinal) {
    return matches;
  }
  const winners = semiFinals.map((match) => teamFromWinner(match, userTeamName));
  return [...matches, createKnockoutMatch("Final", 1, winners[0], winners[1])];
}

function stageToMatchStage(stageView: StageView): Match["stage"] | null {
  if (stageView === "quarter-final") {
    return "Quarter-Final";
  }
  if (stageView === "semi-final") {
    return "Semi-Final";
  }
  if (stageView === "final") {
    return "Final";
  }
  return null;
}

function completedStageForMatchStage(matchStage: string): StageView {
  if (matchStage === "Quarter-Final") {
    return "quarter-final-complete";
  }
  if (matchStage === "Semi-Final") {
    return "semi-final-complete";
  }
  return "final-complete";
}

function continueLabel(
  stageView: StageView,
  eliminated: Match | null,
  championMatch: Match | null,
) {
  if (stageView === "pool-complete") {
    return "Continue to Quarter-Finals";
  }
  if (stageView === "quarter-final-complete") {
    return "Continue to Semi-Finals";
  }
  if (stageView === "semi-final-complete") {
    return "Continue to Final";
  }
  if (stageView === "final-complete" || stageView === "summary-ready") {
    return championMatch || eliminated
      ? "View Tournament Summary"
      : "View Tournament Summary";
  }
  return null;
}

function visibleKnockoutRounds(matches: Match[], stageView: StageView) {
  const rounds = ["Quarter-Final", "Semi-Final", "Final"];
  return rounds.filter((round) =>
    matches.some((match) => match.stage === round)
    && (
      round !== "Final"
      || stageView === "final"
      || stageView === "final-complete"
      || stageView === "summary-ready"
      || stageView === "summary"
    ),
  );
}

function createKnockoutMatch(
  stage: string,
  index: number,
  home: Team,
  away: Team,
): Match {
  return {
    id: `${stage.toLowerCase().replaceAll(" ", "-")}-${index}`,
    stage,
    home: home.name,
    away: away.name,
    homeRating: home.rating,
    awayRating: away.rating,
    played: false,
  };
}

function teamFromWinner(match: Match, userTeamName: string): Team {
  const winnerIsHome = match.winner === match.home;
  return {
    name: match.winner ?? match.home,
    rating: winnerIsHome ? match.homeRating : match.awayRating,
    pool: "",
    isUser: match.winner === userTeamName,
  };
}

function playKnockoutMatchInList(matches: Match[], matchId: string) {
  return matches.map((match) =>
    match.id === matchId && !match.played ? simulateMatch(match) : match,
  );
}

function simulateMatch(match: Match): Match {
  const probability = winProbability(match.homeRating, match.awayRating);
  const homeWins = Math.random() < probability;
  const ratingGap = Math.abs(match.homeRating - match.awayRating);
  const margin = Math.max(1, Math.round(3 + ratingGap * 0.75 + Math.random() * 18));
  const loserScore = Math.round(10 + Math.random() * 18);
  const winnerScore = loserScore + margin;
  return {
    ...match,
    played: true,
    homeScore: homeWins ? winnerScore : loserScore,
    awayScore: homeWins ? loserScore : winnerScore,
    winner: homeWins ? match.home : match.away,
  };
}

function winProbability(homeRating: number, awayRating: number) {
  return Math.max(0.1, Math.min(0.9, 0.5 + (homeRating - awayRating) * 0.035));
}

function resultText(match: Match) {
  return `${match.stage}: ${match.home} ${match.homeScore}-${match.awayScore} ${match.away}. Winner: ${match.winner}.`;
}

function normaliseTeamName(value?: string | null) {
  return String(value ?? "").trim().toLowerCase();
}

function isUserMatch(match: Match | null | undefined, userTeamName: string) {
  if (!match) {
    return false;
  }
  const user = normaliseTeamName(userTeamName);
  if (!user) {
    return false;
  }
  return (
    normaliseTeamName(match.home) === user ||
    normaliseTeamName(match.away) === user
  );
}

function tournamentRecord(matches: Match[], teamName: string) {
  return matches.reduce(
    (record, match) => {
      if (!isUserMatch(match, teamName)) {
        return record;
      }
      const userIsHome = normaliseTeamName(match.home) === normaliseTeamName(teamName);
      const pointsFor =
        userIsHome ? match.homeScore ?? 0 : match.awayScore ?? 0;
      const pointsAgainst =
        userIsHome ? match.awayScore ?? 0 : match.homeScore ?? 0;
      record.pointsFor += pointsFor;
      record.pointsAgainst += pointsAgainst;
      record.pointsDifference = record.pointsFor - record.pointsAgainst;
      if (match.winner === teamName) {
        record.wins += 1;
      } else {
        record.losses += 1;
      }
      return record;
    },
    { wins: 0, losses: 0, pointsFor: 0, pointsAgainst: 0, pointsDifference: 0 },
  );
}

function opponentForMatch(match: Match, teamName: string) {
  return normaliseTeamName(match.home) === normaliseTeamName(teamName)
    ? match.away
    : match.home;
}

function userScoreLine(match: Match, teamName: string) {
  const userIsHome = normaliseTeamName(match.home) === normaliseTeamName(teamName);
  const pointsFor =
    userIsHome ? match.homeScore ?? 0 : match.awayScore ?? 0;
  const pointsAgainst =
    userIsHome ? match.awayScore ?? 0 : match.homeScore ?? 0;
  return `${pointsFor}-${pointsAgainst}`;
}

function eliminationOutcome(match: Match) {
  if (match.stage === "Pool Stage") {
    return "Eliminated in Pool Stage";
  }
  if (match.stage === "Final") {
    return "Runner-Up";
  }
  return `Eliminated in ${match.stage}s`;
}

function sleep(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function userLost(match: Match | undefined, userTeamName: string) {
  return Boolean(
    match?.played &&
      (match.home === userTeamName || match.away === userTeamName) &&
      match.winner !== userTeamName,
  );
}
