// What this device remembers about first steps. Blocked storage counts as done: never nag.
const LOGGED_KEY = "onboard.logged";
const TOUR_KEY = "onboard.tour";

function seen(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return true;
  }
}

function remember(key: string): void {
  try {
    localStorage.setItem(key, "1");
  } catch {
    // Blocked storage: it just isn't remembered.
  }
}

export const loggedBefore = () => seen(LOGGED_KEY);
export const markLogged = () => {
  remember(LOGGED_KEY);
};
export const tourSeen = () => seen(TOUR_KEY);
export const markTourSeen = () => {
  remember(TOUR_KEY);
};
