import type { ApplicationPacket } from "../types";

function identityField(identity: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = identity[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

/** Build a paste-friendly cover letter with contact header. */
export function formatApplicationKit(
  packet: ApplicationPacket,
  coverLetter: string,
): string {
  const lines: string[] = [];

  const name = identityField(packet.identity, "preferred_name", "full_name", "name");
  const email = identityField(packet.identity, "email");
  const phone = identityField(packet.identity, "phone");

  if (name || email || phone) {
    if (name) lines.push(name);
    if (email) lines.push(email);
    if (phone) lines.push(phone);
    lines.push("");
  }

  const letter = coverLetter.trim();
  if (letter) {
    lines.push(letter);
  }

  return lines.join("\n").trim();
}

export async function copyText(text: string): Promise<void> {
  if (!text.trim()) return;
  await navigator.clipboard.writeText(text);
}
