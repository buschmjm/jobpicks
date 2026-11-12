import type { MatchCard } from "../types";

export const DISCUSS_JOB_STATE_KEY = "discussJob" as const;

export type DiscussJobState = {
  [DISCUSS_JOB_STATE_KEY]: MatchCard;
};

/** Soft ceiling for pathological posts; matches API CareerMessageCreate.max_length. */
export const MAX_DISCUSS_MESSAGE_CHARS = 100_000;

function joinBullets(label: string, bullets: string[], limit: number): string {
  if (bullets.length === 0) return "";
  const lines = bullets.slice(0, limit).map((b) => `- ${b}`);
  return `${label}:\n${lines.join("\n")}`;
}

/** Turn HTML job posts into readable plain text for chat + the advisor model. */
export function descriptionToPlainText(raw: string): string {
  const text = (raw || "").trim();
  if (!text) return "";
  if (!/<\/?[a-z][\s\S]*?>/i.test(text)) {
    return text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  if (typeof DOMParser === "undefined") {
    return text
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/(p|div|li|h[1-6]|tr)>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]{2,}/g, " ")
      .trim();
  }
  const doc = new DOMParser().parseFromString(text, "text/html");
  const plain = doc.body.textContent || "";
  return plain.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

/** Build a user message that grounds the advisor on a deck job (full description). */
export function buildDiscussJobMessage(card: MatchCard): string {
  const meta = [
    card.salary_display,
    card.work_mode !== "unknown" ? card.work_mode : null,
    card.location_display,
    card.commute_display,
  ]
    .filter(Boolean)
    .join(" · ");

  const parts = [
    `Give me a frank fit assessment for this posting. Say clearly whether I should apply, lean apply, lean skip, or skip — and why, based on my profile vs the requirements.`,
    ``,
    `Job: ${card.title} at ${card.company}`,
    `Match score: ${Math.round(card.match_score)}%`,
    meta ? `Details: ${meta}` : null,
    card.source_url ? `Posting: ${card.source_url}` : null,
    joinBullets("Why it matched", card.why_bullets, 4),
    joinBullets("Cautions", card.caution_bullets, 3),
  ].filter((p): p is string => Boolean(p));

  let message = parts.join("\n");
  const desc = descriptionToPlainText(card.description || "");
  if (desc) {
    message = `${message}\n\nFull job description:\n${desc}`;
  }

  if (message.length > MAX_DISCUSS_MESSAGE_CHARS) {
    // Extremely rare; keep the ask + meta and as much of the description as fits.
    message = `${message.slice(0, MAX_DISCUSS_MESSAGE_CHARS - 80)}\n\n[Job description truncated for length; use the posting URL for the remainder.]`;
  }
  return message;
}

export function isDiscussJobState(state: unknown): state is DiscussJobState {
  if (!state || typeof state !== "object") return false;
  const job = (state as DiscussJobState)[DISCUSS_JOB_STATE_KEY];
  return Boolean(job && typeof job === "object" && typeof job.title === "string");
}
