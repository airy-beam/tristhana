import { useId } from "react";

interface Props {
  /** The label as the message has it ("📝 Add details"): a leading emoji is the row's icon. */
  label: string;
  /** A muted second line: what was entered, or the fact the row is about. One line, cut with
   * an ellipsis; read as the row's description. */
  sub?: string | undefined;
  /** For a row that opens its panel right under itself. */
  expanded?: boolean | undefined;
  /** Does its thing on the tap (no chevron, the label in the link colour). */
  action?: boolean | undefined;
  onClick: () => void;
}

const ICON = /^(\p{Extended_Pictographic}\S*)\s+(.+)$/su;

/** The one list row (UI-06): icon, label, an optional second line, a chevron. Rows stand in a
 * `.list`, which draws the hairlines between them. At least 44px high; nothing wraps. */
export function Row({ label, sub, expanded, action, onClick }: Props) {
  const id = useId();
  const [, icon, title = label] = ICON.exec(label) ?? [];
  return (
    <button
      type="button"
      className={action ? "lrow act" : "lrow"}
      aria-labelledby={`${id}l`}
      aria-describedby={sub ? `${id}s` : undefined}
      aria-expanded={expanded}
      onClick={onClick}
    >
      <span className="lrow-text">
        <span id={`${id}l`} className="lrow-label">
          {icon && <span className="lrow-icon">{icon}</span>}
          {icon && " "}
          <span className="lrow-title">{title}</span>
        </span>
        {sub && (
          <span id={`${id}s`} className={icon ? "lrow-sub in" : "lrow-sub"}>
            {sub}
          </span>
        )}
      </span>
    </button>
  );
}
