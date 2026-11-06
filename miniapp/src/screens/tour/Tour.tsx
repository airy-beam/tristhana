import { Localized } from "@fluent/react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useDays, useMoonDays } from "../../api/client";
import { haptics, useBackButton } from "../../telegram";

const STEPS = ["today", "stats", "asanas", "moon", "settings"] as const;
type Step = (typeof STEPS)[number];

/** How far into the target the sheet may reach before it moves to the top. */
const TARGET_TOP = 48;
/** The sheet moves only once scrolling has stopped, so Next stays under the thumb. */
const SETTLE_MS = 150;

/** The visible height: the page's lower part can be off screen until the app is expanded. */
function visibleHeight(): number {
  const style = getComputedStyle(document.documentElement);
  return parseFloat(style.getPropertyValue("--tg-viewport-stable-height")) || window.innerHeight;
}

const target = (step: Step) => document.querySelector<HTMLElement>(`[data-tour="${step}"]`);

export interface TourProps {
  onExit: () => void;
}

/** Coach-marks on Home (UI-02): a spotlight and a sheet, nothing behind them can be tapped and
 * nothing is written. Steps whose target isn't on the page are left out. */
export default function Tour({ onExit }: TourProps) {
  useBackButton(onExit);
  const days = useDays();
  const moon = useMoonDays();
  const settled = !days.isPending && !moon.isPending;
  const [steps, setSteps] = useState<Step[] | null>(null);
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [atTop, setAtTop] = useState(false);
  const sheet = useRef<HTMLDivElement>(null);
  const text = useRef<HTMLParagraphElement>(null);
  const step = steps?.[index];
  const count = steps?.length ?? 0;
  const ready = count > 0;

  useEffect(() => {
    if (!settled) return;
    const frame = requestAnimationFrame(() => {
      const found = STEPS.filter((s) => target(s));
      if (found.length > 0) setSteps(found);
      else onExit();
    });
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [settled, onExit]);

  useEffect(() => {
    if (!ready) return;
    const root = document.getElementById("root");
    root?.toggleAttribute("inert", true);
    return () => {
      root?.toggleAttribute("inert", false);
      window.scrollTo({ top: 0 });
      const heading = root?.querySelector("h1");
      heading?.setAttribute("tabindex", "-1");
      heading?.focus({ preventScroll: true });
    };
  }, [ready]);

  useEffect(() => {
    if (!step) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target(step)?.scrollIntoView({ block: "start", behavior: reduced ? "auto" : "smooth" });
    text.current?.focus({ preventScroll: true });
    let frame = 0;
    let settle = 0;
    const place = () => {
      const found = target(step)?.getBoundingClientRect();
      const free = visibleHeight() - (sheet.current?.offsetHeight ?? 0);
      setAtTop(found !== undefined && found.top + TARGET_TOP > free);
    };
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        setRect(target(step)?.getBoundingClientRect() ?? null);
      });
      clearTimeout(settle);
      settle = window.setTimeout(place, SETTLE_MS);
    };
    measure();
    const resized = new ResizeObserver(measure);
    resized.observe(document.body);
    window.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settle);
      resized.disconnect();
      window.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [step]);

  useEffect(() => {
    if (count === 0) return;
    const go = (by: number) => {
      haptics.selection();
      setIndex((i) => Math.min(Math.max(i + by, 0), count - 1));
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onExit();
      else if (event.key === "ArrowRight") go(1);
      else if (event.key === "ArrowLeft") go(-1);
      else if (event.key === "Tab") {
        const buttons = [...(sheet.current?.querySelectorAll("button") ?? [])];
        const edge = event.shiftKey ? buttons[0] : buttons.at(-1);
        if (document.activeElement === edge || document.activeElement === text.current) {
          event.preventDefault();
          (event.shiftKey ? buttons.at(-1) : buttons[0])?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [count, onExit]);

  if (!step) return null;
  const move = (by: number) => {
    haptics.selection();
    setIndex(index + by);
  };
  return createPortal(
    <div
      className="tour"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-progress"
      aria-describedby="tour-text"
    >
      <div className={rect ? "tour-blocker" : "tour-blocker dim"} />
      {rect && (
        <div
          className="tour-spot"
          style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
        />
      )}
      <div ref={sheet} className={atTop ? "tour-sheet top" : "tour-sheet"}>
        <Localized id="tour-progress" vars={{ n: index + 1, total: count }}>
          <p id="tour-progress" className="hint small" />
        </Localized>
        <Localized id={`tour-${step}`}>
          <p id="tour-text" ref={text} tabIndex={-1} />
        </Localized>
        <div className="row">
          {index > 0 && (
            <Localized id="tour-prev" attrs={{ "aria-label": true }}>
              <button
                type="button"
                className="link"
                onClick={() => {
                  move(-1);
                }}
              />
            </Localized>
          )}
          {index < count - 1 && (
            <Localized id="tour-next">
              <button
                type="button"
                className="chip"
                onClick={() => {
                  move(1);
                }}
              />
            </Localized>
          )}
          <Localized id="tour-done">
            <button type="button" className="link" onClick={onExit} />
          </Localized>
        </div>
      </div>
    </div>,
    document.body,
  );
}
