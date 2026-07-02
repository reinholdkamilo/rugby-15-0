const GAME_POSITION_ORDER = [
  "LH",
  "HK",
  "TH",
  "LK",
  "BF",
  "OF",
  "NE",
  "SH",
  "FH",
  "IC",
  "OC",
  "WG",
  "FB",
  "TBC",
];

const PLAYABLE_POSITION_CODES = [
  "LH",
  "HK",
  "TH",
  "LK",
  "BF",
  "OF",
  "NE",
  "SH",
  "FH",
  "IC",
  "OC",
  "WG",
  "FB",
];

const POSITION_ALIASES: Record<string, string> = {
  LOCK: "LK",
  LK4: "LK",
  LK5: "LK",
  BSF: "BF",
  BF: "BF",
  OSF: "OF",
  OF: "OF",
  N8: "NE",
  NE: "NE",
  LW: "WG",
  RW: "WG",
  W: "WG",
  WG: "WG",
};

const EXPANSION_GROUPS = [
  ["FH", "FB", "IC"],
  ["OF", "BF", "NE"],
  ["LH", "TH"],
];

export function toGamePositionCode(positionCode: string | null | undefined) {
  if (!positionCode) {
    return "";
  }
  const code = positionCode.trim().toUpperCase();
  return POSITION_ALIASES[code] ?? code;
}

export function orderGamePositions(positionCodes: Iterable<string>) {
  const uniqueCodes = new Set(
    [...positionCodes].map(toGamePositionCode).filter(Boolean),
  );

  return [...uniqueCodes].sort((left, right) => {
    const leftIndex = GAME_POSITION_ORDER.includes(left)
      ? GAME_POSITION_ORDER.indexOf(left)
      : GAME_POSITION_ORDER.length;
    const rightIndex = GAME_POSITION_ORDER.includes(right)
      ? GAME_POSITION_ORDER.indexOf(right)
      : GAME_POSITION_ORDER.length;
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex;
    }
    return left.localeCompare(right);
  });
}

export function expandPositionEligibility(positionCodes: Iterable<string>) {
  const expanded = new Set(orderGamePositions(positionCodes));

  EXPANSION_GROUPS.forEach((group) => {
    if (group.some((positionCode) => expanded.has(positionCode))) {
      group.forEach((positionCode) => expanded.add(positionCode));
    }
  });

  return orderGamePositions(expanded);
}

export function expandPositionEligibilityForDraft(
  positionCodes: Iterable<string>,
) {
  const expanded = expandPositionEligibility(positionCodes);
  if (expanded.includes("TBC")) {
    return PLAYABLE_POSITION_CODES.slice();
  }
  return expanded;
}

export function isSameGamePosition(left: string, right: string) {
  return toGamePositionCode(left) === toGamePositionCode(right);
}
