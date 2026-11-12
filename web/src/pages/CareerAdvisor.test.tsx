import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CareerAdvisorPage } from "./CareerAdvisor";

const { sendMessageStream, cancelMessage } = vi.hoisted(() => ({
  sendMessageStream: vi.fn(),
  cancelMessage: vi.fn(),
}));

vi.mock("../api/client", () => ({
  api: {
    career: {
      messages: vi.fn(async () => ({ messages: [] })),
      clearMessages: vi.fn(async () => ({ messages: [] })),
      sendMessageStream,
      cancelMessage,
    },
  },
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message);
      this.name = "ApiError";
    }
  },
}));

async function* streamEvents(events: Array<Record<string, unknown>>) {
  for (const event of events) {
    yield event;
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <CareerAdvisorPage />
    </MemoryRouter>,
  );
}

describe("CareerAdvisor chat flow", () => {
  beforeEach(() => {
    sendMessageStream.mockReset();
    cancelMessage.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("streams a long assistant reply into the chat bubble without error", async () => {
    const longReply =
      "**Lean apply.**\n\n" +
      Array.from({ length: 40 }, (_, i) => `- Evidence point ${i + 1}`).join("\n") +
      "\n\n" +
      "Closing guidance. ".repeat(80);

    sendMessageStream.mockImplementation(async function* () {
      yield* streamEvents([
        { type: "user", id: "user-1", content: "Give me a detailed fit assessment." },
        { type: "token", text: longReply.slice(0, 400) },
        { type: "token", text: longReply.slice(400) },
        {
          type: "done",
          source: "llm",
          message: {
            id: "assistant-1",
            role: "assistant",
            content: longReply,
            source: "llm",
            created_at: new Date().toISOString(),
          },
        },
      ]);
    });

    const user = userEvent.setup();
    renderPage();

    const textarea = await screen.findByPlaceholderText("Ask about roles, skills, or your next move…");
    await user.type(textarea, "Give me a detailed fit assessment.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText(/Lean apply/i)).toBeInTheDocument();
    });

    expect(screen.queryByText(/Advisor failed to respond/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Evidence point 40/)).toBeInTheDocument();
    expect(screen.getByText(/Closing guidance\./)).toBeInTheDocument();
    expect(sendMessageStream).toHaveBeenCalledWith(
      "Give me a detailed fit assessment.",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("shows an error when the stream reports failure", async () => {
    sendMessageStream.mockImplementation(async function* () {
      yield* streamEvents([
        { type: "user", id: "user-2", content: "Hello" },
        { type: "error", detail: "Advisor failed to respond. Try again." },
      ]);
    });

    const user = userEvent.setup();
    renderPage();

    const textarea = await screen.findByPlaceholderText("Ask about roles, skills, or your next move…");
    await user.type(textarea, "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Advisor failed to respond. Try again.")).toBeInTheDocument();
  });

  it("shows a stop button while streaming and cancels the assistant reply", async () => {
    let rejectStream: ((reason?: unknown) => void) | undefined;
    const streamPromise = new Promise<never>((_, reject) => {
      rejectStream = reject;
    });

    sendMessageStream.mockImplementation(async function* (_content: string, options?: { signal?: AbortSignal }) {
      yield {
        type: "user",
        id: "user-3",
        content: "Tell me more",
        assistant_id: "assistant-3",
      };
      yield { type: "token", text: "Partial " };
      options?.signal?.addEventListener("abort", () => {
        rejectStream?.(new DOMException("Aborted", "AbortError"));
      });
      await streamPromise;
    });
    cancelMessage.mockResolvedValue({
      id: "assistant-3",
      role: "assistant",
      content: "Partial ",
      source: "llm",
      status: "cancelled",
      created_at: new Date().toISOString(),
    });

    const user = userEvent.setup();
    renderPage();

    const textarea = await screen.findByPlaceholderText("Ask about roles, skills, or your next move…");
    await user.type(textarea, "Tell me more");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("button", { name: "Stop" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() => {
      expect(cancelMessage).toHaveBeenCalledWith("assistant-3");
    });
  });
});
