import DOMPurify from "dompurify";
import { useMemo } from "react";
import { prepareJobDescriptionHtml } from "../lib/formatJobDescription";

const SANITIZE_CONFIG = {
  ALLOWED_TAGS: [
    "p",
    "br",
    "div",
    "span",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "a",
    "blockquote",
    "hr",
    "pre",
    "code",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
  ],
  ALLOWED_ATTR: ["href", "class"],
};

let linkHookRegistered = false;

function ensureLinkHook(): void {
  if (linkHookRegistered) {
    return;
  }
  DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
  linkHookRegistered = true;
}

function sanitizeHtml(html: string): string {
  ensureLinkHook();
  return DOMPurify.sanitize(html, SANITIZE_CONFIG);
}

interface JobDescriptionProps {
  text: string;
}

export function JobDescription({ text }: JobDescriptionProps) {
  const sanitizedHtml = useMemo(() => {
    const prepared = prepareJobDescriptionHtml(text);
    if (!prepared) {
      return null;
    }
    return sanitizeHtml(prepared);
  }, [text]);

  if (!text.trim()) {
    return <p className="italic text-subtle">No description provided.</p>;
  }

  if (sanitizedHtml) {
    return (
      <div
        className="job-description"
        dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
      />
    );
  }

  return <p className="italic text-subtle">No description provided.</p>;
}
