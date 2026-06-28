"""Pydantic request and response schemas for the FastAPI surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# System and settings
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: Literal["ok"]
    active_job_id: str | None = None


class SettingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translated_dir: str
    target_language: str
    llm_provider: str
    fallback_provider: str
    use_browser: bool
    max_chapters: int
    chunk_size: int
    chunk_overlap: int
    review_threshold: float
    max_retries: int
    enable_review: bool
    enable_summary: bool
    translation_temperature: float
    translation_max_tokens: int
    gemini_api_key_configured: bool
    openrouter_api_key_configured: bool
    telegram_configured: bool
    ollama_base_url: str
    ollama_model: str
    gemini_model: str
    openrouter_model: str


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translated_dir: str | None = None
    target_language: Literal["vi", "en"] | None = None
    llm_provider: Literal["ollama", "gemini", "openrouter"] | None = None
    fallback_provider: Literal["", "ollama", "gemini", "openrouter"] | None = None
    use_browser: bool | None = None
    max_chapters: int | None = Field(None, ge=0)
    chunk_size: int | None = Field(None, ge=1)
    chunk_overlap: int | None = Field(None, ge=0)
    review_threshold: float | None = Field(None, ge=0, le=1)
    max_retries: int | None = Field(None, ge=0)
    enable_review: bool | None = None
    enable_summary: bool | None = None
    translation_temperature: float | None = Field(None, ge=0, le=1)
    translation_max_tokens: int | None = Field(None, ge=1)
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    gemini_model: str | None = None
    openrouter_model: str | None = None


class ProviderInfo(BaseModel):
    name: str
    configured: bool
    default_model: str | None = None


class ProvidersResponse(BaseModel):
    providers: list[ProviderInfo]
    default_provider: str


class ProviderCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str


class ProviderCheckResponse(BaseModel):
    provider: str
    ok: bool
    detail: str | None = None


# ---------------------------------------------------------------------------
# Novels
# ---------------------------------------------------------------------------


class NovelChapterStatus(BaseModel):
    number: int
    has_source: bool
    has_translation: bool
    target: str | None = None


class NovelTargetProgress(BaseModel):
    target: str
    completed: int
    failed: int
    total: int


class NovelSummary(BaseModel):
    name: str
    title: str | None = None
    author: str | None = None
    source_language: str | None = None
    total_input_chapters: int
    targets: list[NovelTargetProgress]
    has_illustrations: bool


class NovelDetail(NovelSummary):
    glossary_terms: int
    glossary_entities: int
    glossary_edges: int
    artifacts: list[str]


class ChapterContentResponse(BaseModel):
    novel: str
    chapter: int
    view: str
    target: str | None
    content: str


class NovelMetadataResponse(BaseModel):
    novel: str
    data: dict[str, Any]


class NovelMetadataPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    author: str | None = None
    source_url: str | None = None
    illustration_url: str | None = None
    site_name: str | None = None
    translated: dict[str, str | None] | None = None


# ---------------------------------------------------------------------------
# Pipeline operations
# ---------------------------------------------------------------------------


class TranslationRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    novel: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    source_language: str | None = None
    target_language: Literal["", "vi", "en"] | None = None
    provider: Literal["", "ollama", "gemini", "openrouter"] | None = None
    enable_review: bool | None = None
    enable_summary: bool | None = None
    start_chapter: int | None = Field(None, ge=0)
    end_chapter: int | None = Field(None, ge=0)
    force: bool | None = None
    resume: bool | None = None
    failed_only: bool | None = None
    limit: int | None = Field(None, ge=0)


class PackRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    novel: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    target_language: Literal["vi", "en"] | None = None
    formats: list[Literal["epub", "pdf"]] = Field(default_factory=lambda: ["epub", "pdf"], min_length=1)
    title: str | None = None
    author: str | None = None
    dark_mode: bool | None = None


class CrawlRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str
    translated_output: str | None = None
    max_chapters: int | None = Field(None, ge=0)
    fail_fast: bool | None = None
    ignore_robots: bool | None = None
    overwrite: bool | None = None
    browser: bool | None = None
    headed: bool | None = None
    workers: int | None = Field(None, ge=1, le=32)


class ImportRequestResponse(BaseModel):
    job_id: str


class ArtifactInfoResponse(BaseModel):
    name: str
    format: str
    size: int


# ---------------------------------------------------------------------------
# Configs and drafts
# ---------------------------------------------------------------------------


class ConfigSummary(BaseModel):
    name: str
    version: int
    start_url: str
    updated_at: str | None = None


class ConfigGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    name: str | None = None
    provider: Literal["ollama", "gemini", "openrouter"] | None = None
    browser: bool | None = None
    no_cache: bool | None = None
    ignore_sample: bool | None = None


class ConfigValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str | None = None
    browser: bool | None = None


class ConfigSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]
    draft_id: str | None = None


class DraftSummary(BaseModel):
    draft_id: str
    name: str
    created_at: datetime
    expires_at: datetime
    source_url: str | None = None


class DraftDetail(DraftSummary):
    config: dict[str, Any]


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


JobStatus = Literal["queued", "running", "completed", "failed", "cancelling", "cancelled"]


class JobErrorModel(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class JobModel(BaseModel):
    id: str
    kind: str
    novel: str | None
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    progress: dict[str, Any]
    result: dict[str, Any] | None
    error: JobErrorModel | None
    logs: list[str]


class JobListResponse(BaseModel):
    current: JobModel | None
    history: list[JobModel]


class JobStartResponse(BaseModel):
    job_id: str


# ---------------------------------------------------------------------------
# Glossary
# ---------------------------------------------------------------------------


class GlossaryResponse(BaseModel):
    novel: str
    data: dict[str, Any]


class GlossaryTermsPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terms: dict[str, str]


class GlossaryTermAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    translated: str


class GlossaryCharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    translated_name: str | None = None
    role: str | None = None


class GlossaryRelationshipAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_char: str
    to_char: str
    relationship: str
    since: int | None = Field(None, ge=0)


class GlossaryCharacterSummary(BaseModel):
    original: str
    translated_name: str | None = None
    role: str | None = None
    pronoun: str | None = None


class GlossaryCharactersResponse(BaseModel):
    novel: str
    characters: list[GlossaryCharacterSummary]


# ---------------------------------------------------------------------------
# Generic error shape
# ---------------------------------------------------------------------------


class ApiErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ApiErrorResponse(BaseModel):
    error: ApiErrorDetail
