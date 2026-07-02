import { getCountryFlag } from "@/lib/countryFlags";

export type PlayerTilePick = {
  country: string;
  player_name: string;
  position: string;
  year: number;
  rating: number | null;
};

export function PlayerTile({
  displayCode,
  isActive,
  pick,
  slotNumber,
}: {
  displayCode: string;
  isActive: boolean;
  pick?: PlayerTilePick;
  slotNumber: number;
}) {
  const isFilled = Boolean(pick);
  const formattedName = pick ? formatPlayerName(pick.player_name) : "";

  return (
    <div className={tileClassName(isFilled, isActive)}>
      {pick ? (
        <>
          <div className="pointer-events-none absolute inset-0 rounded-lg bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,0.18),transparent_34%),linear-gradient(135deg,rgba(255,255,255,0.1),transparent_40%),linear-gradient(0deg,rgba(8,13,24,0.18),rgba(8,13,24,0.18))]" />
          <div className="relative z-10 flex h-full min-w-0 flex-col">
            <div className="flex items-start justify-between text-[12px] font-black leading-none text-cyan-50/95">
              <span>{slotNumber}</span>
              <span className="text-sm leading-none drop-shadow-sm">
                {getCountryFlag(pick.country)}
              </span>
            </div>
            <div className="mt-1 flex min-h-0 flex-1 flex-col items-center justify-center">
              <span
                className="block h-4 w-full min-w-0 truncate text-center text-[13px] font-black leading-4 text-white opacity-100 drop-shadow-[0_1px_2px_rgba(0,0,0,0.9)]"
                title={formattedName}
              >
                {formattedName}
              </span>
              <span className="mt-1 block text-center text-2xl font-black leading-none text-yellow-200 drop-shadow-[0_1px_8px_rgba(250,204,21,0.32)]">
                {pick.rating === null ? "--" : Math.round(pick.rating)}
              </span>
              <span className="mt-1 block text-center text-[11px] font-bold leading-none text-slate-200/75">
                {pick.year}
              </span>
            </div>
          </div>
        </>
      ) : (
        <span className="flex h-full w-full items-center justify-center text-2xl font-black text-white/50">
          {displayCode}
        </span>
      )}
    </div>
  );
}

export function formatPlayerName(playerName: string): string {
  const parts = playerName.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) {
    return "";
  }
  if (parts.length === 1) {
    return truncateSurname(parts[0]);
  }

  const initial = `${parts[0][0].toUpperCase()}.`;
  return `${initial} ${truncateSurname(parts[parts.length - 1])}`;
}

function truncateSurname(surname: string): string {
  const maxLength = 12;
  if (surname.length <= maxLength) {
    return surname;
  }
  return `${surname.slice(0, maxLength - 3)}...`;
}

function tileClassName(isFilled: boolean, isActive: boolean): string {
  const base =
    "relative h-24 w-32 shrink-0 overflow-hidden rounded-lg border px-2.5 py-2 transition duration-200 ease-out";

  if (isActive && isFilled) {
    return `${base} motion-safe:animate-[draftTileIn_260ms_ease-out] border-yellow-200 bg-[linear-gradient(145deg,#111827_0%,#172033_52%,#050814_100%)] text-white shadow-[0_0_0_2px_rgba(254,240,138,0.72),0_20px_42px_rgba(0,0,0,0.62),0_0_28px_rgba(250,204,21,0.22),inset_0_1px_0_rgba(255,255,255,0.16)] ring-2 ring-yellow-100 hover:-translate-y-1 hover:scale-[1.015]`;
  }

  if (isActive) {
    return `${base} border-yellow-200 bg-yellow-300/10 text-white/70 shadow-[0_0_20px_rgba(254,240,138,0.28)] ring-2 ring-yellow-100/70`;
  }

  if (isFilled) {
    return `${base} motion-safe:animate-[draftTileIn_260ms_ease-out] border-cyan-100/35 bg-[linear-gradient(145deg,#111827_0%,#172033_52%,#050814_100%)] text-white shadow-[0_18px_36px_rgba(0,0,0,0.58),0_0_20px_rgba(34,211,238,0.16),inset_0_1px_0_rgba(255,255,255,0.14)] hover:-translate-y-1 hover:scale-[1.015] hover:border-yellow-100/80 hover:shadow-[0_22px_46px_rgba(0,0,0,0.64),0_0_24px_rgba(250,204,21,0.18)]`;
  }

  return `${base} border-cyan-300/70 bg-[#060d1d]/90 text-white/60 shadow-[0_0_14px_rgba(0,179,255,0.5),inset_0_0_20px_rgba(0,0,0,0.58)] hover:border-cyan-200/90 hover:bg-[#081328]/90 hover:text-white/80 hover:shadow-[0_0_20px_rgba(0,179,255,0.68),inset_0_0_20px_rgba(0,0,0,0.58)]`;
}
