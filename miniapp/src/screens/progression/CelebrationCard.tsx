// GM-01: the celebration card, shared by My asanas and the practice details (small: it
// sits in the initial bundle with PracticeDetails). ST-07: a "Share" button when the
// celebration can become a card (a given asana, a series, a practice count).
import type { Celebration, ShareSubject } from "../../api/client";
import { ShareButton } from "../share/ShareButton";

/** Inline at the top; tap the text to dismiss. The motion respects prefers-reduced-motion. */
export function CelebrationCard({
  lines,
  onDismiss,
  share,
}: {
  lines: string[];
  onDismiss: () => void;
  share?: ShareSubject | null;
}) {
  return (
    <div className="card celebration">
      <div role="status">
        <button type="button" className="celebration-lines" onClick={onDismiss}>
          {lines.map((line) => (
            <span key={line}>{line}</span>
          ))}
        </button>
      </div>
      {share && <ShareButton subject={share} />}
    </div>
  );
}

const ASANA_KINDS = new Set(["new_asana", "series_begins", "series_complete"]);

/** What a celebration can share: the given event, or the practice count (never an item). */
export function shareOf(
  found: readonly Celebration[],
  eventId: number | null | undefined,
): ShareSubject | null {
  if (eventId != null && found.some((c) => ASANA_KINDS.has(c.kind)))
    return { kind: "asana", event_id: eventId };
  const count = found.find((c) => c.kind === "practice_count")?.count;
  return count ? { kind: "count", count } : null;
}
