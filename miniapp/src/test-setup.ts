import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

// `findBy…` and `waitFor` give up after 1 s by default. The first run after a change is
// cold (nothing transformed yet), and a lazy screen can take longer than that to arrive,
// which failed a few tests now and then. A passing test never waits this long.
configure({ asyncUtilTimeout: 3000 });

// jsdom lays nothing out, so it has no `scrollIntoView`: a no-op here, and a test that looks at
// the scroll puts its own spy in its place.
Element.prototype.scrollIntoView = () => undefined;
