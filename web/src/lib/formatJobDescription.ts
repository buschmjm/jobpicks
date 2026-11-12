const HTML_TAG = /<\/?[a-z][\s\S]*?>/i;
const HTML_ENTITY = /&(?:#\d+|#x[0-9a-f]+|[a-z]+);/i;
const BULLET_LINE = /^[\t ]*[-*•●]\s+/;
const SECTION_HEADER = /^.{1,100}$/;

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Decode HTML entities (Greenhouse API returns escaped markup). */
export function decodeHtmlEntities(text: string): string {
  if (!HTML_ENTITY.test(text)) {
    return text;
  }
  if (typeof document !== "undefined") {
    const el = document.createElement("textarea");
    el.innerHTML = text;
    return el.value;
  }
  return text
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&amp;/gi, "&");
}

export function looksLikeHtml(text: string): boolean {
  return HTML_TAG.test(text);
}

function isSectionHeader(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed || trimmed.length > 100) {
    return false;
  }
  if (BULLET_LINE.test(trimmed)) {
    return false;
  }
  if (trimmed.endsWith(":")) {
    return true;
  }
  if (!SECTION_HEADER.test(trimmed)) {
    return false;
  }
  if (/[.!?]$/.test(trimmed)) {
    return false;
  }
  return true;
}

function blockToHtml(block: string): string {
  const lines = block.split("\n").map((line) => line.trimEnd());
  const nonEmpty = lines.filter((line) => line.trim().length > 0);
  if (nonEmpty.length === 0) {
    return "";
  }

  if (nonEmpty.length === 1 && isSectionHeader(nonEmpty[0])) {
    return `<h3>${escapeHtml(nonEmpty[0].replace(/:$/, ""))}</h3>`;
  }

  if (nonEmpty.every((line) => BULLET_LINE.test(line))) {
    const items = nonEmpty
      .map((line) => line.replace(BULLET_LINE, "").trim())
      .filter(Boolean)
      .map((line) => `<li>${escapeHtml(line)}</li>`)
      .join("");
    return `<ul>${items}</ul>`;
  }

  const chunks: string[] = [];
  let bulletBuffer: string[] = [];

  const flushBullets = () => {
    if (bulletBuffer.length === 0) {
      return;
    }
    const items = bulletBuffer
      .map((line) => `<li>${escapeHtml(line.replace(BULLET_LINE, "").trim())}</li>`)
      .join("");
    chunks.push(`<ul>${items}</ul>`);
    bulletBuffer = [];
  };

  for (const line of nonEmpty) {
    if (BULLET_LINE.test(line)) {
      bulletBuffer.push(line);
      continue;
    }
    flushBullets();
    if (isSectionHeader(line)) {
      chunks.push(`<h3>${escapeHtml(line.replace(/:$/, ""))}</h3>`);
    } else {
      chunks.push(`<p>${escapeHtml(line)}</p>`);
    }
  }
  flushBullets();

  return chunks.join("");
}

/** Turn plain-text postings (Lever, Adzuna, etc.) into simple semantic HTML. */
export function plainTextToHtml(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((block) => blockToHtml(block.trim()))
    .filter(Boolean)
    .join("");
}

/** Normalize stored description text for display. */
export function normalizeJobDescriptionText(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return "";
  }

  let normalized = decodeHtmlEntities(trimmed);
  if (HTML_ENTITY.test(normalized) && !looksLikeHtml(normalized)) {
    normalized = decodeHtmlEntities(normalized);
  }
  return normalized;
}

export function prepareJobDescriptionHtml(text: string): string | null {
  const normalized = normalizeJobDescriptionText(text);
  if (!normalized) {
    return null;
  }
  if (looksLikeHtml(normalized)) {
    return normalized;
  }
  return plainTextToHtml(normalized);
}

/** Detect API snippets that end mid-sentence (e.g. Adzuna's 500-char cap). */
export function descriptionLooksTruncated(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) {
    return false;
  }
  if (trimmed.endsWith("…") || trimmed.endsWith("...")) {
    return true;
  }
  return trimmed.length === 500 && !/[.!?]$/.test(trimmed);
}
