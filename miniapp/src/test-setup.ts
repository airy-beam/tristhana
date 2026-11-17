import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// `findBy…` and `waitFor` give up after 1 s by default. The first run after a change is
// cold (nothing transformed yet), and a lazy screen can take longer than that to arrive,
// which failed a few tests now and then. A passing test never waits this long.
configure({ asyncUtilTimeout: 3000 });
