import type { CSSProperties, ReactNode } from "react";
import type { CardExitDirection } from "../lib/deckCardMotion";
import { exitMotionClass } from "../lib/deckCardMotion";

interface DeckCardMotionProps {
  children: ReactNode;
  entering?: boolean;
  exitDirection?: CardExitDirection | null;
  exitOrigin?: { x: number; y: number };
}

export function DeckCardMotion({
  children,
  entering = false,
  exitDirection = null,
  exitOrigin,
}: DeckCardMotionProps) {
  const motionClass = exitDirection
    ? exitMotionClass(exitDirection)
    : entering
      ? "deck-card-enter"
      : "";

  const style: CSSProperties | undefined = exitDirection
    ? ({
        "--deck-start-x": `${exitOrigin?.x ?? 0}px`,
        "--deck-start-y": `${exitOrigin?.y ?? 0}px`,
        "--deck-start-rotate": `${(exitOrigin?.x ?? 0) * 0.06}deg`,
      } as CSSProperties)
    : undefined;

  return (
    <div className={`deck-card-motion relative ${motionClass}`.trim()} style={style}>
      {children}
    </div>
  );
}
