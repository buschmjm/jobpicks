"""Pydantic request/response models for auth, onboarding, deck, and todo."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# --- Auth ---


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkResponse(BaseModel):
    message: str = "If that email is registered, a sign-in link has been sent."
    # Dev-only: returned when APP_ENV=development for local testing without SMTP
    dev_token: str | None = None


class SessionUser(BaseModel):
    id: UUID
    email: EmailStr
    onboarding_complete: bool = False


class AuthConfigResponse(BaseModel):
    mode: Literal["keycloak", "legacy"]
    authority: str | None = None
    client_id: str | None = None
    token_endpoint: str | None = None


class ClientConfigResponse(BaseModel):
    google_maps_api_key: str | None = None


class AuthVerifyResponse(BaseModel):
    user: SessionUser
    redirect_to: str = "/onboarding"


# --- Onboarding ---


class FactStatus(StrEnum):
    confirmed = "confirmed"
    inferred = "inferred"
    needs_confirmation = "needs_confirmation"


class ProfileFact(BaseModel):
    key: str
    value: str
    status: FactStatus


class SkillOut(BaseModel):
    id: UUID
    name: str
    normalized_name: str
    use_count: int = 0


class SkillCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class SkillSearchResponse(BaseModel):
    items: list[SkillOut] = Field(default_factory=list)
    query: str = ""


class TitleOut(BaseModel):
    id: UUID
    name: str
    normalized_name: str
    use_count: int = 0


class TitleCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class TitleResolveRequest(BaseModel):
    names: list[str] = Field(default_factory=list, max_length=20)


class TitleSearchResponse(BaseModel):
    items: list[TitleOut] = Field(default_factory=list)
    query: str = ""


class ExperienceIn(BaseModel):
    title: str = Field(default="", max_length=512)
    company_name: str = Field(default="", max_length=512)
    location: str = Field(default="", max_length=512)
    start_date: str = Field(default="", max_length=32)
    end_date: str = Field(default="", max_length=32)
    is_current: bool = False
    # Structured accomplishment bullets for the role (JSON-serializable list[str]).
    highlights: list[str] = Field(default_factory=list, max_length=12)


class ExperienceOut(ExperienceIn):
    id: UUID | None = None


class EducationIn(BaseModel):
    institution: str = Field(default="", max_length=512)
    degree: str = Field(default="", max_length=128)
    field: str = Field(default="", max_length=256)
    end_date: str = Field(default="", max_length=32)


class EducationOut(EducationIn):
    id: UUID | None = None


class ProfileWebLink(BaseModel):
    title: str = Field(default="", max_length=128)
    url: str = Field(default="", max_length=2048)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        from core.profile_identity import normalize_web_url

        raw = (value or "").strip()
        if not raw:
            return ""
        return normalize_web_url(raw)


class ProfileIdentity(BaseModel):
    preferred_name: str = Field(default="", max_length=256)
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=64)
    pronouns: str = Field(default="", max_length=64)
    show_pronouns: bool = True
    links: list[ProfileWebLink] = Field(default_factory=list, max_length=12)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        from core.profile_identity import normalize_us_phone

        return normalize_us_phone(value or "")

    @field_validator("pronouns")
    @classmethod
    def _validate_pronouns(cls, value: str) -> str:
        from core.profile_identity import normalize_pronouns

        return normalize_pronouns(value or "")

    @model_validator(mode="after")
    def _links_need_urls(self) -> ProfileIdentity:
        for link in self.links:
            if (link.title or "").strip() and not (link.url or "").strip():
                raise ValueError("Each web link needs a URL")
        return self


class ParsedProfile(BaseModel):
    facts: list[ProfileFact] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    skills: list[SkillOut] = Field(default_factory=list)
    experiences: list[ExperienceOut] = Field(default_factory=list)
    education: list[EducationOut] = Field(default_factory=list)
    scraped_identity: ProfileIdentity | None = None
    raw_summary: str | None = None
    parse_failed: bool = False


class ResumeUploadResponse(BaseModel):
    upload_id: UUID
    filename: str
    size_bytes: int
    parsed_profile: ParsedProfile
    message: str = "Resume received. Confirm extracted profile to continue."


class ProfileConfirmRequest(BaseModel):
    facts: list[ProfileFact]
    skill_ids: list[UUID] = Field(default_factory=list)
    experiences: list[ExperienceIn] = Field(default_factory=list)
    education: list[EducationIn] = Field(default_factory=list)
    identity: ProfileIdentity | None = None


class ProfileConfirmResponse(BaseModel):
    profile_id: UUID
    facts: list[ProfileFact]
    skills: list[SkillOut] = Field(default_factory=list)
    experiences: list[ExperienceOut] = Field(default_factory=list)
    education: list[EducationOut] = Field(default_factory=list)
    identity: ProfileIdentity = Field(default_factory=ProfileIdentity)
    message: str = "Profile confirmed."


class ProfileResumeResponse(BaseModel):
    """Structured resume fields for post-onboarding editing."""

    profile_id: UUID
    identity: ProfileIdentity = Field(default_factory=ProfileIdentity)
    experiences: list[ExperienceOut] = Field(default_factory=list)
    education: list[EducationOut] = Field(default_factory=list)


class ProfileResumeUpdateRequest(BaseModel):
    identity: ProfileIdentity | None = None
    experiences: list[ExperienceIn] = Field(default_factory=list, max_length=12)
    education: list[EducationIn] = Field(default_factory=list, max_length=8)


class ProfileResumeUpdateResponse(ProfileResumeResponse):
    message: str = "Resume updated."


class ProfileResumeUploadResponse(ProfileResumeResponse):
    filename: str = ""
    message: str = "Resume imported. Review and save if needed."


class ResumeTailorRequest(BaseModel):
    job_id: UUID | None = None
    title: str = Field(default="", max_length=512)
    company: str = Field(default="", max_length=512)
    description: str = Field(default="", max_length=8000)
    source_url: str = Field(default="", max_length=2048)
    why_bullets: list[str] = Field(default_factory=list, max_length=8)
    caution_bullets: list[str] = Field(default_factory=list, max_length=8)


class ResumeDraftResponse(BaseModel):
    id: UUID
    job_id: UUID | None = None
    status: Literal["draft", "accepted"] = "draft"
    layout: Literal["ats"] = "ats"
    document: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ResumeDraftUpdateRequest(BaseModel):
    document: dict[str, Any]
    status: Literal["draft", "accepted"] | None = None


class ResumeTailorResponse(BaseModel):
    draft: ResumeDraftResponse
    source: Literal["llm", "template"] = "template"
    message: str = "Tailored resume draft ready for review."


class QuestionnaireRequest(BaseModel):
    target_titles: list[str] = Field(default_factory=list, max_length=20)
    min_salary: int | None = Field(default=None, ge=0)
    home_location: str | None = Field(default=None, max_length=512)
    home_lat: float | None = Field(default=None, ge=-90, le=90)
    home_lon: float | None = Field(default=None, ge=-180, le=180)
    max_commute_minutes: int | None = Field(default=45, ge=15, le=120)
    remote_openness: Literal["local_only", "open_to_remote", "remote_only"] | None = None
    locations: list[str] = Field(default_factory=list)
    location_radius_miles: int | None = Field(default=None, ge=0, le=500)
    remote_preference: Literal["remote", "hybrid", "onsite", "any"] = "any"
    industries_to_avoid: list[str] = Field(default_factory=list)
    free_text_goals: str | None = Field(default=None, max_length=2000)
    referral_code: str | None = Field(default=None, max_length=16)
    timezone: str | None = Field(default=None, max_length=64)


class PreferencesResponse(BaseModel):
    target_titles: list[str] = Field(default_factory=list)
    min_salary: int | None = None
    home_location: str | None = None
    home_lat: float | None = None
    home_lon: float | None = None
    max_commute_minutes: int | None = None
    remote_openness: Literal["local_only", "open_to_remote", "remote_only"] = "open_to_remote"
    free_text_goals: str | None = None
    geocode_status: Literal["ok", "missing", "failed"] = "missing"


class PreferencesUpdateRequest(BaseModel):
    home_location: str | None = Field(default=None, max_length=512)
    home_lat: float | None = Field(default=None, ge=-90, le=90)
    home_lon: float | None = Field(default=None, ge=-180, le=180)
    max_commute_minutes: int | None = Field(default=None, ge=15, le=120)
    remote_openness: Literal["local_only", "open_to_remote", "remote_only"] = "open_to_remote"
    target_titles: list[str] | None = Field(default=None, max_length=20)
    min_salary: int | None = Field(default=None, ge=0)
    free_text_goals: str | None = Field(default=None, max_length=2000)


class PreferencesUpdateResponse(BaseModel):
    preferences: PreferencesResponse
    message: str = "Preferences saved. Rebuilding your deck."


class QuestionnaireResponse(BaseModel):
    user_id: UUID
    onboarding_complete: bool = True
    message: str = "Onboarding complete. Your queue is being built."


# --- Deck ---


class WorkMode(StrEnum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class LeftSwipeReason(StrEnum):
    not_qualified = "not qualified"
    overqualified = "overqualified"
    comp_too_low = "comp too low"
    location_remote = "location/remote"
    dont_want_work = "don't want this work"
    company = "company"


class MatchCard(BaseModel):
    queue_item_id: UUID
    job_id: UUID
    match_score: int = Field(ge=0, le=100)
    title: str
    company: str
    salary_display: str  # e.g. "$140–170k" or "salary not listed"
    work_mode: WorkMode
    location_display: str
    posted_ago: str
    source: str
    source_url: str
    why_bullets: list[str] = Field(default_factory=list, min_length=0, max_length=4)
    caution_bullets: list[str] = Field(default_factory=list, max_length=2)
    score_breakdown: dict[str, float] | None = None
    description: str
    commute_display: str | None = None
    is_explore: bool = False
    stretch: bool = False
    state: Literal["queued", "swiped_right", "swiped_left", "skipped", "expired"] | None = None
    swiped_at: datetime | None = None
    reason: LeftSwipeReason | None = None


class DeckNextResponse(BaseModel):
    card: MatchCard | None = None
    queue_remaining: int = 0
    message: str | None = None
    building: bool = False


class DeckStatusResponse(BaseModel):
    queue_remaining: int = 0
    building: bool = False
    open_jobs: int = 0
    message: str | None = None


class SwipeAction(StrEnum):
    right = "right"
    left = "left"
    skip = "skip"


class SwipeRequest(BaseModel):
    queue_item_id: UUID
    action: SwipeAction
    reason: LeftSwipeReason | None = None
    dwell_ms: int | None = Field(default=None, ge=0)


class SwipeResponse(BaseModel):
    success: bool = True
    action: SwipeAction
    todo_item_id: UUID | None = None  # set on swipe_right
    next_available: bool = True
    message: str | None = None


class ChangeDecisionRequest(BaseModel):
    queue_item_id: UUID
    action: SwipeAction
    reason: LeftSwipeReason | None = None


class ChangeDecisionResponse(BaseModel):
    success: bool = True
    action: SwipeAction
    todo_item_id: UUID | None = None
    message: str | None = None


class DwellRequest(BaseModel):
    queue_item_id: UUID
    dwell_ms: int = Field(ge=0)


class DwellResponse(BaseModel):
    recorded: bool = True


# --- Todo ---


class TodoStatus(StrEnum):
    to_apply = "to_apply"
    applied = "applied"
    archived = "archived"


class ApplicationStep(BaseModel):
    id: str
    label: str = Field(min_length=1, max_length=200)
    done: bool = False
    order: int = Field(ge=0)


class TodoItem(BaseModel):
    id: UUID
    job_id: UUID
    status: TodoStatus
    match_score: int | None = None
    title: str
    company: str
    salary_display: str
    work_mode: WorkMode
    location_display: str
    source_url: str
    created_at: datetime
    updated_at: datetime
    applied_clicked_at: datetime | None = None
    applied_selfreport_at: datetime | None = None
    application_steps: list[ApplicationStep] = Field(default_factory=list)
    steps_done: int = 0
    steps_total: int = 0
    packet_status: Literal["none", "generating", "ready", "opened", "applied", "failed"] = "none"
    packet_id: UUID | None = None


class ApplicationStepTemplateResponse(BaseModel):
    steps: list[ApplicationStep]


class ApplicationStepTemplateUpdateRequest(BaseModel):
    steps: list[ApplicationStep] = Field(min_length=1)


class TodoStepsUpdateRequest(BaseModel):
    steps: list[ApplicationStep] = Field(min_length=1)


class TodoListResponse(BaseModel):
    items: list[TodoItem]
    total: int


class TodoCreateRequest(BaseModel):
    job_id: UUID


class TodoUpdateRequest(BaseModel):
    status: TodoStatus | None = None
    application_steps: list[ApplicationStep] | None = None


class TodoApplyClickResponse(BaseModel):
    source_url: str
    todo_item_id: UUID


class TodoSelfReportRequest(BaseModel):
    did_apply: bool


class JobFromUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    generate_packet: bool = True


class JobDescriptionResponse(BaseModel):
    description: str = ""
    truncated: bool = False
    competitiveness_top_percent: int | None = None
    competitiveness_p_top_percent: int | None = None


class JobSearchHit(BaseModel):
    job_id: UUID
    title: str
    company: str
    match_score: float
    deck_rank_score: float
    search_score: float
    attainability: float
    text_relevance: float
    reach: bool = False
    stretch: bool = False
    remote_mode: str = "unknown"
    location_display: str | None = None
    salary_display: str | None = None
    industry: str | None = None
    date_posted: date | None = None
    source: str | None = None


class JobSearchFacetOption(BaseModel):
    value: str
    label: str
    count: int


class JobSearchFacetsResponse(BaseModel):
    remote_modes: list[JobSearchFacetOption] = Field(default_factory=list)
    industries: list[JobSearchFacetOption] = Field(default_factory=list)
    countries: list[JobSearchFacetOption] = Field(default_factory=list)
    states: list[JobSearchFacetOption] = Field(default_factory=list)
    sources: list[JobSearchFacetOption] = Field(default_factory=list)
    employment_types: list[JobSearchFacetOption] = Field(default_factory=list)
    seniority_levels: list[JobSearchFacetOption] = Field(default_factory=list)


class JobSearchResponse(BaseModel):
    query: str
    results: list[JobSearchHit] = Field(default_factory=list)
    profile_complete: bool = False
    sort: str = "relevance"


class JobFromUrlResponse(BaseModel):
    job_id: UUID
    todo_item_id: UUID
    apply_url: str | None = None
    ats_type: str | None = None
    title: str
    company: str
    packet_status: Literal["queued", "skipped", "skipped_limit"] = "queued"
    todo_item: TodoItem


# --- Career assistant ---


class TitleSuggestion(BaseModel):
    title: str
    tier: Literal["qualified", "adjacent"]
    reason: str


class TitleSuggestionsResponse(BaseModel):
    suggestions: list[TitleSuggestion]
    source: Literal["llm", "template"]


class CareerMessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


class CareerMessageStatus(StrEnum):
    pending = "pending"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


class CareerMessageSource(BaseModel):
    title: str = ""
    url: str = ""
    publisher: str = ""
    kind: str | None = None


class CareerMessage(BaseModel):
    id: UUID
    role: CareerMessageRole
    content: str
    source: Literal["llm", "template"] | None = None
    status: CareerMessageStatus | None = None
    sources: list[CareerMessageSource] | None = None
    created_at: datetime


class CareerMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)


class CareerThreadResponse(BaseModel):
    messages: list[CareerMessage] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


# --- Application packet ---


class PacketAnswerStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    edited = "edited"


class PacketAnswerSource(StrEnum):
    vault = "vault"
    profile = "profile"
    llm = "llm"
    user = "user"
    template = "template"


class PacketAnswerItem(BaseModel):
    key: str
    question_text: str
    suggested_answer: str
    source: PacketAnswerSource = PacketAnswerSource.llm
    status: PacketAnswerStatus = PacketAnswerStatus.pending
    final_answer: str | None = None
    save_to_vault: bool = False


class ApplicationPacketStatus(StrEnum):
    generating = "generating"
    ready = "ready"
    failed = "failed"
    opened = "opened"
    applied = "applied"


class ApplicationPacketResponse(BaseModel):
    id: UUID
    todo_item_id: UUID | None = None
    job_id: UUID
    status: ApplicationPacketStatus
    apply_url: str
    ats_type: str | None = None
    label: str | None = None
    title: str = "Job"
    company: str = "Unknown"
    fit_verdict: Literal["apply", "lean_apply", "lean_skip", "skip"] | None = None
    fit_rationale: list[str] = Field(default_factory=list)
    identity: dict[str, Any] = Field(default_factory=dict)
    resume_draft_id: UUID | None = None
    cover_letter: str | None = None
    answers: list[PacketAnswerItem] = Field(default_factory=list)
    generation_error: str | None = None
    created_at: datetime
    updated_at: datetime


class PacketAnswerPatchItem(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    status: PacketAnswerStatus
    final_answer: str | None = Field(default=None, max_length=4000)
    save_to_vault: bool = False


class ApplicationPacketPatchRequest(BaseModel):
    cover_letter: str | None = Field(default=None, max_length=8000)
    answers: list[PacketAnswerPatchItem] = Field(default_factory=list)
    fit_verdict: Literal["apply", "lean_apply", "lean_skip", "skip"] | None = None
    label: str | None = Field(default=None, min_length=1, max_length=256)


class ApplicationPacketReuseRequest(BaseModel):
    source_packet_id: UUID


class ApplicationPacketOpenResponse(BaseModel):
    packet_id: UUID
    todo_item_id: UUID
    job_id: UUID | None = None
    apply_url: str


class PreparedPacketSummary(BaseModel):
    id: UUID
    todo_item_id: UUID | None = None
    job_id: UUID
    label: str
    title: str
    company: str
    status: ApplicationPacketStatus
    fit_verdict: Literal["apply", "lean_apply", "lean_skip", "skip"] | None = None
    answers_count: int = 0
    has_cover_letter: bool = False
    todo_status: TodoStatus | None = None
    updated_at: datetime


class PreparedPacketListResponse(BaseModel):
    items: list[PreparedPacketSummary] = Field(default_factory=list)
    total: int = 0


class ApplicationPacketAssistRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)


# --- Saved application answers ---


class SavedApplicationAnswerResponse(BaseModel):
    id: UUID
    question_key: str
    question_text: str
    answer: str
    last_used_at: datetime
    created_at: datetime
    updated_at: datetime


class SavedApplicationAnswerListResponse(BaseModel):
    items: list[SavedApplicationAnswerResponse] = Field(default_factory=list)


class SavedApplicationAnswerUpsertRequest(BaseModel):
    question_text: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)


# --- Resume builder (conversational) ---


class ResumeVariantCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=256)
    headline: str | None = Field(default=None, max_length=512)
    summary_override: str | None = Field(default=None, max_length=8000)
    target_titles: list[str] = Field(default_factory=list, max_length=20)
    emphasis_notes: str | None = Field(default=None, max_length=4000)
    is_default: bool = False


class ResumeVariantUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=256)
    headline: str | None = Field(default=None, max_length=512)
    summary_override: str | None = Field(default=None, max_length=8000)
    target_titles: list[str] | None = Field(default=None, max_length=20)
    emphasis_notes: str | None = Field(default=None, max_length=4000)
    is_default: bool | None = None


class ResumeVariantResponse(BaseModel):
    id: UUID
    slug: str
    label: str
    headline: str | None = None
    summary_override: str | None = None
    target_titles: list[str] = Field(default_factory=list)
    emphasis_notes: str | None = None
    is_default: bool = False
    created_at: datetime
    updated_at: datetime


class ResumeVariantListResponse(BaseModel):
    variants: list[ResumeVariantResponse] = Field(default_factory=list)


class ResumeProposalListResponse(BaseModel):
    proposals: list[ResumeProposalResponse] = Field(default_factory=list)


class ResumeProposalStatus(StrEnum):
    pending = "pending"
    applied = "applied"
    rejected = "rejected"


class SetIdentityOperation(BaseModel):
    type: Literal["set_identity"] = "set_identity"
    identity: ProfileIdentity


class SetSummaryOperation(BaseModel):
    type: Literal["set_summary"] = "set_summary"
    summary: str = Field(max_length=8000)


class SetHeadlineOperation(BaseModel):
    type: Literal["set_headline"] = "set_headline"
    headline: str = Field(max_length=512)


class AddExperienceOperation(BaseModel):
    type: Literal["add_experience"] = "add_experience"
    experience: ExperienceIn


class UpdateExperienceOperation(BaseModel):
    type: Literal["update_experience"] = "update_experience"
    experience_id: UUID
    experience: ExperienceIn


class AppendHighlightsOperation(BaseModel):
    type: Literal["append_highlights"] = "append_highlights"
    experience_id: UUID
    highlights: list[str] = Field(min_length=1, max_length=12)


class ReplaceHighlightsOperation(BaseModel):
    type: Literal["replace_highlights"] = "replace_highlights"
    experience_id: UUID
    highlights: list[str] = Field(max_length=12)


class RemoveExperienceOperation(BaseModel):
    type: Literal["remove_experience"] = "remove_experience"
    experience_id: UUID


class AddEducationOperation(BaseModel):
    type: Literal["add_education"] = "add_education"
    education: EducationIn


class UpdateEducationOperation(BaseModel):
    type: Literal["update_education"] = "update_education"
    education_id: UUID
    education: EducationIn


class AddContactLinkOperation(BaseModel):
    type: Literal["add_contact_link"] = "add_contact_link"
    link: ProfileWebLink


class SetSkillsOperation(BaseModel):
    type: Literal["set_skills"] = "set_skills"
    skill_names: list[str] = Field(max_length=50)


ResumeProposalOperation = Annotated[
    SetIdentityOperation
    | SetSummaryOperation
    | SetHeadlineOperation
    | AddExperienceOperation
    | UpdateExperienceOperation
    | AppendHighlightsOperation
    | ReplaceHighlightsOperation
    | RemoveExperienceOperation
    | AddEducationOperation
    | UpdateEducationOperation
    | AddContactLinkOperation
    | SetSkillsOperation,
    Field(discriminator="type"),
]


class ResumeProposalResponse(BaseModel):
    id: UUID
    variant_id: UUID | None = None
    message_id: UUID | None = None
    status: ResumeProposalStatus
    proposal_type: str
    operations: list[ResumeProposalOperation] = Field(default_factory=list)
    preview_summary: str = ""
    applied_at: datetime | None = None
    created_at: datetime


class ResumeProposalApplyResponse(BaseModel):
    proposal: ResumeProposalResponse
    message: str = "Proposal applied to profile."


class ResumeBuilderMessageRole(StrEnum):
    user = "user"
    assistant = "assistant"


ResumeBuilderMessageStatus = CareerMessageStatus


class ResumeBuilderMessage(BaseModel):
    id: UUID
    variant_id: UUID | None = None
    role: ResumeBuilderMessageRole
    content: str
    proposal_id: UUID | None = None
    source: Literal["llm", "template"] | None = None
    status: CareerMessageStatus | None = None
    created_at: datetime


class ResumeBuilderMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    variant_id: UUID | None = None


class ResumeBuilderThreadResponse(BaseModel):
    messages: list[ResumeBuilderMessage] = Field(default_factory=list)


# --- Billing (Workstream B) ---


class UsageQuotaResponse(BaseModel):
    used: int
    limit: int | None = None
    remaining: int | None = None
    unlimited: bool = False
    resets_at: str | None = None
    lifetime: bool = False
    monthly: bool = False


class UsageSummaryResponse(BaseModel):
    tier: Literal["free", "pro"]
    deck_matches: UsageQuotaResponse
    advisor_messages: UsageQuotaResponse
    resume_builder_messages: UsageQuotaResponse
    packets: UsageQuotaResponse


class BillingStatusResponse(BaseModel):
    tier: Literal["free", "pro"]
    daily_topup_cap: int | None
    max_why_bullets: int
    show_score_breakdown: bool
    intraday_alerts: bool
    pro_monthly_price_cents: int | None = None
    price_variant_cents: int | None = None
    subscription_status: str | None = None
    subscription_period_end: datetime | None = None
    stripe_configured: bool = False
    lifetime_packets_used: int = 0
    lifetime_packets_limit: int | None = None
    external_checkout_allowed: bool = True
    usage: UsageSummaryResponse | None = None


class BillingCheckoutResponse(BaseModel):
    checkout_url: str


class BillingPortalResponse(BaseModel):
    portal_url: str


class BillingCancelResponse(BaseModel):
    canceled: bool
    cancel_at_period_end: bool = True
    subscription_period_end: datetime | None = None


# --- Revenue prerequisites (Workstream C) ---


class EmailPreferencesResponse(BaseModel):
    digest_enabled: bool
    unsubscribe_url: str


class EmailStatusResponse(BaseModel):
    backend: Literal["smtp", "log"]
    configured: bool
    ready: bool
    from_domain: str | None = None


class MobileReadinessResponse(BaseModel):
    apple_universal_links_configured: bool
    android_app_links_configured: bool
    apple_bundle_id: str | None = None
    android_package: str | None = None
    auth_callback_paths: list[str] = Field(default_factory=list)
    external_checkout_storefronts: list[str] = Field(default_factory=list)


class ReferralStatusResponse(BaseModel):
    referral_code: str
    share_url: str
    reward_days: int
    successful_referrals: int
    referred_by_applied: bool


class ReferralApplyRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)


class TrackEventResponse(BaseModel):
    accepted: bool = True


# --- Privacy ---


class DeleteMyDataResponse(BaseModel):
    deleted: bool
    counts: dict[str, int]
    message: str = "Your personal data has been deleted or anonymized."


class ExportMyDataResponse(BaseModel):
    exported_at: str
    user_id: str
    email: str
    data: dict[str, object]
