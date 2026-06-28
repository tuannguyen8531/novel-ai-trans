import type {
  ArtifactInfo,
  ChapterContentResponse,
  ConfigSummary,
  DraftDetail,
  DraftSummary,
  GlossaryResponse,
  HealthResponse,
  JobListResponse,
  JobModel,
  NovelChapterStatus,
  NovelDetail,
  NovelMetadataResponse,
  NovelSummary,
  ProvidersResponse,
  Settings
} from './types'

const BASE = ''

let authToken: string | null = null

export function setAuthToken(token: string | null): void {
  authToken = token
}

export function getAuthToken(): string | null {
  return authToken
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const out: Record<string, string> = { Accept: 'application/json', ...extra }
  if (authToken) {
    out.Authorization = `Bearer ${authToken}`
  }
  return out
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: headers(init.headers as Record<string, string> | undefined)
  })
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`
    let code = 'http_error'
    let details: Record<string, unknown> | null = null
    try {
      const body = (await response.json()) as { error?: { code: string; message: string; details?: Record<string, unknown> | null } }
      if (body.error) {
        code = body.error.code
        message = body.error.message
        details = body.error.details ?? null
      }
    } catch (_) {
      // ignore parse errors
    }
    let displayMessage = message
    if (code === 'validation_error' && details && Array.isArray(details.errors)) {
      const fields = (details.errors as Array<{ loc?: unknown[]; msg?: string }>)
        .map((entry) => {
          const path = Array.isArray(entry.loc) ? entry.loc.filter((p) => p !== 'body').join('.') : ''
          return path ? `${path}: ${entry.msg ?? 'invalid'}` : (entry.msg ?? 'invalid')
        })
      if (fields.length) {
        displayMessage = `Request validation failed. ${fields.join('; ')}`
      }
    }
    const err = new Error(displayMessage) as Error & { code: string; status: number; details: Record<string, unknown> | null }
    err.code = code
    err.status = response.status
    err.details = details
    throw err
  }
  if (response.status === 204) {
    return undefined as unknown as T
  }
  return (await response.json()) as T
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  getSettings: () => request<Settings>('/api/settings'),
  patchSettings: (patch: Partial<Settings>) =>
    request<Settings>('/api/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch)
    }),
  persistSettings: () =>
    request<{ path: string; changed_keys: string[] }>(
      '/api/settings/persist',
      { method: 'POST' }
    ),
  listProviders: () => request<ProvidersResponse>('/api/providers'),
  listProviderModels: (provider: string) =>
    request<{ provider: string; models: string[] }>(
      `/api/providers/${encodeURIComponent(provider)}/models`
    ),
  checkProvider: (provider: string) =>
    request<{ provider: string; ok: boolean; detail: string | null }>(
      '/api/providers/check',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider })
      }
    ),

  listNovels: () => request<NovelSummary[]>('/api/novels'),
  getNovel: (name: string) => request<NovelDetail>(`/api/novels/${encodeURIComponent(name)}`),
  listChapters: (name: string) =>
    request<NovelChapterStatus[]>(`/api/novels/${encodeURIComponent(name)}/chapters`),
  getChapterContent: (
    name: string,
    chapter: number,
    view: 'source' | 'translation',
    target?: string
  ) => {
    const params = new URLSearchParams({ view })
    if (target) params.set('target', target)
    return request<ChapterContentResponse>(
      `/api/novels/${encodeURIComponent(name)}/chapters/${chapter}?${params.toString()}`
    )
  },
  listArtifacts: (name: string) =>
    request<ArtifactInfo[]>(`/api/novels/${encodeURIComponent(name)}/artifacts`),
  downloadArtifact: async (name: string, filename: string): Promise<Blob> => {
    const response = await fetch(
      `${BASE}/api/novels/${encodeURIComponent(name)}/artifacts/${encodeURIComponent(filename)}`,
      { headers: headers() }
    )
    if (!response.ok) {
      throw new Error(`Artifact download failed: ${response.status} ${response.statusText}`)
    }
    return response.blob()
  },
  deleteNovel: (name: string) =>
    request<void>(`/api/novels/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  getTranslationProgress: (name: string, target?: string) => {
    const params = new URLSearchParams()
    if (target) params.set('target', target)
    return request<{ completed: number[]; failed: number[] }>(
      `/api/novels/${encodeURIComponent(name)}/translation-progress${
        params.toString() ? `?${params.toString()}` : ''
      }`
    )
  },
  getNovelMetadata: (name: string) =>
    request<NovelMetadataResponse>(`/api/novels/${encodeURIComponent(name)}/metadata`),
  patchNovelMetadata: (name: string, patch: Record<string, unknown>) =>
    request<NovelMetadataResponse>(`/api/novels/${encodeURIComponent(name)}/metadata`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch)
    }),

  listConfigs: () => request<ConfigSummary[]>('/api/configs'),
  getConfig: (name: string) => request<Record<string, unknown>>(`/api/configs/${encodeURIComponent(name)}`),
  saveConfig: (name: string, config: Record<string, unknown>, draft_id?: string) =>
    request<{ name: string; saved: boolean }>(`/api/configs/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config, draft_id })
    }),
  generateConfig: (payload: Record<string, unknown>) =>
    request<{ job_id: string }>('/api/configs/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }),
  validateConfig: (name: string, payload: { target?: string; browser?: boolean }) =>
    request<{ job_id: string }>(`/api/configs/${encodeURIComponent(name)}/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }),

  listDrafts: () => request<DraftSummary[]>('/api/config-drafts'),
  getDraft: (draft_id: string) => request<DraftDetail>(`/api/config-drafts/${draft_id}`),
  deleteDraft: (draft_id: string) =>
    request<void>(`/api/config-drafts/${draft_id}`, { method: 'DELETE' }),

  startTranslate: (payload: Record<string, unknown>) =>
    request<{ job_id: string }>('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }),
  startPack: (payload: Record<string, unknown>) =>
    request<{ job_id: string }>('/api/pack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }),
  startCrawl: (payload: Record<string, unknown>) =>
    request<{ job_id: string }>('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }),
  uploadImport: (file: File, name?: string, keep_existing = false) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    form.append('keep_existing', String(keep_existing))
    return request<{ job_id: string }>('/api/import', { method: 'POST', body: form })
  },

  getGlossary: (name: string) =>
    request<GlossaryResponse>(`/api/novels/${encodeURIComponent(name)}/glossary`),
  putTerms: (name: string, terms: Record<string, string>) =>
    request<GlossaryResponse>(`/api/novels/${encodeURIComponent(name)}/glossary/terms`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ terms })
    }),
  addTerm: (name: string, original: string, translated: string) =>
    request<GlossaryResponse>(`/api/novels/${encodeURIComponent(name)}/glossary/terms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ original, translated })
    }),
  removeTerm: (name: string, original: string) =>
    request<GlossaryResponse>(
      `/api/novels/${encodeURIComponent(name)}/glossary/terms/${encodeURIComponent(original)}`,
      { method: 'DELETE' }
    ),
  listCharacters: (name: string) =>
    request<{ novel: string; characters: Array<{ original: string; translated_name: string | null; role: string | null; pronoun: string | null }> }>(
      `/api/novels/${encodeURIComponent(name)}/glossary/characters`
    ),
  updateCharacter: (
    name: string,
    original: string,
    payload: { translated_name?: string; role?: string }
  ) =>
    request<GlossaryResponse>(
      `/api/novels/${encodeURIComponent(name)}/glossary/characters/${encodeURIComponent(original)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }
    ),
  addRelationship: (
    name: string,
    payload: { from_char: string; to_char: string; relationship: string; since?: number }
  ) =>
    request<GlossaryResponse>(`/api/novels/${encodeURIComponent(name)}/glossary/relationships`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }),
  validateGlossary: (name: string) =>
    request<{ job_id: string }>(`/api/novels/${encodeURIComponent(name)}/glossary/validate`, {
      method: 'POST'
    }),
  auditGlossary: (name: string, target?: string) => {
    const params = new URLSearchParams()
    if (target) params.set('target', target)
    return request<{ job_id: string }>(
      `/api/novels/${encodeURIComponent(name)}/glossary/audit${
        params.toString() ? `?${params.toString()}` : ''
      }`,
      { method: 'POST' }
    )
  },

  listJobs: () => request<JobListResponse>('/api/jobs'),
  getJob: (id: string) => request<JobModel>(`/api/jobs/${id}`),
  cancelJob: (id: string) =>
    request<JobModel>(`/api/jobs/${id}/cancel`, { method: 'POST' })
}

export type ApiError = Error & { code: string; status: number; details: Record<string, unknown> | null }
