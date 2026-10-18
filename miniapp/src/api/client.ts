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
  const others = days.days.filter((d) => d.date !== date);
  const next = status ? [...others, { date, status }] : others;
  return { ...days, days: next.sort((a, b) => a.date.localeCompare(b.date)) };
}

/** Sets (status) or clears (null) a day, optimistically; rolls back if the server refuses. */
export function useSetDay() {
  const client = useQueryClient();
  return useMutation({
    // One at a time, in tap order: the last tap wins and a rollback can't undo a later tap.
    scope: { id: "day" },
    mutationFn: async ({ date, status }: { date: string; status: DayStatus | null }) => {
      const params = { path: { date } };
      const { error, response } = status
        ? await api.PUT("/api/v1/me/days/{date}", { params, body: { status } })
        : await api.DELETE("/api/v1/me/days/{date}", { params });
      if (!response.ok) fail(response, error);
    },
    onMutate: async ({ date, status }) => {
      await client.cancelQueries({ queryKey: DAYS_KEY });
      const before = client.getQueryData<Days>(DAYS_KEY);
      if (before) client.setQueryData(DAYS_KEY, withDay(before, date, status));
      return { before };
    },
    onError: (_error, _vars, context) => {
      if (context?.before) client.setQueryData(DAYS_KEY, context.before);
    },
  });
}
