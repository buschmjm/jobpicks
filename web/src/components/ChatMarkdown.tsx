import DOMPurify from "dompurify";
import { useMemo } from "react";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatInline(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/__(.+?)__/g, "<strong>$1</strong>");
  out = out.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
  out = out.replace(/(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g, "<em>$1</em>");
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  return out;
}

/** Minimal markdown → HTML for chat bubbles (bold, italics, lists, paragraphs). */
export function markdownToSafeHtml(markdown: string): string {
  const normalized = markdown.replace(/\r\n/g, "\n").trimEnd();
  if (!normalized.trim()) return "";

  const lines = normalized.split("\n");
  const blocks: string[] = [];
  let listTag: "ul" | "ol" | null = null;
  let listItems: string[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${paragraph.join("<br />")}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listTag) return;
    blocks.push(`<${listTag}>${listItems.map((item) => `<li>${item}</li>`).join("")}</${listTag}>`);
    listTag = null;
    listItems = [];
  };

  for (const line of lines) {
    const ul = line.match(/^[ \t]*[-*•]\s+(.+)$/);
    const ol = line.match(/^[ \t]*\d+\.\s+(.+)$/);
    if (ul) {
      flushParagraph();
      if (listTag && listTag !== "ul") flushList();
      listTag = "ul";
      listItems.push(formatInline(ul[1]));
      continue;
    }
    if (ol) {
      flushParagraph();
      if (listTag && listTag !== "ol") flushList();
      listTag = "ol";
      listItems.push(formatInline(ol[1]));
      continue;
    }
    if (!line.trim()) {
      flushList();
      flushParagraph();
      continue;
    }
    flushList();
    paragraph.push(formatInline(line));
  }
  flushList();
  flushParagraph();

  return DOMPurify.sanitize(blocks.join(""), {
    ALLOWED_TAGS: ["p", "br", "strong", "em", "ul", "ol", "li", "code", "a"],
    ALLOWED_ATTR: ["href", "target", "rel"],
  });
}

export function ChatMarkdown({
  content,
  className = "",
}: {
  content: string;
  className?: string;
}) {
  const html = useMemo(() => markdownToSafeHtml(content), [content]);
  if (!html) return null;
  return (
    <div
      className={`chat-markdown ${className}`.trim()}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
