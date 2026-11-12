import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ChatMarkdown } from "../components/ChatMarkdown";
import { ResumeLivePreview } from "../components/ResumeLivePreview";
import { ResumePreviewSheet } from "../components/ResumePreviewSheet";
import { ResumeProposalCard } from "../components/ResumeProposalCard";
import { ResumeVariantPicker } from "../components/ResumeVariantPicker";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { FieldTextarea } from "../components/ui/Field";
import { InlineSpinner } from "../components/ui/NavIcon";
import type { ResumeBuilderMessage, ResumeProposal, ResumeVariant, TodoItem } from "../types";

const STARTERS = [
  "Strengthen my summary for senior engineering roles.",
  "Which accomplishments should I highlight for product management?",
  "Make my resume more concise without losing impact.",
];

export function ResumeBuilderChatPage() {
  const [searchParams] = useSearchParams();
  const todoId = searchParams.get("todo_id");
  const [jobContext, setJobContext] = useState<TodoItem | null>(null);
  const [variant, setVariant] = useState<ResumeVariant | null>(null);
  const [messages, setMessages] = useState<ResumeBuilderMessage[]>([]);
  const [proposals, setProposals] = useState<Record<string, ResumeProposal>>({});
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewDraftId, setPreviewDraftId] = useState<string | null>(null);
  const [previewRefreshKey, setPreviewRefreshKey] = useState(0);
  const [previewOpen, setPreviewOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);
  const streamingAssistantIdRef = useRef<string | null>(null);

  const pendingProposals = useMemo(
    () => Object.values(proposals).filter((p) => p.status === "pending"),
    [proposals],
  );

  const refreshProposals = useCallback(async (variantId: string | null) => {
    if (!variantId) {
      setProposals({});
      return;
    }
    const res = await api.resume.chat.listProposals(variantId);
    setProposals(Object.fromEntries(res.proposals.map((p) => [p.id, p])));
  }, []);

  const refreshMessages = useCallback(
    async (variantId: string | null) => {
      if (!variantId) {
        setMessages([]);
        return [];
      }
      const res = await api.resume.chat.listMessages(variantId);
      setMessages(res.messages);
      return res.messages;
    },
    [],
  );

  const refreshPreviewDraft = useCallback(async () => {
    try {
      const draft = await api.resume.buildMaster();
      setPreviewDraftId(draft.id);
      setPreviewRefreshKey((k) => k + 1);
    } catch {
      setPreviewRefreshKey((k) => k + 1);
    }
  }, []);

  useEffect(() => {
    if (!todoId) {
      setJobContext(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const todo = await api.todo.get(todoId);
        if (!cancelled) setJobContext(todo);
      } catch {
        if (!cancelled) setJobContext(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [todoId]);

  const jobStarters = useMemo(() => {
    if (!jobContext) return [];
    const role = `${jobContext.title} at ${jobContext.company}`;
    return [
      `Tailor my resume for ${role}.`,
      `Which accomplishments should I emphasize for ${jobContext.title}?`,
      `Strengthen my summary for this ${jobContext.title} application.`,
    ];
  }, [jobContext]);

  const starters = jobStarters.length > 0 ? jobStarters : STARTERS;

  useEffect(() => {
    void refreshPreviewDraft();
  }, [refreshPreviewDraft]);

  useEffect(() => {
    if (!variant?.id) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        await Promise.all([refreshMessages(variant.id), refreshProposals(variant.id)]);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Failed to load resume builder");
      } finally {
        setLoading(false);
      }
    })();
  }, [variant?.id, refreshMessages, refreshProposals]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, pendingProposals.length]);

  const handleSend = useCallback(
    async (content: string) => {
      const text = content.trim();
      if (!text || sendingRef.current || !variant?.id) return;
      sendingRef.current = true;
      setSending(true);
      setError(null);
      setDraft("");
      streamingAssistantIdRef.current = null;

      const pendingUser: ResumeBuilderMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      };
      const pendingAssistant: ResumeBuilderMessage = {
        id: `local-assistant-${Date.now()}`,
        role: "assistant",
        content: "",
        status: "pending",
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, pendingUser, pendingAssistant]);
      streamingAssistantIdRef.current = pendingAssistant.id;

      let streamFailed = false;
      try {
        for await (const event of api.resume.chat.sendStream(text, variant.id)) {
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
          } else if (event.type === "token") {
            const assistantId = streamingAssistantIdRef.current;
            if (!assistantId) continue;
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId ? { ...msg, content: msg.content + event.text } : msg,
              ),
            );
          } else if (event.type === "proposal") {
            setProposals((prev) => ({ ...prev, [event.proposal.id]: event.proposal }));
            const assistantId = streamingAssistantIdRef.current;
            if (assistantId) {
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId ? { ...msg, proposal_id: event.proposal.id } : msg,
                ),
              );
            }
          } else if (event.type === "done") {
            const assistantId = streamingAssistantIdRef.current;
            streamingAssistantIdRef.current = null;
            setMessages((prev) =>
              prev.map((msg) => {
                if (msg.id !== event.message.id && msg.id !== assistantId) {
                  return msg;
                }
                return {
                  ...event.message,
                  proposal_id: event.message.proposal_id ?? msg.proposal_id,
                  status: "complete",
                };
              }),
            );
            sendingRef.current = false;
            setSending(false);
          } else if (event.type === "error") {
            streamFailed = true;
            setError(event.detail);
          }
        }
      } catch (err) {
        streamFailed = true;
        setError(err instanceof ApiError ? err.message : "Failed to send message");
        if (!draft) setDraft(text);
      } finally {
        if (streamFailed) {
          sendingRef.current = false;
          setSending(false);
          if (variant?.id) {
            void refreshMessages(variant.id).catch(() => undefined);
          }
        } else if (sendingRef.current) {
          sendingRef.current = false;
          setSending(false);
        }
      }
    },
    [draft, refreshMessages, variant?.id],
  );

  async function handleClear() {
    if (clearing || sending || !variant?.id || messages.length === 0) return;
    const ok = window.confirm("Start a new conversation? This clears the current chat.");
    if (!ok) return;
    setClearing(true);
    setError(null);
    sendingRef.current = false;
    setSending(false);
    streamingAssistantIdRef.current = null;
    try {
      const res = await api.resume.chat.clearMessages(variant.id);
      setMessages(res.messages);
      setProposals({});
      setDraft("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to clear conversation");
    } finally {
      setClearing(false);
    }
  }

  function handleProposalApplied(proposal: ResumeProposal) {
    setProposals((prev) => ({ ...prev, [proposal.id]: proposal }));
    void refreshPreviewDraft();
  }

  function handleProposalDismissed(proposal: ResumeProposal) {
    setProposals((prev) => ({ ...prev, [proposal.id]: proposal }));
  }

  function handleProposalEdit(proposal: ResumeProposal) {
    setDraft(`Please revise this proposal: ${proposal.preview_summary}`);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    void handleSend(draft);
  }

  function proposalsForMessage(message: ResumeBuilderMessage): ResumeProposal[] {
    if (!message.proposal_id) return [];
    const proposal = proposals[message.proposal_id];
    return proposal && proposal.status === "pending" ? [proposal] : [];
  }

  const orphanProposals = pendingProposals.filter(
    (p) => !messages.some((m) => m.proposal_id === p.id),
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="font-display text-xl tracking-tight text-ink-text sm:text-2xl">
            Resume builder
          </h1>
          <p className="mt-0.5 truncate text-xs text-muted sm:text-sm">
            Chat to refine your resume
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!previewDraftId}
            onClick={() => setPreviewOpen(true)}
          >
            Preview
          </Button>
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
      </div>

      <div className="mb-3 shrink-0">
        <ResumeVariantPicker selectedId={variant?.id ?? null} onChange={setVariant} />
      </div>

      {jobContext ? (
        <Alert tone="info" className="mb-3 shrink-0">
          <span className="font-semibold">Application target:</span> {jobContext.title} at{" "}
          {jobContext.company}
          {todoId ? (
            <>
              {" "}
              ·{" "}
              <Link
                to={`/todo/${todoId}/prepare`}
                className="font-semibold text-brand-strong hover:text-brand-deep"
              >
                Back to application help
              </Link>
            </>
          ) : null}
        </Alert>
      ) : null}

      {error ? <Alert tone="error" className="mb-2 shrink-0">{error}</Alert> : null}

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-2">
        <div className="flex min-h-0 flex-col overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain p-3 sm:p-4">
            {loading ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted">
                <InlineSpinner label="Loading conversation" />
                Loading conversation…
              </div>
            ) : null}
            {!loading && !variant ? (
              <p className="py-4 text-sm text-muted">Create a resume variant to start building.</p>
            ) : null}
            {!loading && variant && messages.length === 0 ? (
              <div className="space-y-3 py-2">
                <p className="text-sm text-muted">
                  {jobContext
                    ? `Tell the builder how to position your resume for ${jobContext.title}. Try one of these:`
                    : "Tell the builder what to improve. Try one of these:"}
                </p>
                <div className="flex flex-wrap gap-2">
                  {starters.map((prompt) => (
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
              const relatedProposals = proposalsForMessage(msg);
              return (
                <div key={msg.id} className="space-y-2">
                  <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
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
                          <InlineSpinner label="Builder is working" />
                          Thinking…
                        </span>
                      ) : msg.status === "failed" ? (
                        <span className="text-muted">{msg.content}</span>
                      ) : (
                        <ChatMarkdown content={msg.content} />
                      )}
                    </div>
                  </div>
                  {relatedProposals.map((proposal) => (
                    <ResumeProposalCard
                      key={proposal.id}
                      proposal={proposal}
                      onApplied={handleProposalApplied}
                      onDismissed={handleProposalDismissed}
                      onEdit={handleProposalEdit}
                    />
                  ))}
                </div>
              );
            })}
            {orphanProposals.map((proposal) => (
              <ResumeProposalCard
                key={proposal.id}
                proposal={proposal}
                onApplied={handleProposalApplied}
                onDismissed={handleProposalDismissed}
                onEdit={handleProposalEdit}
              />
            ))}
            <div ref={bottomRef} />
          </div>

          <form
            onSubmit={handleSubmit}
            className="shrink-0 border-t border-border-subtle p-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom))] sm:p-3"
          >
            <FieldTextarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              placeholder="Ask to improve summary, bullets, or emphasis…"
              disabled={sending || !variant}
              className="max-h-28 resize-none"
            />
            <Button
              type="submit"
              fullWidth
              className="mt-2"
              disabled={sending || !draft.trim() || !variant}
            >
              {sending ? (
                <span className="inline-flex items-center justify-center gap-2">
                  <InlineSpinner label="Sending" />
                  Writing…
                </span>
              ) : (
                "Send"
              )}
            </Button>
          </form>
        </div>

        <div className="hidden min-h-0 lg:flex lg:flex-col">
          <ResumeLivePreview draftId={previewDraftId} refreshKey={previewRefreshKey} />
        </div>
      </div>

      {previewOpen && previewDraftId ? (
        <ResumePreviewSheet
          draftId={previewDraftId}
          refreshKey={previewRefreshKey}
          onClose={() => setPreviewOpen(false)}
        />
      ) : null}
    </div>
  );
}
