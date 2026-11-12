import { useState } from "react";
import { api, ApiError } from "../api/client";
import { ChatMarkdown } from "./ChatMarkdown";
import { Button } from "./ui/Button";
import { FieldGroup, FieldTextarea } from "./ui/Field";

type Props = {
  todoId: string;
};

export function ApplicationAssistPanel({ todoId }: Props) {
  const [question, setQuestion] = useState("");
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function runAssist() {
    const q = question.trim();
    if (!q || streaming) return;
    setStreaming(true);
    setError(null);
    setDraft("");
    setCopied(false);
    try {
      for await (const evt of api.todo.packetAssistStream(todoId, { question: q })) {
        if (evt.type === "token") setDraft((current) => current + evt.text);
        else if (evt.type === "done") setDraft(evt.reply || "");
        else if (evt.type === "error") setError(evt.detail);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not draft an answer");
    } finally {
      setStreaming(false);
    }
  }

  async function handleCopy() {
    if (!draft.trim()) return;
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy answer");
    }
  }

  return (
    <div className="space-y-3">
      <FieldGroup label="Ask about an application question">
        <p className="mt-1 text-xs text-muted">
          Paste a question from the employer site and get a draft grounded in your resume and this
          job.
        </p>
        <FieldTextarea
          rows={3}
          value={question}
          disabled={streaming}
          placeholder="Example: Why do you want to work here?"
          onChange={(event) => setQuestion(event.target.value)}
        />
      </FieldGroup>

      <Button disabled={streaming || !question.trim()} onClick={() => void runAssist()}>
        {streaming ? "Drafting…" : "Draft answer"}
      </Button>

      {error ? <p className="text-sm text-decline">{error}</p> : null}

      {draft ? (
        <div className="rounded-[var(--radius-button)] border border-border bg-surface-raised p-3">
          <ChatMarkdown content={draft} />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={() => void handleCopy()}>
              {copied ? "Copied" : "Copy answer"}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
