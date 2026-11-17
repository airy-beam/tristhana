import { Component, type ReactNode } from "react";

import { retryChunks } from "./lazyRetry";

interface Props {
  children: ReactNode;
  /** Tells the owner, so it can close what it opened and say so. */
  onFail?: (() => void) | undefined;
}

/** Round a lazy piece inside a screen (a panel of the day card, a row on Today): when its
 * chunk fails to load, the piece is just not there and the screen stays as it was. The chunk
 * loads again the next time the piece is mounted. For whole screens use `ChunkBoundary`. */
export class ChunkGuard extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(): void {
    retryChunks();
    this.props.onFail?.();
  }

  override render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}
