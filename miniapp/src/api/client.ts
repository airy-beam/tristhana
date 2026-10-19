import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import createClient from "openapi-fetch";

import { rawInitData } from "../telegram";
import type { components, paths } from "./schema";

// Typed client generated from the backend contract (ADR-0013); never hand-write API types.
// Empty base URL in dev: /api is proxied to the local backend.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  // Resolve fetch per call (openapi-fetch would capture it once at import), so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});

// Every request carries the signed Telegram initData; the API verifies it (ADR-0015).
api.use({
  onRequest({ request }) {
    const raw = rawInitData();
    if (raw) request.headers.set("Authorization", `tma ${raw}`);
    return request;
  },
});

export type Health = components["schemas"]["Health"];
export type Me = components["schemas"]["Me"];
export type ErrorCode = components["schemas"]["ErrorCode"];

/** A non-2xx answer from the API, with the stable `code` when the body has one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: ErrorCode | null,
  ) {
    super(`API ${String(status)}${code ? ` ${code}` : ""}`);
  }
}

function fail(response: Response, error: unknown): never {
  const code =
    error !== null && typeof error === "object" && "code" in error
      ? (error.code as ErrorCode)
      : null;
  throw new ApiError(response.status, code);
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async (): Promise<Health> => {
      const { data } = await api.GET("/api/v1/health");
      if (!data) throw new Error("health request failed");
      return data;
    },
    staleTime: 60_000,
  });
}

/** The caller's account; the first call creates it (ID-01). */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Me> => {
      const { data, error, response } = await api.GET("/api/v1/me");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: Infinity,
    // An expired or invalid session won't fix itself by retrying.
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 1,
  });
}

/** Reports the device zone; the server keeps it only if none is set yet. */
export function useReportDeviceTimezone() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (timezone: string): Promise<Me> => {
      const { data, error, response } = await api.POST("/api/v1/me/device-timezone", {
        body: { timezone },
      });
      if (!data) fail(response, error);
      return data;
    },
    onSuccess: (me) => {
      client.setQueryData(["me"], me);
      // "Today" may have been computed in the provisional zone before this landed.
      void client.invalidateQueries({ queryKey: ["days"] });
    },
  });
}

export type DayStatus = components["schemas"]["DayStatus"];
export type Days = components["schemas"]["Days"];

/** Grid order as in the bot: Practiced first, "No practice" last (ashtanga-expert). */
export const DAY_STATUSES: readonly DayStatus[] = [
  "practiced",
  "rest",
  "moon",
  "ladies",
  "sick",
  "travel",
  "skipped",
];

const DAYS_KEY = ["days", "recent"] as const;

/** Day-scope mutations run one at a time, but each `onMutate` (optimistic update) runs at
 * tap time; so after the last queued one settles (or the server refused with a conflict),
 * refetch, and the cache matches the server whatever the order of failures was. */
function settleDays(client: ReturnType<typeof useQueryClient>, error: unknown): void {
  const queued = client.isMutating({ predicate: (m) => m.options.scope?.id === "day" });
  if (queued <= 1 || (error instanceof ApiError && error.status === 409)) {
    // Every day query (recent, ranges for the day editor) and the stats built on them.
    void client.invalidateQueries({ queryKey: ["days"] });
    void client.invalidateQueries({ queryKey: STATS_KEY });
  }
}

const STATS_KEY = ["stats"] as const;
export type Stats = components["schemas"]["StatsOut"];
export type StatsSummary = components["schemas"]["SummaryOut"];

/** One year of stats (ST-01..03); `year` undefined = the local current year. */
export function useStats(year: number | undefined) {
  return useQuery({
    queryKey: [...STATS_KEY, year ?? "current"],
    queryFn: async (): Promise<Stats> => {
      const { data, error, response } = await api.GET("/api/v1/me/stats", {
        params: { query: year === undefined ? {} : { year } },
      });
      if (!data) fail(response, error);
      return data;
    },
    staleTime: 60_000,
  });
}

/** Logged days in [from, to] (the day editor on the stats screen). */
export function useDaysRange(from: string, to: string) {
  return useQuery({
    queryKey: ["days", "range", from, to],
    queryFn: async (): Promise<Days> => {
      const { data, error, response } = await api.GET("/api/v1/me/days", {
        params: { query: { from, to } },
      });
      if (!data) fail(response, error);
      return data;
    },
    staleTime: 60_000,
  });
}

/** The last 7 days and the server's "today" (PR-01). */
export function useDays() {
  return useQuery({
    queryKey: DAYS_KEY,
    queryFn: async (): Promise<Days> => {
      const { data, error, response } = await api.GET("/api/v1/me/days");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: 60_000,
  });
}

function withDay(days: Days, date: string, status: DayStatus | null): Days {
  const before = days.days.find((d) => d.date === date);
  const others = days.days.filter((d) => d.date !== date);
  // Details live only on a practiced day (the server drops them on any other status).
  const practices = status === "practiced" ? (before?.practices ?? []) : [];
  const next = status ? [...others, { date, status, practices }] : others;
  return { ...days, days: next.sort((a, b) => a.date.localeCompare(b.date)) };
}

type Snapshot = [readonly unknown[], Days | undefined][];

/** Applies `change` optimistically to every cached day query (the recent week and the
 * stats day editor's ranges; a range only gets days inside it) and returns what to
 * restore if the server refuses. */
async function patchDays(
  client: ReturnType<typeof useQueryClient>,
  date: string,
  change: (days: Days) => Days,
): Promise<Snapshot> {
  await client.cancelQueries({ queryKey: ["days"] });
  const before = client.getQueriesData<Days>({ queryKey: ["days"] });
  for (const [key, days] of before) {
    const [, kind, from, to] = key as [string, string, string?, string?];
    const inside =
      kind !== "range" || (from !== undefined && to !== undefined && from <= date && date <= to);
    if (days && inside) client.setQueryData(key, change(days));
  }
  return before;
}

function restore(client: ReturnType<typeof useQueryClient>, snapshot: Snapshot | undefined) {
  for (const [key, days] of snapshot ?? []) client.setQueryData(key, days);
}

/** Sets (status) or clears (null) a day, optimistically; rolls back if the server refuses. */
export function useSetDay() {
  const client = useQueryClient();
  return useMutation({
    scope: { id: "day" }, // one request at a time, in tap order
    onSettled: (_data, error) => {
      settleDays(client, error);
    },
    mutationFn: async ({ date, status }: { date: string; status: DayStatus | null }) => {
      const params = { path: { date } };
      const { error, response } = status
        ? await api.PUT("/api/v1/me/days/{date}", { params, body: { status } })
        : await api.DELETE("/api/v1/me/days/{date}", { params });
      if (!response.ok) fail(response, error);
    },
    onMutate: async ({ date, status }) => ({
      before: await patchDays(client, date, (days) => withDay(days, date, status)),
    }),
    onError: (_error, _vars, context) => {
      restore(client, context?.before);
    },
  });
}

export type Practice = components["schemas"]["PracticeOut"];
export type PracticeBody = components["schemas"]["PracticeBody"];
export type Length = components["schemas"]["Length"];
export type PracticeContext = components["schemas"]["PracticeContext"];
export type Catalog = components["schemas"]["CatalogOut"];
export type PracticePresets = components["schemas"]["PracticePresets"];

/** Series and stop points for the length picker (public, ETag-cached). */
export function useCatalog() {
  return useQuery({
    queryKey: ["catalog"],
    queryFn: async (): Promise<Catalog> => {
      const { data, error, response } = await api.GET("/api/v1/catalog");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: Infinity,
  });
}

/** "Same as last time" and the length presets for a day (PR-03). */
export function usePracticePresets(date: string, enabled: boolean) {
  return useQuery({
    queryKey: ["practice-presets", date],
    enabled,
    queryFn: async (): Promise<PracticePresets> => {
      const { data, error, response } = await api.GET("/api/v1/me/days/{date}/practice-presets", {
        params: { path: { date } },
      });
      if (!data) fail(response, error);
      return data;
    },
    staleTime: 60_000,
  });
}

function withPractice(days: Days, date: string, practice: Practice | null): Days {
  return {
    ...days,
    days: days.days.map((d) =>
      d.date === date ? { ...d, practices: practice ? [practice] : [] } : d,
    ),
  };
}

/** Replaces (body) or removes (null) the day's practice details, optimistically. */
export function useSavePractice() {
  const client = useQueryClient();
  return useMutation({
    scope: { id: "day" }, // in tap order with status changes
    mutationFn: async ({
      date,
      body,
    }: {
      date: string;
      body: PracticeBody | null;
    }): Promise<Practice | null> => {
      const params = { path: { date, slot: 1 } };
      if (!body) {
        const { error, response } = await api.DELETE("/api/v1/me/days/{date}/practices/{slot}", {
          params,
        });
        if (!response.ok) fail(response, error);
        return null;
      }
      const { data, error, response } = await api.PUT("/api/v1/me/days/{date}/practices/{slot}", {
        params,
        body,
      });
      if (!data) fail(response, error);
      return data;
    },
    onMutate: async ({ date, body }) => {
      const practice = body ? { slot: 1, timezone: null, ...body } : null;
      return {
        before: await patchDays(client, date, (days) => withPractice(days, date, practice)),
      };
    },
    onSuccess: (saved, { date }) => {
      // The server's normalised practice (e.g. a full series, the stored zone) wins.
      client.setQueriesData<Days>({ queryKey: ["days"] }, (days) =>
        days ? withPractice(days, date, saved) : days,
      );
    },
    onError: (_error, _vars, context) => {
      restore(client, context?.before);
    },
    onSettled: (_data, error) => {
      settleDays(client, error);
    },
  });
}

export type MoonDays = components["schemas"]["MoonDays"];
export type City = components["schemas"]["CityOut"];
export type NotificationSettings = components["schemas"]["NotificationSettingsOut"];

const MOON_KEY = ["moon-days"] as const;
const SETTINGS_KEY = ["notification-settings"] as const;

/** The cities whose moon calendars can be followed (public, ETag-cached). */
export function useMoonCities() {
  return useQuery({
    queryKey: ["moon-cities"],
    queryFn: async (): Promise<City[]> => {
      const { data, error, response } = await api.GET("/api/v1/moon/cities");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: Infinity,
  });
}

/** Upcoming moon days of the followed city (MD-03). */
export function useMoonDays() {
  return useQuery({
    queryKey: MOON_KEY,
    queryFn: async (): Promise<MoonDays> => {
      const { data, error, response } = await api.GET("/api/v1/me/moon-days");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: 10 * 60_000,
  });
}

export function useNotificationSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: async (): Promise<NotificationSettings> => {
      const { data, error, response } = await api.GET("/api/v1/me/notification-settings");
      if (!data) fail(response, error);
      return data;
    },
    staleTime: Infinity,
  });
}

/** Follow another city's moon calendar; the days are refetched for it. */
export function useSetMoonLocation() {
  const client = useQueryClient();
  return useMutation({
    scope: { id: "settings" },
    mutationFn: async (slug: string) => {
      const { data, error, response } = await api.PUT("/api/v1/me/moon-location", {
        body: { slug },
      });
      if (!data) fail(response, error);
      return data;
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: MOON_KEY });
    },
  });
}

export type SettingsPatch = components["schemas"]["NotificationSettingsPatch"];

/** What the settings look like after `patch` (the optimistic view; the server's answer wins). */
function merged(settings: NotificationSettings, patch: SettingsPatch): NotificationSettings {
  const { moon, quiet, daily_cap, practice } = patch;
  return {
    ...settings,
    moon: moon
      ? {
          offsets: moon.offsets ?? settings.moon.offsets,
          at: moon.at ?? settings.moon.at,
        }
      : settings.moon,
    quiet: quiet ?? settings.quiet,
    daily_cap: daily_cap ?? settings.daily_cap,
    practice: practice
      ? {
          on: practice.on !== undefined ? practice.on : settings.practice.on,
          at: practice.at ?? settings.practice.at,
          days: practice.days ?? settings.practice.days,
        }
      : settings.practice,
  };
}

/** Changes only what was tapped (ADR-0021), optimistically; the server's answer wins. */
export function usePatchNotificationSettings() {
  const client = useQueryClient();
  return useMutation({
    scope: { id: "settings" },
    mutationFn: async (body: SettingsPatch): Promise<NotificationSettings> => {
      const { data, error, response } = await api.PATCH("/api/v1/me/notification-settings", {
        body,
      });
      if (!data) fail(response, error);
      return data;
    },
    onMutate: async (body) => {
      await client.cancelQueries({ queryKey: SETTINGS_KEY });
      const before = client.getQueryData<NotificationSettings>(SETTINGS_KEY);
      if (before) client.setQueryData(SETTINGS_KEY, merged(before, body));
      return { before };
    },
    onSuccess: (saved) => {
      // A later tap may still be queued: its optimistic state wins until it settles.
      const queued = client.isMutating({ predicate: (m) => m.options.scope?.id === "settings" });
      if (queued <= 1) client.setQueryData(SETTINGS_KEY, saved);
    },
    onError: (_error, _vars, context) => {
      if (context?.before) client.setQueryData(SETTINGS_KEY, context.before);
    },
  });
}

export type MePatch = components["schemas"]["MePatch"];

/** Name, language or time zone (ID-06). A zone change moves "today" and the reminders, so
 * everything computed from it is refetched. */
export function usePatchMe() {
  const client = useQueryClient();
  return useMutation({
    scope: { id: "me" }, // a name and a language tapped together go in order
    mutationFn: async (body: MePatch): Promise<Me> => {
      const { data, error, response } = await api.PATCH("/api/v1/me", { body });
      if (!data) fail(response, error);
      return data;
    },
    onSuccess: (me, body) => {
      client.setQueryData(["me"], me);
      if (body.timezone !== undefined) {
        for (const key of [["days"], STATS_KEY, MOON_KEY, SETTINGS_KEY]) {
          void client.invalidateQueries({ queryKey: key });
        }
      }
    },
  });
}
