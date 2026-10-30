// GM-01 part 2: the 🎉 for a practice count (100/365/1000), from the day save's response
// (never optimistic: the server's ledger decides it celebrates once ever).
import { useLocalization } from "@fluent/react";

import type { Celebration } from "../../api/client";
import { CelebrationCard } from "./CelebrationCard";
import { countLines } from "./progressionText";

export function CountCelebration({
  found,
  onDismiss,
}: {
  found: readonly Celebration[];
  onDismiss: () => void;
}) {
  const { l10n } = useLocalization();
  const lines = countLines(l10n, found);
  return lines.length ? <CelebrationCard lines={lines} onDismiss={onDismiss} /> : null;
}
