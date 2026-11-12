import { describe, expect, it } from "vitest";
import {
  decodeHtmlEntities,
  looksLikeHtml,
  normalizeJobDescriptionText,
  plainTextToHtml,
  prepareJobDescriptionHtml,
} from "./formatJobDescription";

describe("formatJobDescription", () => {
  it("decodes escaped Greenhouse HTML", () => {
    const escaped = "&lt;p&gt;Hello &amp; welcome&lt;/p&gt;";
    expect(decodeHtmlEntities(escaped)).toBe("<p>Hello & welcome</p>");
    expect(looksLikeHtml(decodeHtmlEntities(escaped))).toBe(true);
  });

  it("formats plain text sections and bullets", () => {
    const plain = `The Role

We're looking for engineers.

Requirements:
- Python experience
- Kubernetes knowledge`;

    const html = plainTextToHtml(plain);
    expect(html).toContain("<h3>The Role</h3>");
    expect(html).toContain("<p>We're looking for engineers.</p>");
    expect(html).toContain("<h3>Requirements</h3>");
    expect(html).toContain("<li>Python experience</li>");
    expect(html).toContain("<li>Kubernetes knowledge</li>");
  });

  it("prepares escaped HTML for sanitization", () => {
    const escaped = "&lt;ul&gt;&lt;li&gt;Item&lt;/li&gt;&lt;/ul&gt;";
    expect(prepareJobDescriptionHtml(escaped)).toBe("<ul><li>Item</li></ul>");
  });

  it("normalizes without losing real HTML", () => {
    const html = "<p>Already formatted</p>";
    expect(normalizeJobDescriptionText(html)).toBe(html);
    expect(prepareJobDescriptionHtml(html)).toBe(html);
  });
});
