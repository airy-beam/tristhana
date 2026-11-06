import { useCallback, useState, type ComponentType } from "react";

import type { TourProps } from "./Tour";

type Loaded = { default: ComponentType<TourProps> };
const loadTour = (): Promise<Loaded> => import("./Tour");

/** The tour is its own chunk, loaded on the first tap. Not `React.lazy`: the app has no error
 * boundary, so a failed chunk would blank Home, where logging lives. Here it does nothing. */
export function useTour(load: () => Promise<Loaded> = loadTour) {
  const [Tour, setTour] = useState<ComponentType<TourProps> | null>(null);
  const [open, setOpen] = useState(false);
  const start = useCallback(() => {
    setOpen(true);
    load()
      .then((chunk) => {
        setTour(() => chunk.default);
      })
      .catch(() => {
        setOpen(false);
      });
  }, [load]);
  const close = useCallback(() => {
    setOpen(false);
  }, []);
  return { Tour: open ? Tour : null, start, close };
}
