export const CARD_EXIT_MS = 280;
export const CARD_ENTER_MS = 320;

export type CardExitDirection = "left" | "right" | "down";

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function motionDuration(kind: "exit" | "enter"): number {
  if (prefersReducedMotion()) return 0;
  return kind === "exit" ? CARD_EXIT_MS : CARD_ENTER_MS;
}

export function swipeActionToExit(action: "left" | "right" | "skip"): CardExitDirection {
  if (action === "left") return "left";
  if (action === "right") return "right";
  return "down";
}

export function exitMotionClass(direction: CardExitDirection): string {
  return `deck-card-exit-${direction}`;
}
