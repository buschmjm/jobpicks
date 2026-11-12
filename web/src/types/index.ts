export type RemoteOpenness = "local_only" | "open_to_remote" | "remote_only";

export type WorkMode = "remote" | "hybrid" | "onsite" | "unknown";

export type LeftSwipeReason =
  | "not qualified"
  | "overqualified"
  | "comp too low"
  | "location/remote"
  | "don't want this work"
  | "company";

export type SwipeAction = "right" | "left" | "skip";

export type QueueState = "queued" | "swiped_right" | "swiped_left" | "skipped" | "expired";

export type TodoStatus = "to_apply" | "applied" | "archived";

export interface ApplicationStep {
  id: string;
  label: string;
  done: boolean;
  order: number;
}

export type FactStatus = "confirmed" | "inferred" | "needs_confirmation";

export interface SessionUser {
  id: string;
  email: string;
  onboarding_complete: boolean;
}

export interface MatchCard {
  queue_item_id: string;
  job_id: string;
  match_score: number;
  title: string;
  company: string;
  salary_display: string;
  work_mode: WorkMode;
  location_display: string;
  posted_ago: string;
  source: string;
  source_url: string;
  why_bullets: string[];
  caution_bullets: string[];
  score_breakdown?: Record<string, number> | null;
  description: string;
  commute_display?: string | null;
  is_explore: boolean;
  stretch?: boolean;
  state?: QueueState | null;
  swiped_at?: string | null;
  reason?: LeftSwipeReason | null;
}

export interface JobSearchHit {
  job_id: string;
  title: string;
  company: string;
  match_score: number;
  deck_rank_score: number;
  search_score: number;
  attainability: number;
  text_relevance: number;
  reach: boolean;
  stretch: boolean;
  remote_mode: string;
  location_display?: string | null;
  salary_display?: string | null;
  industry?: string | null;
  date_posted?: string | null;
  source?: string | null;
}

export type JobSearchSort = "relevance" | "match" | "date" | "salary" | "attainability";

export interface JobSearchFacetOption {
  value: string;
  label: string;
  count: number;
}

export interface JobSearchFacets {
  remote_modes: JobSearchFacetOption[];
  industries: JobSearchFacetOption[];
  countries: JobSearchFacetOption[];
  states: JobSearchFacetOption[];
  sources: JobSearchFacetOption[];
  employment_types: JobSearchFacetOption[];
  seniority_levels: JobSearchFacetOption[];
}

export interface JobSearchParams {
  q?: string;
  sort?: JobSearchSort;
  limit?: number;
  remote_mode?: string[];
  seniority?: number[];
  industry?: string[];
  country?: string[];
  state?: string[];
  source?: string[];
  employment_type?: string[];
  min_salary?: number;
  posted_within_days?: number;
  direct_only?: boolean;
  company?: string;
  include_reach?: boolean;
  include_stretch?: boolean;
}

export interface JobSearchResponse {
  query: string;
  results: JobSearchHit[];
  profile_complete: boolean;
  sort: JobSearchSort;
}

export type BillingTier = "free" | "pro";

export interface UsageQuota {
  used: number;
  limit: number | null;
  remaining: number | null;
  unlimited: boolean;
  resets_at?: string | null;
  lifetime?: boolean;
  monthly?: boolean;
}

export interface UsageSummary {
  tier: BillingTier;
  deck_matches: UsageQuota;
  advisor_messages: UsageQuota;
  resume_builder_messages: UsageQuota;
  packets: UsageQuota;
}

export interface EngagementFocusJob {
  id: string;
  title: string;
  company: string;
  match_score: number | null;
}

export interface EngagementMilestone {
  id: string;
  label: string;
}

export interface EngagementSummary {
  streak_days: number;
  longest_streak: number;
  applied_this_week: number;
  applied_total: number;
  in_prep_count: number;
  milestones: EngagementMilestone[];
  focus_job: EngagementFocusJob | null;
  pro_trial_active: boolean;
  pro_trial_ends_at: string | null;
  new_milestones?: string[];
}

export const MILESTONE_LABELS: Record<string, string> = {
  first_prep: "First application prepped",
  first_applied: "First application submitted",
  five_applied: "5 applications sent",
  streak_3: "3-day streak",
  streak_7: "7-day streak",
  streak_14: "14-day streak",
};

export interface BillingStatus {
  tier: BillingTier;
  daily_topup_cap: number | null;
  max_why_bullets: number;
  show_score_breakdown: boolean;
  intraday_alerts: boolean;
  pro_monthly_price_cents: number | null;
  price_variant_cents: number | null;
  subscription_status: string | null;
  subscription_period_end: string | null;
  stripe_configured: boolean;
  lifetime_packets_used: number;
  lifetime_packets_limit: number | null;
  external_checkout_allowed: boolean;
  usage?: UsageSummary | null;
}

export interface EmailPreferences {
  digest_enabled: boolean;
  unsubscribe_url: string;
}

export interface EmailStatus {
  backend: "smtp" | "log";
  configured: boolean;
  ready: boolean;
  from_domain: string | null;
}

export interface PrivacyExport {
  exported_at: string;
  user_id: string;
  email: string;
  data: Record<string, unknown>;
}

export interface PrivacyDeleteResult {
  deleted: boolean;
  counts: Record<string, number>;
  message: string;
}

export interface ReferralStatus {
  referral_code: string;
  share_url: string;
  reward_days: number;
  successful_referrals: number;
  referred_by_applied: boolean;
}

export type ClientEventType =
  | "card_viewed"
  | "login"
  | "page_view"
  | "deck_opened"
  | "settings_opened";

export interface UserPreferences {
  target_titles: string[];
  min_salary: number | null;
  home_location: string | null;
  home_lat: number | null;
  home_lon: number | null;
  max_commute_minutes: number | null;
  remote_openness: RemoteOpenness;
  free_text_goals: string | null;
  geocode_status: "ok" | "missing" | "failed";
}

export interface ClientConfig {
  google_maps_api_key: string | null;
}

export type TitleSuggestionTier = "qualified" | "adjacent";

export interface TitleSuggestion {
  title: string;
  tier: TitleSuggestionTier;
  reason: string;
}

export interface TitleSuggestionsResponse {
  suggestions: TitleSuggestion[];
  source: "llm" | "template";
}

export interface CareerMessageSource {
  title: string;
  url: string;
  publisher: string;
  kind?: string;
}

export interface CareerMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  source: "llm" | "template" | null;
  status?: "pending" | "complete" | "failed" | "cancelled" | null;
  created_at: string;
  sources?: CareerMessageSource[];
}

export interface CareerThreadResponse {
  messages: CareerMessage[];
}

export interface DeckNextResponse {
  card: MatchCard | null;
  queue_remaining: number;
  message?: string | null;
  building?: boolean;
}

export interface DeckStatusResponse {
  queue_remaining: number;
  building: boolean;
  open_jobs: number;
  message?: string | null;
}

export interface SwipeResponse {
  success: boolean;
  action: SwipeAction;
  todo_item_id?: string | null;
  next_available: boolean;
  message?: string | null;
}

export interface ProfileFact {
  key: string;
  value: string;
  status: FactStatus;
}

export interface Skill {
  id: string;
  name: string;
  normalized_name: string;
  use_count: number;
}

export interface JobTitle {
  id: string;
  name: string;
  normalized_name: string;
  use_count: number;
}

export interface Experience {
  id?: string | null;
  title: string;
  company_name: string;
  location: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  /** Structured accomplishment bullets for this role (JSON field: highlights). */
  highlights: string[];
}

export interface ProfileWebLink {
  title: string;
  url: string;
}

export interface ProfileIdentity {
  preferred_name: string;
  email: string;
  phone: string;
  pronouns: string;
  show_pronouns: boolean;
  links: ProfileWebLink[];
}

export interface ResumeSelectableText {
  text: string;
  included: boolean;
}

export interface ResumeDocumentRole {
  experience_id?: string;
  included: boolean;
  title: string;
  subtitle?: string | null;
  company_name: string;
  location?: string;
  start_date?: string;
  end_date?: string;
  is_current?: boolean;
  scope?: string | null;
  meta?: string;
  highlights: ResumeSelectableText[];
}

export interface ResumeDocument {
  schema: string;
  layout?: string;
  target?: {
    job_id?: string | null;
    title?: string;
    company?: string;
    source_url?: string;
  } | null;
  rationale?: string;
  header?: {
    full_name?: string;
    headline?: string;
    tagline?: string;
    contacts?: { label: string; value: string; href?: string }[];
  };
  summary_paragraphs?: string[];
  roles?: ResumeDocumentRole[];
  skill_groups?: { label: string; items: ResumeSelectableText[] }[];
  projects?: { name: string; description: string; included?: boolean }[];
  education?: {
    education_id?: string;
    included: boolean;
    institution: string;
    degree?: string;
    field?: string;
    end_date?: string;
  }[];
}

export interface ResumeDraft {
  id: string;
  job_id?: string | null;
  status: "draft" | "accepted";
  layout: "ats";
  document: ResumeDocument;
  created_at: string;
  updated_at: string;
}

export interface Education {
  id?: string | null;
  institution: string;
  degree: string;
  field: string;
  end_date: string;
}

export interface ParsedProfile {
  facts: ProfileFact[];
  skill_names?: string[];
  skills?: Skill[];
  experiences?: Experience[];
  education?: Education[];
  scraped_identity?: ProfileIdentity | null;
  raw_summary?: string | null;
  parse_failed?: boolean;
}

export interface TodoItem {
  id: string;
  job_id: string;
  status: TodoStatus;
  match_score?: number | null;
  title: string;
  company: string;
  salary_display: string;
  work_mode: WorkMode;
  location_display: string;
  source_url: string;
  created_at: string;
  updated_at: string;
  applied_clicked_at?: string | null;
  applied_selfreport_at?: string | null;
  application_steps?: ApplicationStep[];
  steps_done?: number;
  steps_total?: number;
  packet_status?: "none" | "generating" | "ready" | "opened" | "applied" | "failed";
  packet_id?: string | null;
}

export interface PreparedPacketSummary {
  id: string;
  todo_item_id: string | null;
  job_id: string;
  label: string;
  title: string;
  company: string;
  status: "generating" | "ready" | "failed" | "opened" | "applied";
  fit_verdict: "apply" | "lean_apply" | "lean_skip" | "skip" | null;
  answers_count: number;
  has_cover_letter: boolean;
  todo_status: TodoStatus | null;
  updated_at: string;
}

export interface JobFromUrlResponse {
  job_id: string;
  todo_item_id: string;
  apply_url: string | null;
  ats_type: string | null;
  title: string;
  company: string;
  packet_status: "queued" | "skipped" | "skipped_limit";
  todo_item: TodoItem;
}

export interface ApplicationPacketOpenResult {
  packet_id: string;
  todo_item_id: string;
  job_id?: string | null;
  apply_url: string;
}

export type PacketAnswerStatus = "pending" | "confirmed" | "rejected" | "edited";
export type PacketAnswerSource = "vault" | "profile" | "llm" | "user" | "template";

export type PacketAnswer = {
  key: string;
  question_text: string;
  suggested_answer: string;
  source: PacketAnswerSource;
  status: PacketAnswerStatus;
  final_answer?: string | null;
  save_to_vault?: boolean;
};

export type ApplicationPacket = {
  id: string;
  todo_item_id: string | null;
  job_id: string;
  status: "generating" | "ready" | "failed" | "opened" | "applied";
  apply_url: string;
  ats_type?: string | null;
  label?: string | null;
  title?: string;
  company?: string;
  fit_verdict?: "apply" | "lean_apply" | "lean_skip" | "skip" | null;
  fit_rationale?: string[];
  identity: Record<string, unknown>;
  resume_draft_id?: string | null;
  cover_letter?: string | null;
  answers: PacketAnswer[];
  generation_error?: string | null;
  created_at: string;
  updated_at: string;
};

export type SavedApplicationAnswer = {
  id: string;
  question_key: string;
  question_text: string;
  answer: string;
  last_used_at: string;
  created_at: string;
  updated_at: string;
};

export const AUTO_VAULT_ANSWER_KEYS = [
  "work_authorization",
  "sponsorship",
  "salary_expectation",
] as const;

export interface ResumeVariant {
  id: string;
  slug: string;
  label: string;
  headline?: string | null;
  summary_override?: string | null;
  target_titles: string[];
  emphasis_notes?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ResumeVariantListResponse {
  variants: ResumeVariant[];
}

export interface ResumeBuilderMessage {
  id: string;
  variant_id?: string | null;
  role: "user" | "assistant";
  content: string;
  proposal_id?: string | null;
  source?: "llm" | "template" | null;
  status?: "pending" | "complete" | "failed" | null;
  created_at: string;
}

export interface ResumeBuilderThreadResponse {
  messages: ResumeBuilderMessage[];
}

export type ResumeProposalStatus = "pending" | "applied" | "rejected";

export type ResumeProposalOperation =
  | { type: "set_identity"; identity: ProfileIdentity }
  | { type: "set_summary"; summary: string }
  | { type: "set_headline"; headline: string }
  | { type: "add_experience"; experience: Experience }
  | { type: "update_experience"; experience_id: string; experience: Experience }
  | { type: "append_highlights"; experience_id: string; highlights: string[] }
  | { type: "replace_highlights"; experience_id: string; highlights: string[] }
  | { type: "remove_experience"; experience_id: string }
  | { type: "add_education"; education: Education }
  | { type: "update_education"; education_id: string; education: Education }
  | { type: "add_contact_link"; link: ProfileWebLink }
  | { type: "set_skills"; skill_names: string[] };

export interface ResumeProposal {
  id: string;
  variant_id?: string | null;
  message_id?: string | null;
  status: ResumeProposalStatus;
  proposal_type: string;
  preview_summary: string;
  operations: ResumeProposalOperation[];
  applied_at?: string | null;
  created_at: string;
}

export interface ResumeProposalsResponse {
  proposals: ResumeProposal[];
}

export const LEFT_SWIPE_REASONS: { value: LeftSwipeReason; label: string }[] = [
  { value: "not qualified", label: "Not qualified" },
  { value: "overqualified", label: "Overqualified" },
  { value: "comp too low", label: "Comp too low" },
  { value: "location/remote", label: "Location/remote" },
  { value: "don't want this work", label: "Don't want this work" },
  { value: "company", label: "Company" },
];
