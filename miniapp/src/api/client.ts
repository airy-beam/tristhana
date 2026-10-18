import { useQuery } from "@tanstack/react-query";
import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

// Typed client generated from the backend contract (ADR-0013); never hand-write API types.
// Empty base URL in dev: /api is proxied to the local backend.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  // Resolve fetch per call (openapi-fetch would capture it once at import), so tests can stub it.
  fetch: (request) => globalThis.fetch(request),
});

export type Health = components["schemas"]["Health"];

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
