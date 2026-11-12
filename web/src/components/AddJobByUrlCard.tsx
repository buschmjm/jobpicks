import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Button } from "./ui/Button";
import { FieldInput } from "./ui/Field";

type AddJobByUrlCardProps = {
  className?: string;
  onError?: (message: string) => void;
};

export function AddJobByUrlCard({ className = "", onError }: AddJobByUrlCardProps) {
  const navigate = useNavigate();
  const [applyUrl, setApplyUrl] = useState("");
  const [importing, setImporting] = useState(false);

  async function handleImportByUrl(event: FormEvent) {
    event.preventDefault();
    const trimmed = applyUrl.trim();
    if (!trimmed) return;

    setImporting(true);
    try {
      const result = await api.jobs.importFromUrl(trimmed, true);
      void api.engagement.heartbeat("prepare_open").catch(() => undefined);
      navigate(`/todo/${result.todo_item_id}/prepare`);
    } catch (err) {
      onError?.(err instanceof ApiError ? err.message : "Failed to import job from URL");
    } finally {
      setImporting(false);
    }
  }

  return (
    <form
      onSubmit={(e) => void handleImportByUrl(e)}
      className={`flex flex-col gap-1.5 sm:flex-row sm:items-center ${className}`}
    >
      <FieldInput
        type="url"
        name="apply_url"
        aria-label="Apply page URL"
        placeholder="Paste Greenhouse or Lever apply URL"
        value={applyUrl}
        onChange={(event) => setApplyUrl(event.target.value)}
        className="mt-0 flex-1 py-2 text-sm"
        required
      />
      <Button
        type="submit"
        size="sm"
        className="shrink-0 sm:w-auto"
        disabled={importing || !applyUrl.trim()}
      >
        {importing ? "Importing…" : "Import"}
      </Button>
    </form>
  );
}
