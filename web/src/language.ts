import { t } from '@/i18n'

const LANGUAGE_MAP: Record<string, string> = {
  vi: 'vietnamese',
  vietnamese: 'vietnamese',
  en: 'english',
  english: 'english',
  ko: 'korean',
  korean: 'korean',
  ja: 'japanese',
  japanese: 'japanese',
  zh: 'chinese',
  chinese: 'chinese',
}

export function normalizeLanguage(codeOrName?: string | null): string {
  const normalized = codeOrName?.trim().toLowerCase() ?? ''
  return LANGUAGE_MAP[normalized] ?? normalized
}

/**
 * Format language code or raw name into a localized full name.
 */
export function formatLanguage(codeOrName?: string | null, fallback = ''): string {
  if (!codeOrName) return fallback ? t(normalizeLanguage(fallback)) : fallback
  const normalized = codeOrName.trim().toLowerCase()
  return LANGUAGE_MAP[normalized] ? t(normalizeLanguage(codeOrName)) : codeOrName.charAt(0).toUpperCase() + codeOrName.slice(1)
}
