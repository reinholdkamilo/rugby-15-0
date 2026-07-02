"use client";

import { useEffect, useState } from "react";

import { getCountryFlag } from "@/lib/countryFlags";

const COUNTRIES = [
  "New Zealand",
  "South Africa",
  "Australia",
  "England",
  "France",
  "Ireland",
  "Wales",
  "Scotland",
  "Argentina",
  "Fiji",
  "Japan",
  "Italy",
  "Samoa",
  "Tonga",
  "United States",
  "Canada",
  "Uruguay",
  "Namibia",
  "Georgia",
  "Romania",
  "Russia",
  "Spain",
  "Portugal",
  "Chile",
  "Zimbabwe",
  "Ivory Coast",
];

const YEARS = [1987, 1991, 1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023];
const REVEAL_DURATION_MS = 1900;

export function SpinRevealAnimation({
  isSpinning,
  finalCountry,
  finalYear,
  onComplete,
}: {
  isSpinning: boolean;
  finalCountry?: string;
  finalYear?: number;
  onComplete?: () => void;
}) {
  const [displayCountry, setDisplayCountry] = useState("New Zealand");
  const [displayYear, setDisplayYear] = useState(2023);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateReducedMotion = () => setReducedMotion(mediaQuery.matches);
    updateReducedMotion();
    mediaQuery.addEventListener("change", updateReducedMotion);
    return () => mediaQuery.removeEventListener("change", updateReducedMotion);
  }, []);

  useEffect(() => {
    if (!isSpinning) {
      return;
    }

    if (reducedMotion) {
      const timeoutId = window.setTimeout(() => {
        setDisplayCountry(finalCountry ?? randomCountry());
        setDisplayYear(finalYear ?? randomYear());
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }

    let cancelled = false;
    let timeoutId: number | undefined;
    const start = performance.now();

    const tick = () => {
      if (cancelled) {
        return;
      }

      const elapsed = performance.now() - start;
      const progress = Math.min(elapsed / REVEAL_DURATION_MS, 1);
      const hasFinalTarget = Boolean(finalCountry && finalYear);
      const shouldSettle = progress > 0.82 && hasFinalTarget;

      if (shouldSettle) {
        setDisplayCountry(finalCountry as string);
        setDisplayYear(finalYear as number);
      } else {
        setDisplayCountry(randomCountry());
        setDisplayYear(randomYear());
      }

      if (progress >= 1) {
        if (hasFinalTarget) {
          setDisplayCountry(finalCountry as string);
          setDisplayYear(finalYear as number);
        }
        onComplete?.();
        return;
      }

      const nextDelay =
        progress < 0.55 ? 55 : progress < 0.8 ? 92 : 145;
      timeoutId = window.setTimeout(tick, nextDelay);
    };

    tick();

    return () => {
      cancelled = true;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [finalCountry, finalYear, isSpinning, onComplete, reducedMotion]);

  return (
    <div
      aria-live="polite"
      className="overflow-hidden rounded-md border border-neutral-800 bg-neutral-950 p-4"
    >
      <p className="text-sm font-medium text-neutral-400">
        {reducedMotion ? "Revealing squad" : "Current squad"}
      </p>
      <div className="mt-1 text-2xl font-bold text-white">
        {displayCountry} {displayYear}
      </div>
      <div className="mt-4 flex max-h-[620px] flex-col gap-2 overflow-hidden">
        <div className="relative overflow-hidden rounded-md border border-cyan-300/25 bg-neutral-900/80 px-3 py-2 shadow-[0_0_0_1px_rgba(34,211,238,0.05),inset_0_0_18px_rgba(0,0,0,0.32)]">
          <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(34,211,238,0.05),transparent_30%,transparent_70%,rgba(34,211,238,0.04))]" />
          <div className="relative flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-white">
                {getCountryFlag(displayCountry)} {displayCountry.toUpperCase()}
              </div>
              <div className="mt-1 text-xs text-neutral-400">
                {reducedMotion
                  ? "Loading next squad"
                  : finalCountry && finalYear
                    ? "Locking in final squad"
                    : "Cycling World Cup squads"}
              </div>
            </div>
            <div className="shrink-0 text-sm font-bold text-cyan-200">
              {displayYear}
            </div>
          </div>
        </div>

        <div className="rounded-md border border-dashed border-neutral-700 bg-neutral-950 px-4 py-6 text-sm text-neutral-400">
          {reducedMotion ? "Revealing squad..." : "Spinning squads..."}
        </div>
      </div>
    </div>
  );
}

function randomCountry() {
  return COUNTRIES[Math.floor(Math.random() * COUNTRIES.length)];
}

function randomYear() {
  return YEARS[Math.floor(Math.random() * YEARS.length)];
}
