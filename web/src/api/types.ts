export interface Settings {
  translated_dir: string
  target_language: string
  llm_provider: string
  fallback_provider: string
  max_chapters: number
  chunk_size: number
  chunk_overlap: number
  review_threshold: number
  max_retries: number
  enable_review: boolean
  enable_summary: boolean
  translation_temperature: number
  translation_max_tokens: number
  gemini_api_key_configured: boolean
  openrouter_api_key_configured: boolean
  telegram_enabled: boolean
  telegram_configured: boolean
  telegram_api_base: string
  telegram_parse_mode: '' | 'HTML'
  telegram_silent: boolean
  telegram_timeout_seconds: number
  ollama_base_url: string
  ollama_model: string
  gemini_model: string
  openrouter_model: string
}

export interface TelegramSettings {
  telegram_enabled: boolean
  telegram_api_base: string
  telegram_parse_mode: '' | 'HTML'
  telegram_silent: boolean
  telegram_timeout_seconds: number
}

export interface ProviderSettings {
  llm_provider: 'ollama' | 'gemini' | 'openrouter'
  fallback_provider: '' | 'ollama' | 'gemini' | 'openrouter'
  ollama_base_url: string
  ollama_model: string
  gemini_model: string
  openrouter_model: string
  gemini_api_key?: string
  openrouter_api_key?: string
}

export interface ProviderCheckSettings {
  ollama_base_url?: string
  gemini_api_key?: string
  openrouter_api_key?: string
}

export interface NovelSummary {
  name: string
  title: string | null
  author: string | null
  source_language: string | null
  total_input_chapters: number
  targets: NovelTargetProgress[]
  has_illustrations: boolean
}

export interface NovelTargetProgress {
  target: string
  completed: number
  failed: number
  total: number
}

export interface NovelDetail extends NovelSummary {
  glossary_terms: number
  glossary_entities: number
  glossary_edges: number
  artifacts: string[]
}

export interface NovelChapterStatus {
  number: number
  has_source: boolean
  has_translation: boolean
  target: string | null
}

export interface ChapterContentResponse {
  novel: string
  chapter: number
  view: 'source' | 'translation'
  target: string | null
  content: string
}

export interface JobError {
  code: string
  message: string
  details?: Record<string, unknown> | null
}

export interface JobModel {
  id: string
  kind: string
  novel: string | null
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelling' | 'cancelled'
  created_at: string
  started_at: string | null
  finished_at: string | null
  progress: Record<string, unknown>
  result: Record<string, unknown> | null
  error: JobError | null
  logs: string[]
}

export interface JobListResponse {
  current: JobModel | null
  history: JobModel[]
}

export interface ConfigSummary {
  name: string
  version: number
  start_url: string
  updated_at: string | null
}

export interface DraftSummary {
  draft_id: string
  name: string
  created_at: string
  expires_at: string
  source_url: string | null
}

export interface DraftDetail extends DraftSummary {
  config: Record<string, unknown>
}

export interface ArtifactInfo {
  name: string
  format: string
  size: number
}

export interface GlossaryResponse {
  novel: string
  data: Record<string, unknown>
}

export interface NovelMetadataResponse {
  novel: string
  data: Record<string, unknown>
}

export interface HealthResponse {
  status: 'ok'
  active_job_id: string | null
}

export interface ProviderInfo {
  name: string
  configured: boolean
  default_model: string | null
}

export interface ProvidersResponse {
  providers: ProviderInfo[]
  default_provider: string
}

export interface ApiError {
  error: {
    code: string
    message: string
    details?: Record<string, unknown> | null
  }
}
