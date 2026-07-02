import { PlayerTile } from "@/components/PlayerTile";
import { RugbyField } from "@/components/RugbyField";

export type ActivePositionFilter = {
  positionCode: string;
  slotNumber: number;
} | null;

export type FieldPick = {
  country: string;
  slotNumber: number;
  positionCode: string;
  player_name: string;
  position: string;
  year: number;
  rating: number | null;
};

export type FieldSlot = {
  slotNumber: number;
  positionCode: string;
  displayCode: string;
  positionName: string;
};

type FieldRow = {
  label: string;
  slots: FieldSlot[];
};

const FIELD_ROWS: FieldRow[] = [
  {
    label: "Front row",
    slots: [
      {
        slotNumber: 1,
        positionCode: "LH",
        displayCode: "LH",
        positionName: "Loosehead Prop",
      },
      {
        slotNumber: 2,
        positionCode: "HK",
        displayCode: "HK",
        positionName: "Hooker",
      },
      {
        slotNumber: 3,
        positionCode: "TH",
        displayCode: "TH",
        positionName: "Tighthead Prop",
      },
    ],
  },
  {
    label: "Second row",
    slots: [
      {
        slotNumber: 4,
        positionCode: "LK4",
        displayCode: "LK",
        positionName: "Lock",
      },
      {
        slotNumber: 5,
        positionCode: "LK5",
        displayCode: "LK",
        positionName: "Lock",
      },
    ],
  },
  {
    label: "Back row",
    slots: [
      {
        slotNumber: 6,
        positionCode: "BSF",
        displayCode: "BF",
        positionName: "Blindside Flanker",
      },
      {
        slotNumber: 8,
        positionCode: "N8",
        displayCode: "NE",
        positionName: "Number 8",
      },
      {
        slotNumber: 7,
        positionCode: "OSF",
        displayCode: "OF",
        positionName: "Openside Flanker",
      },
    ],
  },
  {
    label: "Halves",
    slots: [
      {
        slotNumber: 9,
        positionCode: "SH",
        displayCode: "SH",
        positionName: "Scrumhalf",
      },
      {
        slotNumber: 10,
        positionCode: "FH",
        displayCode: "FH",
        positionName: "Flyhalf",
      },
    ],
  },
  {
    label: "Backline",
    slots: [
      {
        slotNumber: 11,
        positionCode: "LW",
        displayCode: "WG",
        positionName: "Left Wing",
      },
      {
        slotNumber: 12,
        positionCode: "IC",
        displayCode: "IC",
        positionName: "Inside Centre",
      },
      {
        slotNumber: 13,
        positionCode: "OC",
        displayCode: "OC",
        positionName: "Outside Centre",
      },
      {
        slotNumber: 14,
        positionCode: "RW",
        displayCode: "WG",
        positionName: "Right Wing",
      },
    ],
  },
  {
    label: "Backfield",
    slots: [
      {
        slotNumber: 15,
        positionCode: "FB",
        displayCode: "FB",
        positionName: "Fullback",
      },
    ],
  },
];

export function RugbyFieldLayout({
  picks,
  activePositionFilter,
  onPositionClick,
}: {
  picks: FieldPick[];
  activePositionFilter: ActivePositionFilter;
  onPositionClick: (positionCode: string, slotNumber: number) => void;
}) {
  const picksBySlot = new Map(
    picks.map((pick) => [pick.slotNumber, pick] as const),
  );

  return (
    <section className="overflow-hidden rounded-xl border border-cyan-300/15 bg-[#050b18] p-4 shadow-[0_24px_70px_rgba(0,0,0,0.42)]">
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-cyan-200/10 pb-4">
        <div>
          <h2 className="text-xl font-black uppercase tracking-[0.18em] text-white">
            Starting XV
          </h2>
          <p className="mt-1 text-xs font-semibold uppercase tracking-[0.12em] text-cyan-200/70">
            Build your ultimate Rugby World Cup team
          </p>
        </div>
        {activePositionFilter ? (
          <span className="rounded-md border border-cyan-300/40 bg-cyan-400/10 px-3 py-1 text-xs font-semibold text-cyan-100">
            Slot {activePositionFilter.slotNumber}
          </span>
        ) : null}
      </div>

      <RugbyField>
          {FIELD_ROWS.map((row) => (
            <div key={row.label}>
              <div className="flex justify-center gap-3">
                {row.slots.map((slot) => {
                  const pick = picksBySlot.get(slot.slotNumber);
                  const isActive =
                    activePositionFilter?.slotNumber === slot.slotNumber;
                  return (
                    <button
                      key={slot.slotNumber}
                      type="button"
                      onClick={() =>
                        onPositionClick(slot.positionCode, slot.slotNumber)
                      }
                      className="rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-yellow-100"
                    >
                      <PlayerTile
                        displayCode={slot.displayCode}
                        isActive={isActive}
                        pick={pick}
                        slotNumber={slot.slotNumber}
                      />
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
      </RugbyField>
    </section>
  );
}
