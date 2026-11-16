// What this device remembers about first steps. Blocked storage counts as done: never nag.
const LOGGED_KEY = "onboard.logged";

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
