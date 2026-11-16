import { Localized } from "@fluent/react";
import { Component, type ReactNode } from "react";

import { backButtonAvailable, haptics } from "../telegram";
import { retryChunks } from "./lazyRetry";

interface Props {
  children: ReactNode;
  /** A pushed screen: where its own back link leads on clients without Telegram's button. */
  onBack?: (() => void) | undefined;
}

/** Round every tab and pushed screen (ADR-0047): when a lazy chunk fails to load (a weak
 * connection, a deploy mid-session), the screen says so and offers a retry. The tab bar is
 * outside, so it stays. */
export class ChunkBoundary extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  retry = (): void => {
    haptics.impact("light");
    retryChunks();
    this.setState({ failed: false });
  };

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    const { onBack } = this.props;
    return (
      <main className="screen">
        {onBack && !backButtonAvailable() && (
          <Localized id="stats-back">
            <button type="button" className="link" onClick={onBack} />
          </Localized>
        )}
        <Localized id="chunk-failed">
          <p className="hint" role="alert" />
        </Localized>
        <Localized id="chunk-retry">
          <button type="button" className="row-button" onClick={this.retry} />
        </Localized>
      </main>
    );
  }
}
