// GM-01: the celebration card, shared by My asanas and the practice details (small: it
// sits in the initial bundle with PracticeDetails).

/** Inline at the top; tap to dismiss. The motion respects prefers-reduced-motion (CSS). */
export function CelebrationCard({ lines, onDismiss }: { lines: string[]; onDismiss: () => void }) {
  return (
    <button type="button" className="card celebration" role="status" onClick={onDismiss}>
      {lines.map((line) => (
        <span key={line}>{line}</span>
      ))}
    </button>
  );
}
