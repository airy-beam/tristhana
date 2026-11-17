import { useState } from "react";

import { useStats, type Stats } from "../../api/client";
import { monthOf } from "./cells";

/** One year of stats; `year` null = the current one. While another year loads, the year that
 * was on screen stays (`stats`), so a step over New Year never empties the screen. `today` is
 * the server's, when the caller already has it. */
export function useKeptStats(year: number | null, today?: string) {
  const [kept, setKept] = useState<Stats>();
  const now = today ?? kept?.today;
  // The current year is cached as "current": coming back to it needs no refetch.
  const current = year === null || (now !== undefined && year === monthOf(now).year);
  const query = useStats(current ? undefined : year);
  if (query.data && query.data !== kept) setKept(query.data);
  return { stats: query.data ?? kept, failed: query.isError };
}
