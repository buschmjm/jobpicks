/** Hide the template's embedded print bar; the app shell provides Print / Save PDF. */
export function prepareResumePreviewHtml(html: string): string {
  const style = "<style>.print-actions{display:none!important}</style>";
  if (html.includes("</head>")) {
    return html.replace("</head>", `${style}</head>`);
  }
  return `${style}${html}`;
}
