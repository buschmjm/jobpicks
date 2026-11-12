import { useCallback, useEffect, useRef, useState, type TouchEvent as ReactTouchEvent } from "react";

const SWIPE_THRESHOLD = 80;
const DRAG_DEAD_ZONE = 12;

interface UseSwipeOptions {
  onSwipeLeft: (offset: { x: number; y: number }) => void;
  onSwipeRight: (offset: { x: number; y: number }) => void;
  onSkip: (offset: { x: number; y: number }) => void;
  enabled?: boolean;
}

interface DragStart {
  x: number;
  y: number;
  pointer: "touch" | "mouse";
  active: boolean;
}

function isNoSwipeTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return !!target.closest(
    "[data-no-swipe], button, a, input, textarea, select, label, [data-scroll-zone]",
  );
}

export function useSwipe({ onSwipeLeft, onSwipeRight, onSkip, enabled = true }: UseSwipeOptions) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [mouseTracking, setMouseTracking] = useState(false);
  const startRef = useRef<DragStart | null>(null);
  const offsetRef = useRef(offset);
  offsetRef.current = offset;

  const reset = useCallback(() => {
    setOffset({ x: 0, y: 0 });
    setDragging(false);
    setMouseTracking(false);
    startRef.current = null;
  }, []);

  const finishDrag = useCallback(() => {
    if (!startRef.current?.active) {
      reset();
      return;
    }
    const { x, y } = offsetRef.current;
    if (y > SWIPE_THRESHOLD * 1.5) {
      onSkip({ x, y });
      return;
    }
    if (x > SWIPE_THRESHOLD) {
      onSwipeRight({ x, y });
      return;
    }
    if (x < -SWIPE_THRESHOLD) {
      onSwipeLeft({ x, y });
      return;
    }
    reset();
  }, [onSkip, onSwipeLeft, onSwipeRight, reset]);

  const beginPointer = useCallback(
    (clientX: number, clientY: number, pointer: "touch" | "mouse") => {
      if (!enabled) return;
      startRef.current = { x: clientX, y: clientY, pointer, active: false };
    },
    [enabled],
  );

  const movePointer = useCallback(
    (clientX: number, clientY: number) => {
      if (!enabled || !startRef.current) return;
      const dx = clientX - startRef.current.x;
      const dy = clientY - startRef.current.y;

      if (!startRef.current.active) {
        if (Math.abs(dx) < DRAG_DEAD_ZONE && Math.abs(dy) < DRAG_DEAD_ZONE) {
          return;
        }
        if (Math.abs(dy) >= Math.abs(dx)) {
          reset();
          return;
        }
        startRef.current.active = true;
        setDragging(true);
      }

      setOffset({ x: dx, y: dy });
    },
    [enabled, reset],
  );

  const onTouchStart = useCallback(
    (e: ReactTouchEvent) => {
      if (!enabled || isNoSwipeTarget(e.target)) return;
      const t = e.touches[0];
      beginPointer(t.clientX, t.clientY, "touch");
    },
    [beginPointer, enabled],
  );

  const onTouchMove = useCallback(
    (e: ReactTouchEvent) => {
      if (!enabled || !startRef.current || startRef.current.pointer !== "touch") return;
      const t = e.touches[0];
      movePointer(t.clientX, t.clientY);
    },
    [enabled, movePointer],
  );

  const onTouchEnd = useCallback(() => {
    if (!enabled || startRef.current?.pointer !== "touch") return;
    finishDrag();
  }, [enabled, finishDrag]);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!enabled || e.button !== 0 || isNoSwipeTarget(e.target)) return;
      beginPointer(e.clientX, e.clientY, "mouse");
      setMouseTracking(true);
    },
    [beginPointer, enabled],
  );

  useEffect(() => {
    if (!mouseTracking) return;

    function onMouseMove(e: MouseEvent) {
      movePointer(e.clientX, e.clientY);
    }

    function onMouseUp() {
      finishDrag();
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [mouseTracking, finishDrag, movePointer]);

  return {
    offset,
    dragging,
    handlers: { onTouchStart, onTouchMove, onTouchEnd, onMouseDown },
    reset,
  };
}

export function useCardDwell(queueItemId: string | undefined) {
  const startRef = useRef<number | null>(null);
  const idRef = useRef(queueItemId);

  idRef.current = queueItemId;

  const start = useCallback(() => {
    startRef.current = Date.now();
  }, []);

  const stop = useCallback(async (record: (id: string, ms: number) => Promise<unknown>) => {
    if (!startRef.current || !idRef.current) return 0;
    const ms = Date.now() - startRef.current;
    startRef.current = null;
    if (ms > 0) {
      await record(idRef.current, ms).catch(() => undefined);
    }
    return ms;
  }, []);

  return { start, stop };
}
