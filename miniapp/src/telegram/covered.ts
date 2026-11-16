import { createContext } from "react";

/** True for a screen kept mounted but hidden under another (Settings over it, ADR-0047): its
 * main button is hidden with it. Its own module, so a test that mocks `telegram` keeps it. */
export const Covered = createContext(false);
