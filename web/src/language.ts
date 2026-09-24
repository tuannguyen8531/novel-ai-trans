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

/**
 * Format language code or raw name into a localized full name.
 */
export function formatLanguage(codeOrName?: string | null, fallback = ''): string {
  if (!codeOrName) return fallback ? t(LANGUAGE_MAP[fallback.toLowerCase()] ?? fallback.toLowerCase()) : fallback
  const normalized = codeOrName.trim().toLowerCase()
  return LANGUAGE_MAP[normalized] ? t(LANGUAGE_MAP[normalized]) : codeOrName.charAt(0).toUpperCase() + codeOrName.slice(1)
}
