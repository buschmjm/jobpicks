import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ChatMarkdown } from "../components/ChatMarkdown";
import { UsageBanner } from "../components/UsageLimits";
import { rememberDiscussJob } from "../components/ResumeBuilderPanel";
import { Button } from "../components/ui/Button";
import { Alert } from "../components/ui/Alert";
import { FieldTextarea } from "../components/ui/Field";
import { InlineSpinner } from "../components/ui/NavIcon";
import {
  buildDiscussJobMessage,
  DISCUSS_JOB_STATE_KEY,
  isDiscussJobState,
} from "../lib/discussJob";
import { openExternalUrl } from "../lib/openExternalUrl";
import type { BillingStatus, CareerMessage, CareerMessageSource } from "../types";

const STARTERS = [
  "What’s the market like for my target titles where I live?",
  "Which of my roles am I actually competitive for?",
  "Where are the hard gaps in my profile?",
];

const POLL_MS = 2500;

function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function hasPendingReply(messages: CareerMessage[]): boolean {
  if (!messages.length) return false;
  const last = messages[messages.length - 1];
  if (last.role === "assistant" && last.status === "pending") return true;
  if (last.role === "user") return true;
  return false;
}

function MessageSources({ sources }: { sources: CareerMessageSource[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-border-subtle pt-2">
      <span className="w-full text-[11px] font-medium uppercase tracking-wide text-subtle">
        Sources
      </span>
      {sources.slice(0, 8).map((src) => {
        const label = src.publisher || sourceHost(src.url) || src.title;
        if (src.url) {
          return (
            <a
              key={`${src.url}-${src.title}`}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-muted transition hover:border-muted hover:text-ink-text"
              title={src.title}
            >
              {label}
            </a>
          );
        }
        return (
          <span
            key={`corpus-${src.title}`}
            className="rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-muted"
            title={src.title}
          >
            {label}
          </span>
        );
      })}
    </div>
  );
}

export function CareerAdvisorPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<CareerMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [billingBusy, setBillingBusy] = useState(false);
  const [researchStatus, setResearchStatus] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const seededDiscussRef = useRef(false);
  const sendingRef = useRef(false);
  const pollRef = useRef<number | null>(null);
  const streamingAssistantIdRef = useRef<string | null>(null);
  const streamAbortRef = useRef<AbortController | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const refreshMessages = useCallback(async () => {
    const res = await api.career.messages();
    setMessages(res.messages);
    return res.messages;
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = window.setInterval(() => {
      void (async () => {
        try {
          const next = await refreshMessages();
          if (!hasPendingReply(next)) {
            stopPolling();
            sendingRef.current = false;
            setSending(false);
            setResearchStatus(null);
            streamingAssistantIdRef.current = null;
          }
        } catch {
          /* keep polling */
        }
      })();
    }, POLL_MS);
  }, [refreshMessages, stopPolling]);

  useEffect(() => {
    void (async () => {
      try {
        const next = await refreshMessages();
        if (hasPendingReply(next)) {
          sendingRef.current = true;
          setSending(true);
          startPolling();
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load conversation");
      } finally {
        setLoading(false);
      }
    })();
    return stopPolling;
  }, [refreshMessages, startPolling, stopPolling]);

  useEffect(() => {
    void api.billing.status().then(setBilling).catch(() => undefined);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, researchStatus]);

  const handleStop = useCallback(async () => {
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    stopPolling();
    setResearchStatus(null);

    const assistantId = streamingAssistantIdRef.current;
    streamingAssistantIdRef.current = null;
    sendingRef.current = false;
    setSending(false);

    if (assistantId && !assistantId.startsWith("local-")) {
      try {
        await api.career.cancelMessage(assistantId);
        await refreshMessages();
        return;
      } catch {
        /* fall through to refresh */
      }
    }

    setMessages((prev) =>
      prev.map((msg) =>
        msg.id === assistantId
          ? {
              ...msg,
              status: "cancelled",
              content: msg.content.trim() || "Response stopped.",
            }
          : msg,
      ),
    );
    void refreshMessages().catch(() => undefined);
  }, [refreshMessages, stopPolling]);

  const handleSend = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || sendingRef.current) return;
      sendingRef.current = true;
      setSending(true);
      setError(null);
      setDraft("");
      setResearchStatus(null);
      streamingAssistantIdRef.current = null;
      streamAbortRef.current?.abort();
      const abortController = new AbortController();
      streamAbortRef.current = abortController;

      const pendingUser: CareerMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: text,
        source: null,
        created_at: new Date().toISOString(),
      };
      const pendingAssistant: CareerMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        source: null,
        status: "pending",
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, pendingUser, pendingAssistant]);
      streamingAssistantIdRef.current = pendingAssistant.id;

      let streamFailed = false;
      let streamAborted = false;
      try {
        for await (const event of api.career.sendMessageStream(text, {
          signal: abortController.signal,
        })) {
          if (event.type === "user") {
            streamingAssistantIdRef.current =
              event.assistant_id ?? streamingAssistantIdRef.current;
            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id === pendingUser.id) {
                  return { ...msg, id: event.id, content: event.content };
                }
                if (
                  event.assistant_id &&
                  (msg.id === pendingAssistant.id || msg.id === streamingAssistantIdRef.current)
                ) {
                  return { ...msg, id: event.assistant_id, status: "pending" };
                }
                return msg;
              }),
            );
            if (event.assistant_id) {
              streamingAssistantIdRef.current = event.assistant_id;
            }
          } else if (event.type === "status") {
            if (event.phase === "researching") {
              setResearchStatus(event.detail || "Researching market…");
            } else if (event.phase === "research_failed") {
              setResearchStatus(event.detail || "Couldn’t verify live market data");
            } else {
              setResearchStatus(null);
            }
          } else if (event.type === "sources") {
            const assistantId = streamingAssistantIdRef.current;
            if (!assistantId) continue;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, sources: event.items } : msg,
              ),
            );
          } else if (event.type === "token") {
            setResearchStatus(null);
            const assistantId = streamingAssistantIdRef.current;
            if (!assistantId) continue;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, content: msg.content + event.text }
                  : msg,
              ),
            );
          } else if (event.type === "done") {
            setResearchStatus(null);
            const assistantId = streamingAssistantIdRef.current;
            streamingAssistantIdRef.current = null;
            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id !== event.message.id && msg.id !== assistantId) {
                  return msg;
                }
                return {
                  ...event.message,
                  sources: event.message.sources?.length
                    ? event.message.sources
                    : msg.sources,
                  status: "complete",
                };
              }),
            );
            stopPolling();
            sendingRef.current = false;
            setSending(false);
            streamAbortRef.current = null;
          } else if (event.type === "error") {
            streamFailed = true;
            setResearchStatus(null);
            setError(event.detail);
            startPolling();
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          streamAborted = true;
          return;
        }
        streamFailed = true;
        setResearchStatus(null);
        setError(err instanceof ApiError ? err.message : "Failed to send message");
        if (!draft) setDraft(text);
        startPolling();
      } finally {
        streamAbortRef.current = null;
        if (streamAborted) {
          return;
        }
        if (streamFailed) {
          void refreshMessages().catch(() => undefined);
        } else if (sendingRef.current) {
          startPolling();
        }
        setResearchStatus(null);
      }
    },
    [draft, refreshMessages, startPolling, stopPolling],
  );

  useEffect(() => {
    return () => {
      streamAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (loading || seededDiscussRef.current) return;
    if (!isDiscussJobState(location.state)) return;
    seededDiscussRef.current = true;
    const card = location.state[DISCUSS_JOB_STATE_KEY];
    rememberDiscussJob(card);
    navigate(".", { replace: true, state: null });
    void handleSend(buildDiscussJobMessage(card));
  }, [loading, location.state, navigate, handleSend]);

  async function handleClear() {
    if (clearing || sending || messages.length === 0) return;
    const ok = window.confirm("Start a new conversation? This clears the current chat.");
    if (!ok) return;
    setClearing(true);
    setError(null);
    stopPolling();
    streamAbortRef.current?.abort();
    streamAbortRef.current = null;
    sendingRef.current = false;
    setSending(false);
    streamingAssistantIdRef.current = null;
    try {
      const res = await api.career.clearMessages();
      setMessages(res.messages);
      setDraft("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to clear conversation");
    } finally {
      setClearing(false);
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    void handleSend(draft);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {billing?.usage && billing.tier === "free" ? (
        <UsageBanner
          className="mb-3 shrink-0"
          quota={billing.usage.advisor_messages}
          featureLabel="advisor messages"
          stripeConfigured={billing.stripe_configured}
          externalCheckoutAllowed={billing.external_checkout_allowed}
          upgradeBusy={billingBusy}
          onUpgrade={() => {
            setBillingBusy(true);
            void api.billing
              .checkout()
              .then((res) => {
                void openExternalUrl(res.checkout_url);
              })
              .catch((err) => {
                setError(err instanceof ApiError ? err.message : "Could not start checkout");
                setBillingBusy(false);
              });
          }}
        />
      ) : null}
      <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display text-xl tracking-tight text-ink-text sm:text-2xl">
            Career Advisor
          </h1>
          <p className="mt-0.5 truncate text-xs text-muted sm:text-sm">
            Frank fit checks against your saved profile
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={loading || clearing || sending || messages.length === 0}
          onClick={() => void handleClear()}
        >
          {clearing ? "Clearing…" : "New chat"}
        </Button>
      </div>

      {error ? <Alert tone="error" className="mb-2 shrink-0">{error}</Alert> : null}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface">
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-3 sm:p-4">
          {loading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-muted">
              <InlineSpinner label="Loading conversation" />
              Loading conversation…
            </div>
          ) : null}
          {!loading && messages.length === 0 ? (
            <div className="space-y-3 py-2">
              <p className="text-sm text-muted">
                Ask for a realistic fit call. Try one of these:
              </p>
              <div className="flex flex-wrap gap-2">
                {STARTERS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={sending}
                    onClick={() => void handleSend(prompt)}
                    className="rounded-full border border-border bg-surface-raised px-3 py-1.5 text-sm text-muted transition hover:border-muted hover:text-ink-text disabled:opacity-50"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {messages.map((msg) => {
            const waiting =
              msg.role === "assistant" &&
              (msg.status === "pending" || (msg.status !== "failed" && !msg.content));
            const statusLabel =
              waiting && researchStatus
                ? researchStatus
                : waiting
                  ? "Thinking…"
                  : null;
            return (
              <div
                key={msg.id}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed break-words ${
                    msg.role === "user"
                      ? "whitespace-pre-wrap bg-brand-strong text-on-brand"
                      : "border border-border bg-surface-raised text-ink-text"
                  }`}
                >
                  {msg.role === "user" ? (
                    msg.content
                  ) : waiting ? (
                    <span className="flex items-center gap-2 text-muted">
                      <InlineSpinner label="Advisor is working" />
                      {statusLabel}
                    </span>
                  ) : msg.status === "cancelled" ? (
                    msg.content && msg.content !== "Response stopped." ? (
                      <ChatMarkdown content={msg.content} />
                    ) : (
                      <span className="text-muted">Response stopped.</span>
                    )
                  ) : msg.status === "failed" ? (
                    <span className="text-muted">{msg.content}</span>
                  ) : (
                    <>
                      <ChatMarkdown content={msg.content} />
                      {msg.sources?.length ? <MessageSources sources={msg.sources} /> : null}
                    </>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={handleSubmit} className="shrink-0 border-t border-border-subtle p-2.5 sm:p-3">
          <FieldTextarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={2}
            placeholder="Ask about roles, skills, or your next move…"
            disabled={sending}
            className="max-h-28 resize-none"
          />
          <div className="mt-2">
            {sending ? (
              <Button type="button" variant="secondary" fullWidth onClick={() => void handleStop()}>
                Stop
              </Button>
            ) : (
              <Button type="submit" fullWidth disabled={!draft.trim()}>
                Send
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
