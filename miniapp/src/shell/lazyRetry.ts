import { createElement, lazy, type ComponentType } from "react";

type Loader<P> = () => Promise<{ default: ComponentType<P> }>;

// Chunks whose load failed, renewed together when the person taps "Try again".
const failed = new Set<() => void>();

/** `React.lazy` that can try again. `lazy` keeps a failed load for good, so a retry button
 * could never work; here a failed chunk gets a new `lazy` on `retryChunks()`. A failure is
 * thrown to the nearest error boundary (`ChunkBoundary`), as with `lazy`. */
export function lazyRetry<P extends object>(load: Loader<P>): ComponentType<P> {
  const fresh = () =>
    lazy(() =>
      load().catch((error: unknown) => {
        failed.add(renew);
        throw error;
      }),
    );
  let Chunk = fresh();
  function renew() {
    Chunk = fresh();
  }
  return function Lazy(props: P) {
    return createElement(Chunk, props);
  };
}

/** Lets every chunk that failed load again on its next render. */
export function retryChunks(): void {
  failed.forEach((renew) => {
    renew();
  });
  failed.clear();
}
