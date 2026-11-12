import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { DeckCardMotion } from "../components/DeckCardMotion";
import { DeckMilestoneScreen, DeckQuotaPill } from "../components/DeckQuotaPill";
import { DiscussWithAdvisorButton } from "../components/DiscussWithAdvisorButton";
import { JobDescriptionView } from "../components/JobDescriptionView";
import { MatchCard, SwipeActionBar } from "../components/MatchCard";
import { ReasonChips } from "../components/ReasonChips";
import { useIsDesktop } from "../hooks/useMediaQuery";
import { useCardDwell, useSwipe } from "../hooks/useSwipe";
import {
  motionDuration,
  sleep,
  swipeActionToExit,
  type CardExitDirection,
} from "../lib/deckCardMotion";
import { useBilling } from "../hooks/useBilling";
import type { LeftSwipeReason, MatchCard as MatchCardType } from "../types";

const BUILD_POLL_MS = 3000;

export function DeckPage() {
  const isDesktop = useIsDesktop();
  const { billing } = useBilling();
  const [searchParams, setSearchParams] = useSearchParams();
  const [welcomeDismissed, setWelcomeDismissed] = useState(false);
  const showWelcome = searchParams.get("welcome") === "1" && !welcomeDismissed;
  const [card, setCard] = useState<MatchCardType | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [loading, setLoading] = useState(true);
  const [swiping, setSwiping] = useState(false);
  const [showReasons, setShowReasons] = useState(false);
  const [selectedReason, setSelectedReason] = useState<LeftSwipeReason | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [exitingCard, setExitingCard] = useState<MatchCardType | null>(null);
  const [exitDirection, setExitDirection] = useState<CardExitDirection | null>(null);
  const [exitOrigin, setExitOrigin] = useState<{ x: number; y: number } | undefined>();
  const [entering, setEntering] = useState(false);
  const pollRef = useRef<number | null>(null);
  const deckExhausted =
    !card &&
    !building &&
    !loading &&
    billing?.usage?.deck_matches.limit != null &&
    (billing.usage.deck_matches.remaining ?? 0) === 0;
  const dwell = useCardDwell(card?.queue_item_id);
  const displayedCard = exitingCard ?? card;
  const isAnimating = Boolean(exitingCard || entering);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadNext = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.deck.next();
      setCard(res.card);
      setRemaining(res.queue_remaining);
      setMessage(res.message ?? null);
      setBuilding(Boolean(res.building) && !res.card);
      setShowReasons(false);
      setSelectedReason(null);
      setDetailsOpen(false);
      return res;
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Failed to load deck");
      setBuilding(false);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const status = await api.deck.status();
      setBuilding(status.building);
      if (status.message) setMessage(status.message);
      if (status.queue_remaining > 0 || !status.building) {
        await loadNext();
      }
    } catch {
      /* keep polling */
    }
  }, [loadNext]);

  useEffect(() => {
    loadNext();
  }, [loadNext]);

  useEffect(() => {
    void api.events.track("deck_opened").catch(() => undefined);
  }, []);

  useEffect(() => {
    stopPolling();
    if (building && !card) {
      pollRef.current = window.setInterval(() => {
        void pollStatus();
      }, BUILD_POLL_MS);
    }
    return stopPolling;
  }, [building, card, pollStatus, stopPolling]);

  useEffect(() => {
    if (card) dwell.start();
  }, [card, dwell]);

  useEffect(() => {
    if (!card?.queue_item_id || exitingCard) return;
    setEntering(true);
    const timer = window.setTimeout(() => setEntering(false), motionDuration("enter"));
    return () => window.clearTimeout(timer);
  }, [card?.queue_item_id, exitingCard]);

  const performSwipeRef = useRef<
    (
      action: "right" | "left" | "skip",
      reason?: LeftSwipeReason,
      dragOrigin?: { x: number; y: number },
    ) => void
  >(() => undefined);

  const handleLeftIntent = useCallback(() => {
    setShowReasons(true);
  }, []);

  const confirmLeft = useCallback(
    (reason?: LeftSwipeReason) => {
      performSwipeRef.current("left", reason);
    },
    [],
  );

  const swipe = useSwipe({
    enabled: !swiping && !showReasons && !detailsOpen && !!card && !exitingCard,
    onSwipeLeft: () => handleLeftIntent(),
    onSwipeRight: (offset) => performSwipeRef.current("right", undefined, offset),
    onSkip: (offset) => performSwipeRef.current("skip", undefined, offset),
  });

  const performSwipe = useCallback(
    async (
      action: "right" | "left" | "skip",
      reason?: LeftSwipeReason,
      dragOrigin?: { x: number; y: number },
    ) => {
      if (!card || swiping || exitingCard) return;
      setSwiping(true);
      setExitDirection(swipeActionToExit(action));
      setExitOrigin(dragOrigin);
      setExitingCard(card);

      await sleep(motionDuration("exit"));

      const dwellMs = await dwell.stop((id, ms) => api.deck.dwell(id, ms));
      try {
        await api.deck.swipe(card.queue_item_id, action, reason, dwellMs || undefined);
        void api.engagement.heartbeat("deck_swipe").catch(() => undefined);
        await loadNext();
        setExitingCard(null);
        setExitDirection(null);
        setExitOrigin(undefined);
        swipe.reset();
      } catch (err) {
        setExitingCard(null);
        setExitDirection(null);
        setExitOrigin(undefined);
        swipe.reset();
        setMessage(err instanceof ApiError ? err.message : "Swipe failed");
      } finally {
        setSwiping(false);
      }
    },
    [card, swiping, exitingCard, dwell, loadNext, swipe],
  );

  performSwipeRef.current = performSwipe;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (swiping || isAnimating || !card || detailsOpen) return;
      if (showReasons) {
        if (e.key === "Escape") setShowReasons(false);
        return;
      }
      if (e.key === "ArrowLeft") handleLeftIntent();
      if (e.key === "ArrowRight") performSwipe("right");
      if (e.key === "ArrowDown") performSwipe("skip");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [card, swiping, isAnimating, showReasons, detailsOpen, handleLeftIntent, performSwipe]);

  if (loading && !card) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center py-16">
        <div className="relative h-10 w-10">
          <div className="absolute inset-0 rounded-full border-2 border-border" />
          <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-brand-strong" />
        </div>
        <p className="mt-4 text-sm text-muted">
          {building ? message ?? "Building your deck…" : "Loading next job…"}
        </p>
      </div>
    );
  }

  if (!card) {
    if (deckExhausted) {
      return <DeckMilestoneScreen onRefresh={loadNext} />;
    }
    return (
      <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl border border-border bg-surface text-brand-strong">
          {building ? (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.75" />
              <path d="M12 8v4l3 2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
            </svg>
          ) : (
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
              <rect x="4" y="6" width="12" height="9" rx="2" stroke="currentColor" strokeWidth="1.75" />
              <rect x="8" y="10" width="12" height="9" rx="2" stroke="currentColor" strokeWidth="1.75" />
            </svg>
          )}
        </div>
        <p className="font-display text-2xl text-ink-text">
          {building ? "Building your deck" : message ?? "You're all caught up"}
        </p>
        <p className="mt-2 max-w-sm text-sm text-muted">
          {building
            ? message ??
              "We're pulling jobs and ranking matches for you. Cards will appear automatically."
            : "No more cards in your deck right now. Check back tomorrow or review past swipes."}
        </p>
        {!building ? (
          <div className="mt-6 flex flex-col items-center gap-3">
            <Link
              to="/todo"
              className="rounded-[var(--radius-button)] border border-brand/30 bg-brand-muted px-5 py-2.5 text-sm font-semibold text-brand-strong transition hover:border-brand hover:bg-brand-muted/80"
            >
              View matches
            </Link>
            <button
              type="button"
              onClick={loadNext}
              className="rounded-[var(--radius-button)] border border-border bg-surface-raised px-5 py-2.5 text-sm font-semibold text-muted transition hover:border-muted hover:text-ink-text"
            >
              Refresh deck
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  const reasonUi = showReasons ? (
    isDesktop ? (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <button
          type="button"
          className="absolute inset-0 bg-ink-text/25 backdrop-blur-sm"
          aria-label="Go back to card"
          onClick={() => setShowReasons(false)}
        />
        <div className="relative w-full max-w-md rounded-[var(--radius-card)] border border-border bg-canvas p-5 shadow-xl">
          <ReasonChips
            selected={selectedReason}
            onSelect={(r) => {
              setSelectedReason(r);
              confirmLeft(r);
            }}
            onSkipReason={() => confirmLeft(undefined)}
            onCancel={() => setShowReasons(false)}
          />
        </div>
      </div>
    ) : (
      <div className="fixed inset-0 z-50 flex flex-col justify-end">
        <button
          type="button"
          className="absolute inset-0 bg-ink-text/25 backdrop-blur-sm"
          aria-label="Go back to card"
          onClick={() => setShowReasons(false)}
        />
        <div className="relative mx-auto w-full max-w-lg border-t border-border bg-canvas px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-5 shadow-[0_-8px_32px_rgba(15,23,42,0.12)]">
          <ReasonChips
            selected={selectedReason}
            onSelect={(r) => {
              setSelectedReason(r);
              confirmLeft(r);
            }}
            onSkipReason={() => confirmLeft(undefined)}
            onCancel={() => setShowReasons(false)}
          />
        </div>
      </div>
    )
  ) : null;

  if (isDesktop) {
    return (
      <div className="flex min-h-0 flex-1 flex-col pb-2">
        {showWelcome ? (
          <div className="mb-3 rounded-xl border border-accent/25 bg-accent-muted/40 px-4 py-3">
            <p className="text-sm font-semibold text-ink-text">You&apos;re all set — start swiping!</p>
            <p className="mt-1 text-xs text-muted">
              Swipe right on jobs you like. We&apos;ll add them to your application queue and help you
              prep with AI.
            </p>
            <button
              type="button"
              className="mt-2 text-xs font-semibold text-brand-strong hover:text-brand-deep"
              onClick={() => {
                setWelcomeDismissed(true);
                setSearchParams({}, { replace: true });
              }}
            >
              Got it
            </button>
          </div>
        ) : null}
        <div className="mb-3 flex items-center justify-between gap-3 px-1">
          <DeckQuotaPill remaining={remaining} />
          <span className="text-xs text-subtle">
            {detailsOpen
              ? "Close description to swipe · Esc or ✕"
              : "Focus mode · ← pass · → interested · ↓ skip"}
          </span>
        </div>

        <div className="flex min-h-0 flex-1 gap-5">
          <div className="relative mx-auto w-full max-w-lg shrink-0 select-none xl:mx-0">
            <div className="absolute inset-x-4 top-3 h-full scale-[0.96] rounded-[var(--radius-card)] bg-surface-raised/50" />
            <div className="absolute inset-x-2 top-1.5 h-full scale-[0.98] rounded-[var(--radius-card)] bg-surface-raised/80" />
            <div className="relative touch-pan-y" {...swipe.handlers}>
              {displayedCard ? (
                <DeckCardMotion
                  entering={entering && !exitingCard}
                  exitDirection={exitingCard ? exitDirection : null}
                  exitOrigin={exitOrigin}
                >
                  <MatchCard
                    key={displayedCard.queue_item_id}
                    card={displayedCard}
                    dragOffset={isAnimating ? { x: 0, y: 0 } : swipe.offset}
                    isDragging={!isAnimating && swipe.dragging}
                    showActions={false}
                    onDetailsOpenChange={setDetailsOpen}
                  />
                </DeckCardMotion>
              ) : null}
            </div>
            {!showReasons ? (
              <div className="mt-5">
                <SwipeActionBar
                  disabled={swiping || isAnimating}
                  onPass={handleLeftIntent}
                  onSkip={() => performSwipe("skip")}
                  onLike={() => performSwipe("right")}
                />
              </div>
            ) : null}
          </div>

          <div className="hidden min-h-0 flex-1 overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface lg:flex lg:flex-col">
            <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border-subtle px-4 py-3">
              <p className="text-xs font-semibold uppercase tracking-[0.06em] text-subtle">
                Job description
              </p>
              <DiscussWithAdvisorButton card={card} size="sm" />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
              <JobDescriptionView card={card} showHeader showDiscussButton={false} />
            </div>
          </div>
        </div>

        {reasonUi}
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden pb-2">
      {showWelcome ? (
        <div className="mb-3 shrink-0 rounded-xl border border-accent/25 bg-accent-muted/40 px-3 py-2.5">
          <p className="text-sm font-semibold text-ink-text">You&apos;re all set — start swiping!</p>
          <p className="mt-1 text-xs text-muted">Swipe right to add jobs to your application queue.</p>
          <button
            type="button"
            className="mt-2 text-xs font-semibold text-brand-strong"
            onClick={() => {
              setWelcomeDismissed(true);
              setSearchParams({}, { replace: true });
            }}
          >
            Got it
          </button>
        </div>
      ) : null}
      <div className="mb-3 flex shrink-0 items-center justify-between px-1">
        <DeckQuotaPill remaining={remaining} />
      </div>

      <div className="relative mx-auto min-h-0 w-full max-w-md flex-1 select-none overflow-hidden">
        <div className="absolute inset-x-4 top-3 h-full scale-[0.96] rounded-[var(--radius-card)] bg-surface-raised/50" />
        <div className="absolute inset-x-2 top-1.5 h-full scale-[0.98] rounded-[var(--radius-card)] bg-surface-raised/80" />
        <div className="relative touch-pan-y" {...swipe.handlers}>
          {displayedCard ? (
            <DeckCardMotion
              entering={entering && !exitingCard}
              exitDirection={exitingCard ? exitDirection : null}
              exitOrigin={exitOrigin}
            >
              <MatchCard
                key={displayedCard.queue_item_id}
                card={displayedCard}
                dragOffset={isAnimating ? { x: 0, y: 0 } : swipe.offset}
                isDragging={!isAnimating && swipe.dragging}
                showActions={false}
                onDetailsOpenChange={setDetailsOpen}
              />
            </DeckCardMotion>
          ) : null}
        </div>
      </div>

      {!showReasons ? (
        <div className="mt-4 shrink-0 pb-1">
          <SwipeActionBar
            disabled={swiping || isAnimating}
            onPass={handleLeftIntent}
            onSkip={() => performSwipe("skip")}
            onLike={() => performSwipe("right")}
          />
        </div>
      ) : null}

      {reasonUi}
    </div>
  );
}
