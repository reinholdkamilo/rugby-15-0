const COUNTRY_FLAGS: Record<string, string> = {
  "new zealand": "🇳🇿",
  "south africa": "🇿🇦",
  australia: "🇦🇺",
  england: "🏴",
  france: "🇫🇷",
  ireland: "🇮🇪",
  wales: "🏴",
  scotland: "🏴",
  argentina: "🇦🇷",
  fiji: "🇫🇯",
  japan: "🇯🇵",
  italy: "🇮🇹",
  samoa: "🇼🇸",
  "western samoa": "🇼🇸",
  tonga: "🇹🇴",
  "united states": "🇺🇸",
  "united states of america": "🇺🇸",
  usa: "🇺🇸",
  canada: "🇨🇦",
  uruguay: "🇺🇾",
  namibia: "🇳🇦",
  georgia: "🇬🇪",
  romania: "🇷🇴",
  russia: "🇷🇺",
  spain: "🇪🇸",
  portugal: "🇵🇹",
  chile: "🇨🇱",
  zimbabwe: "🇿🇼",
  "ivory coast": "🇨🇮",
  "cote d'ivoire": "🇨🇮",
};

export function getCountryFlag(countryName: string): string {
  return COUNTRY_FLAGS[normaliseCountryName(countryName)] ?? "🏳️";
}

function normaliseCountryName(countryName: string): string {
  return countryName
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\u2019/g, "'")
    .trim()
    .toLowerCase();
}
