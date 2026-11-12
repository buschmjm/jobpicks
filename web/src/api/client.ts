import type {
  ApplicationStep,
  DeckNextResponse,
  DeckStatusResponse,
  Education,
  Experience,
  LeftSwipeReason,
  ParsedProfile,
  ProfileFact,
  ProfileIdentity,
  ResumeBuilderMessage,
  ResumeProposal,
  ResumeVariant,
  SessionUser,
  Skill,
  SwipeAction,
  SwipeResponse,
  JobFromUrlResponse,
  TodoItem,
  TodoStatus,
} from "../types";
import { parseSseJson } from "./sse";
import { appStorefrontHeaders } from "../lib/storefront";
import { API_BASE } from "../lib/mountPath";

let accessToken: string | null = null;
let refreshAccessToken: (() => Promise<string | null>) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function setAccessTokenRefresher(fn: (() => Promise<string | null>) | null) {
  refreshAccessToken = fn;
}

async function authorizedFetch(url: string, init: RequestInit = {}, retried = false): Promise<Response> {
  const headers = new Headers(init.headers);
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  const res = await fetch(url, {
    ...init,
    credentials: init.credentials ?? "include",
    headers,
  });
  if (res.status === 401 && !retried && refreshAccessToken) {
    const next = await refreshAccessToken();
    if (next && next !== accessToken) {
      setAccessToken(next);
      return authorizedFetch(url, init, true);
    }
  }
  return res;
}

export function getAccessToken(): string | null {
  return accessToken;
}

import { ApiError } from "./errors";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...appStorefrontHeaders(),
    ...(options.headers as Record<string, string> | undefined),
  };
  const res = await authorizedFetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, String(detail));
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export const api = {
  auth: {
    config: () =>
      request<{
        mode: "keycloak" | "legacy";
        authority?: string;
        client_id?: string;
        token_endpoint?: string;
      }>("/auth/config"),

    me: () => request<SessionUser>("/auth/me"),

    logout: () => request<void>("/auth/logout", { method: "POST" }),
  },

  config: {
    client: () => request<import("../types").ClientConfig>("/config/client"),
  },

  onboarding: {
    uploadResume: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await authorizedFetch(`${API_BASE}/onboarding/resume`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body.detail ?? "Upload failed");
      }
      return res.json() as Promise<{
        upload_id: string;
        filename: string;
        size_bytes: number;
        parsed_profile: ParsedProfile;
        message: string;
      }>;
    },

    confirmProfile: (
      facts: ProfileFact[],
      skillIds: string[],
      experiences: Experience[],
      education: Education[],
      identity?: ProfileIdentity,
    ) =>
      request<{
        profile_id: string;
        facts: ProfileFact[];
        skills: Skill[];
        experiences: Experience[];
        education: Education[];
        identity?: ProfileIdentity;
        message: string;
      }>("/onboarding/profile/confirm", {
        method: "POST",
        body: JSON.stringify({
          facts,
          skill_ids: skillIds,
          experiences,
          education,
          identity: identity ?? null,
        }),
      }),

    submitQuestionnaire: (data: {
      target_titles: string[];
      min_salary?: number | null;
      home_location?: string | null;
      home_lat?: number | null;
      home_lon?: number | null;
      max_commute_minutes?: number | null;
      remote_openness?: string;
      locations?: string[];
      remote_preference?: string;
      industries_to_avoid: string[];
      free_text_goals?: string | null;
      referral_code?: string | null;
      timezone?: string | null;
    }) =>
      request<{ user_id: string; onboarding_complete: boolean; message: string }>(
        "/onboarding/questionnaire",
        { method: "POST", body: JSON.stringify(data) },
      ),
  },

  preferences: {
    get: () => request<import("../types").UserPreferences>("/preferences"),

    update: (data: {
      home_location?: string | null;
      home_lat?: number | null;
      home_lon?: number | null;
      max_commute_minutes?: number | null;
      remote_openness: string;
      target_titles?: string[];
      min_salary?: number | null;
      free_text_goals?: string | null;
    }) =>
      request<{ preferences: import("../types").UserPreferences; message: string }>(
        "/preferences",
        { method: "PATCH", body: JSON.stringify(data) },
      ),
  },

  aiSettings: {
    get: () => request<import("../types").UserAiSettings>("/ai-settings"),
    update: (body: {
      provider: import("../types").AiProvider;
      chat_model?: string | null;
      api_key?: string | null;
      clear_api_key?: boolean;
      auto_prepare_packets?: boolean;
    }) =>
      request<import("../types").UserAiSettings>("/ai-settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
  },

    profile: {
    getResume: () =>
      request<{
        profile_id: string;
        identity: ProfileIdentity;
        experiences: Experience[];
        education: Education[];
      }>("/profile/resume"),

    updateResume: (data: {
      identity?: ProfileIdentity;
      experiences: Experience[];
      education: Education[];
    }) =>
      request<{
        profile_id: string;
        identity: ProfileIdentity;
        experiences: Experience[];
        education: Education[];
        message: string;
      }>("/profile/resume", {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    uploadResume: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await authorizedFetch(`${API_BASE}/profile/resume/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new ApiError(res.status, body.detail ?? "Upload failed");
      }
      return res.json() as Promise<{
        profile_id: string;
        identity: ProfileIdentity;
        experiences: Experience[];
        education: Education[];
        filename: string;
        message: string;
      }>;
    },
  },

  resume: {
    buildMaster: () => request<import("../types").ResumeDraft>("/resume/master", { method: "POST" }),

    tailor: (data: {
      job_id?: string | null;
      title?: string;
      company?: string;
      description?: string;
      source_url?: string;
      why_bullets?: string[];
      caution_bullets?: string[];
    }) =>
      request<{
        draft: import("../types").ResumeDraft;
        source: "llm" | "template";
        message: string;
      }>("/resume/tailor", { method: "POST", body: JSON.stringify(data) }),

    getDraft: (id: string) => request<import("../types").ResumeDraft>(`/resume/drafts/${id}`),

    updateDraft: (id: string, document: import("../types").ResumeDocument, status?: "draft" | "accepted") =>
      request<import("../types").ResumeDraft>(`/resume/drafts/${id}`, {
        method: "PUT",
        body: JSON.stringify({ document, status: status ?? null }),
      }),

    acceptDraft: (id: string) =>
      request<import("../types").ResumeDraft>(`/resume/drafts/${id}/accept`, { method: "POST" }),

    fetchHtml: async (id: string) => {
      const res = await authorizedFetch(`${API_BASE}/resume/drafts/${id}/html`);
      if (!res.ok) {
        let message = "Failed to load resume HTML";
        try {
          const body = await res.json();
          if (typeof body.detail === "string" && body.detail.trim()) {
            message = body.detail;
          } else if (body.detail != null) {
            message = `${message} (${res.status})`;
          } else {
            message = `${message} (${res.status})`;
          }
        } catch {
          message = `${message} (${res.status})`;
        }
        throw new ApiError(res.status, message);
      }
      return res.text();
    },

    chat: {
      listMessages: (variantId?: string | null) => {
        const qs = variantId ? `?variant_id=${encodeURIComponent(variantId)}` : "";
        return request<import("../types").ResumeBuilderThreadResponse>(`/resume/chat/messages${qs}`);
      },

      clearMessages: (variantId?: string | null) => {
        const qs = variantId ? `?variant_id=${encodeURIComponent(variantId)}` : "";
        return request<import("../types").ResumeBuilderThreadResponse>(`/resume/chat/messages${qs}`, {
          method: "DELETE",
        });
      },

      sendStream: async function* (
        content: string,
        variantId?: string | null,
      ): AsyncGenerator<
        | { type: "user"; id: string; content: string; assistant_id?: string }
        | { type: "token"; text: string }
        | { type: "proposal"; proposal: ResumeProposal }
        | { type: "done"; message: ResumeBuilderMessage }
        | { type: "error"; detail: string },
        void
      > {
        const res = await authorizedFetch(`${API_BASE}/resume/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            content,
            variant_id: variantId ?? null,
          }),
        });
        if (!res.ok) {
          let detail = res.statusText;
          try {
            const body = await res.json();
            detail = body.detail ?? detail;
          } catch {
            /* ignore */
          }
          throw new ApiError(res.status, String(detail));
        }
        yield* parseSseJson(res);
      },

      listProposals: (variantId?: string | null, status?: import("../types").ResumeProposalStatus) => {
        const qs = new URLSearchParams();
        if (variantId) qs.set("variant_id", variantId);
        if (status) qs.set("status", status);
        const query = qs.toString();
        return request<import("../types").ResumeProposalsResponse>(
          query ? `/resume/chat/proposals?${query}` : "/resume/chat/proposals",
        );
      },

      applyProposal: (proposalId: string) =>
        request<{ proposal: ResumeProposal; message: string }>(
          `/resume/chat/proposals/${proposalId}/apply`,
          { method: "POST" },
        ),

      rejectProposal: (proposalId: string) =>
        request<ResumeProposal>(`/resume/chat/proposals/${proposalId}/reject`, {
          method: "POST",
        }),
    },

    variants: {
      list: () => request<import("../types").ResumeVariantListResponse>("/resume/variants"),

      create: (data: {
        slug: string;
        label: string;
        emphasis_notes?: string | null;
        is_default?: boolean;
      }) =>
        request<ResumeVariant>("/resume/variants", {
          method: "POST",
          body: JSON.stringify(data),
        }),

      update: (
        variantId: string,
        data: {
          label?: string;
          headline?: string | null;
          summary_override?: string | null;
          target_titles?: string[];
          emphasis_notes?: string | null;
          is_default?: boolean;
        },
      ) =>
        request<ResumeVariant>(`/resume/variants/${variantId}`, {
          method: "PATCH",
          body: JSON.stringify(data),
        }),

      setDefault: (variantId: string) =>
        request<ResumeVariant>(`/resume/variants/${variantId}/set-default`, {
          method: "POST",
        }),
    },
  },

  deck: {
    status: () => request<DeckStatusResponse>("/deck/status"),

    next: () => request<DeckNextResponse>("/deck/next"),

    swipe: (queueItemId: string, action: SwipeAction, reason?: LeftSwipeReason, dwellMs?: number) =>
      request<SwipeResponse>("/deck/swipe", {
        method: "POST",
        body: JSON.stringify({
          queue_item_id: queueItemId,
          action,
          reason: reason ?? null,
          dwell_ms: dwellMs ?? null,
        }),
      }),

    dwell: (queueItemId: string, dwellMs: number) =>
      request<{ recorded: boolean }>("/deck/dwell", {
        method: "POST",
        body: JSON.stringify({ queue_item_id: queueItemId, dwell_ms: dwellMs }),
      }),

    changeDecision: (
      queueItemId: string,
      action: SwipeAction,
      reason?: LeftSwipeReason,
    ) =>
      request<{ success: boolean; action: SwipeAction; todo_item_id?: string | null }>(
        "/deck/change-decision",
        {
          method: "POST",
          body: JSON.stringify({
            queue_item_id: queueItemId,
            action,
            reason: reason ?? null,
          }),
        },
      ),
  },

  todo: {
    list: (status?: TodoStatus) =>
      request<{ items: TodoItem[]; total: number }>(
        status ? `/todo?status=${status}` : "/todo",
      ),

    listPrepared: () =>
      request<{ items: import("../types").PreparedPacketSummary[]; total: number }>(
        "/todo/prepared",
      ),

    get: (itemId: string) => request<TodoItem>(`/todo/${itemId}`),

    update: (itemId: string, body: { status?: TodoStatus; application_steps?: ApplicationStep[] }) =>
      request<TodoItem>(`/todo/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    updateSteps: (itemId: string, steps: ApplicationStep[]) =>
      request<TodoItem>(`/todo/${itemId}/steps`, {
        method: "PUT",
        body: JSON.stringify({ steps }),
      }),

    getStepTemplate: () =>
      request<{ steps: ApplicationStep[] }>("/todo/steps/template"),

    saveStepTemplate: (steps: ApplicationStep[]) =>
      request<{ steps: ApplicationStep[] }>("/todo/steps/template", {
        method: "PUT",
        body: JSON.stringify({ steps }),
      }),

    markApplied: (itemId: string) =>
      request<TodoItem>(`/todo/${itemId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "applied" }),
      }),

    applyClick: (itemId: string) =>
      request<{ source_url: string; todo_item_id: string }>(
        `/todo/${itemId}/apply-click`,
        { method: "POST" },
      ),

    selfReport: (itemId: string, didApply: boolean) =>
      request<TodoItem>(`/todo/${itemId}/self-report`, {
        method: "POST",
        body: JSON.stringify({ did_apply: didApply }),
      }),

    delete: (itemId: string) =>
      request<void>(`/todo/${itemId}`, { method: "DELETE" }),

    generatePacket: (itemId: string) =>
      request<import("../types").ApplicationPacket>(`/todo/${itemId}/packet`, {
        method: "POST",
      }),

    getPacket: (itemId: string) =>
      request<import("../types").ApplicationPacket>(`/todo/${itemId}/packet`),

    getPacketById: (packetId: string) =>
      request<import("../types").ApplicationPacket>(`/todo/packets/${packetId}`),

    patchPacket: (
      itemId: string,
      body: {
        answers?: Array<{
          key: string;
          status: import("../types").PacketAnswerStatus;
          final_answer?: string | null;
          save_to_vault?: boolean;
        }>;
        cover_letter?: string | null;
        label?: string;
      },
    ) =>
      request<import("../types").ApplicationPacket>(`/todo/${itemId}/packet`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    patchPacketById: (
      packetId: string,
      body: {
        answers?: Array<{
          key: string;
          status: import("../types").PacketAnswerStatus;
          final_answer?: string | null;
          save_to_vault?: boolean;
        }>;
        cover_letter?: string | null;
        label?: string;
      },
    ) =>
      request<import("../types").ApplicationPacket>(`/todo/packets/${packetId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),

    reusePacket: (itemId: string, sourcePacketId: string) =>
      request<import("../types").ApplicationPacket>(`/todo/${itemId}/packet/reuse`, {
        method: "POST",
        body: JSON.stringify({ source_packet_id: sourcePacketId }),
      }),

    openPacket: (itemId: string) =>
      request<import("../types").ApplicationPacketOpenResult>(`/todo/${itemId}/packet/open`, {
        method: "POST",
      }),

    packetAssistStream: async function* (
      itemId: string,
      body: { question: string },
    ): AsyncGenerator<
      | { type: "token"; text: string }
      | { type: "done"; reply: string }
      | { type: "error"; detail: string },
      void
    > {
      const res = await authorizedFetch(`${API_BASE}/todo/${itemId}/packet/assist/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const errBody = await res.json();
          detail = errBody.detail ?? detail;
        } catch {
          /* ignore */
        }
        throw new ApiError(res.status, String(detail));
      }
      yield* parseSseJson<
        | { type: "token"; text: string }
        | { type: "done"; reply: string }
        | { type: "error"; detail: string }
      >(res);
    },
  },

  jobs: {
    description: (jobId: string) =>
      request<{ description: string; truncated: boolean }>(`/jobs/${jobId}/description`),

    importFromUrl: (url: string, generatePacket = true) =>
      request<JobFromUrlResponse>("/jobs/from-url", {
        method: "POST",
        body: JSON.stringify({ url, generate_packet: generatePacket }),
      }),
  },

  applicationAnswers: {
    list: () =>
      request<{ items: import("../types").SavedApplicationAnswer[] }>("/application-answers"),

    upsert: (
      questionKey: string,
      body: { question_text: string; answer: string },
    ) =>
      request<import("../types").SavedApplicationAnswer>(
        `/application-answers/${encodeURIComponent(questionKey)}`,
        { method: "PUT", body: JSON.stringify(body) },
      ),

    delete: (questionKey: string) =>
      request<void>(`/application-answers/${encodeURIComponent(questionKey)}`, {
        method: "DELETE",
      }),
  },

  skills: {
    search: (q: string) => {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set("q", q.trim());
      const query = qs.toString();
      return request<{ items: Skill[]; query: string }>(query ? `/skills?${query}` : "/skills");
    },

    create: (name: string) =>
      request<Skill>("/skills", { method: "POST", body: JSON.stringify({ name }) }),
  },

  titles: {
    search: (q: string) => {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set("q", q.trim());
      const query = qs.toString();
      return request<{ items: import("../types").JobTitle[]; query: string }>(
        query ? `/titles?${query}` : "/titles",
      );
    },

    create: (name: string) =>
      request<import("../types").JobTitle>("/titles", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),

    resolve: (names: string[]) =>
      request<{ items: import("../types").JobTitle[]; query: string }>("/titles/resolve", {
        method: "POST",
        body: JSON.stringify({ names }),
      }),
  },

  billing: {
    status: () => request<import("../types").BillingStatus>("/billing/status"),

    checkout: () =>
      request<{ checkout_url: string }>("/billing/checkout", { method: "POST" }),

    portal: () => request<{ portal_url: string }>("/billing/portal", { method: "POST" }),

    cancel: () =>
      request<{
        canceled: boolean;
        cancel_at_period_end: boolean;
        subscription_period_end: string | null;
      }>("/billing/cancel", { method: "POST" }),
  },

  referrals: {
    status: () => request<import("../types").ReferralStatus>("/referrals/status"),

    apply: (code: string) =>
      request<import("../types").ReferralStatus>("/referrals/apply", {
        method: "POST",
        body: JSON.stringify({ code }),
      }),
  },

  privacy: {
    export: () => request<import("../types").PrivacyExport>("/privacy/export"),

    deleteMyData: () =>
      request<import("../types").PrivacyDeleteResult>("/privacy/delete-my-data", {
        method: "DELETE",
      }),
  },

  email: {
    preferences: () => request<import("../types").EmailPreferences>("/email/preferences"),

    status: () => request<import("../types").EmailStatus>("/email/status"),

    unsubscribe: () =>
      request<import("../types").EmailPreferences>("/email/unsubscribe", { method: "POST" }),

    resubscribe: () =>
      request<import("../types").EmailPreferences>("/email/resubscribe", { method: "POST" }),
  },

  search: {
    facets: () => request<import("../types").JobSearchFacets>("/search/facets"),

    jobs: (params: import("../types").JobSearchParams = {}) => {
      const qs = new URLSearchParams();
      if (params.q?.trim()) qs.set("q", params.q.trim());
      if (params.sort) qs.set("sort", params.sort);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.company?.trim()) qs.set("company", params.company.trim());
      if (params.min_salary != null) qs.set("min_salary", String(params.min_salary));
      if (params.posted_within_days != null) {
        qs.set("posted_within_days", String(params.posted_within_days));
      }
      if (params.direct_only) qs.set("direct_only", "true");
      if (params.include_reach === false) qs.set("include_reach", "false");
      if (params.include_stretch === false) qs.set("include_stretch", "false");
      for (const value of params.remote_mode ?? []) qs.append("remote_mode", value);
      for (const value of params.seniority ?? []) qs.append("seniority", String(value));
      for (const value of params.industry ?? []) qs.append("industry", value);
      for (const value of params.country ?? []) qs.append("country", value);
      for (const value of params.state ?? []) qs.append("state", value);
      for (const value of params.source ?? []) qs.append("source", value);
      for (const value of params.employment_type ?? []) qs.append("employment_type", value);
      return request<import("../types").JobSearchResponse>(`/search/jobs?${qs.toString()}`);
    },
  },

  events: {
    track: (
      type: import("../types").ClientEventType,
      entityId?: string | null,
      payload?: Record<string, unknown>,
    ) =>
      request<{ accepted: boolean }>("/events/track", {
        method: "POST",
        body: JSON.stringify({
          type,
          entity_id: entityId ?? null,
          payload: payload ?? null,
        }),
      }),
  },

  engagement: {
    summary: () => request<import("../types").EngagementSummary>("/engagement/summary"),
    heartbeat: (activityType = "session") =>
      request<import("../types").EngagementSummary>("/engagement/heartbeat", {
        method: "POST",
        body: JSON.stringify({ activity_type: activityType }),
      }),
  },

  career: {
    titleSuggestions: (params?: { goals?: string }) => {
      const qs = new URLSearchParams();
      if (params?.goals?.trim()) qs.set("goals", params.goals.trim());
      const query = qs.toString();
      return request<import("../types").TitleSuggestionsResponse>(
        query ? `/career/title-suggestions?${query}` : "/career/title-suggestions",
      );
    },

    messages: () => request<import("../types").CareerThreadResponse>("/career/messages"),

    clearMessages: () =>
      request<import("../types").CareerThreadResponse>("/career/messages", {
        method: "DELETE",
      }),

    sendMessage: (content: string) =>
      request<import("../types").CareerThreadResponse>("/career/messages", {
        method: "POST",
        body: JSON.stringify({ content }),
      }),

    sendMessageStream: async function* (
      content: string,
      options?: { signal?: AbortSignal },
    ): AsyncGenerator<
      | { type: "user"; id: string; content: string; assistant_id?: string }
      | {
          type: "status";
          phase: "researching" | "research_done" | "research_failed" | "research_skipped";
          detail: string;
        }
      | { type: "sources"; items: import("../types").CareerMessageSource[] }
      | { type: "token"; text: string }
      | {
          type: "done";
          source: "llm" | "template";
          message: import("../types").CareerMessage;
        }
      | { type: "error"; detail: string },
      void
    > {
      const res = await authorizedFetch(`${API_BASE}/career/messages/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({ content }),
        signal: options?.signal,
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body.detail ?? detail;
        } catch {
          /* ignore */
        }
        throw new ApiError(res.status, String(detail));
      }
      yield* parseSseJson<
        | { type: "user"; id: string; content: string; assistant_id?: string }
        | {
            type: "status";
            phase: "researching" | "research_done" | "research_failed" | "research_skipped";
            detail: string;
          }
        | { type: "sources"; items: import("../types").CareerMessageSource[] }
        | { type: "token"; text: string }
        | {
            type: "done";
            source: "llm" | "template";
            message: import("../types").CareerMessage;
          }
        | { type: "error"; detail: string }
      >(res, options?.signal);
    },

    cancelMessage: (messageId: string) =>
      request<import("../types").CareerMessage>(`/career/messages/${messageId}/cancel`, {
        method: "POST",
      }),
  },
};

export { ApiError } from "./errors";
