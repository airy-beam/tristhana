import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  fail,
  type Listing,
  type ListingBody,
  type ListingLevel,
  type ListingMark,
} from "../../api/client";
import type { Locale } from "../../i18n/negotiate";

// ID-05: the SYC directory line. Kept out of api/client so the initial bundle doesn't carry it:
// only the lazy Teachers-and-students and form chunks import this.
export type { Listing, ListingBody, ListingLevel, ListingMark };

export const LEVELS: readonly ListingLevel[] = [
  "authorised",
  "authorised-1",
  "authorised-2",
  "certified",
];

const LISTING_KEY = ["me", "directory-listing"];

/** My request. `available` false: requests aren't taken right now (no one is set up to
 * check), so callers hide the entry and the form; my own row can still be read and removed.
 * No retry: a failure only hides the row. */
export function useListing() {
  return useQuery({
    staleTime: 60_000,
    retry: false,
    queryKey: LISTING_KEY,
    queryFn: async (): Promise<Listing> => {
      const { data, error, response } = await api.GET("/api/v1/me/directory-listing");
      if (!data) fail(response, error);
      return data;
    },
  });
}

export function useSaveListing() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (body: ListingBody): Promise<Listing> => {
      const { data, error, response } = await api.PUT("/api/v1/me/directory-listing", { body });
      if (!data) fail(response, error);
      return data;
    },
    onSuccess: (listing) => {
      client.setQueryData(LISTING_KEY, listing);
    },
  });
}

export function useRemoveListing() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<void> => {
      const { error, response } = await api.DELETE("/api/v1/me/directory-listing");
      if (!response.ok) fail(response, error);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: LISTING_KEY }),
  });
}

/** `checked_on` is a date, not an instant: month and year only, read in UTC so no device zone
 * moves it into the month before. RU: nominative, lowercase, without the «г.» Intl adds. */
export function checkedMonth(checkedOn: string, locale: Locale): string {
  return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(`${checkedOn.slice(0, 10)}T00:00:00Z`))
    .replace(/\s*г\.$/, "");
}
