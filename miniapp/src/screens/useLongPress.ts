import { useEffect, useRef } from "react";

const LONG_PRESS_MS = 700;

/** Pointer handlers that call `onLongPress` after a steady press; scrolling or a tap cancels. */
export function useLongPress(onLongPress: (() => void) | undefined) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancel = () => {
    clearTimeout(timer.current);
    timer.current = undefined;
  };
  useEffect(() => cancel, []);

  if (!onLongPress) return {};
  return {
    onPointerDown: () => {
      cancel();
      timer.current = setTimeout(onLongPress, LONG_PRESS_MS);
    },
    onPointerUp: cancel,
    onPointerLeave: cancel,
    onPointerCancel: cancel, // a touch scroll ends with pointercancel, not pointerup
    onContextMenu: (event: { preventDefault: () => void }) => {
      event.preventDefault(); // no system menu on long press
    },
  };
}
