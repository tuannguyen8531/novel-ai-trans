const LANGUAGE_MAP: Record<string, string> = {
  vi: 'Vietnamese',
  vietnamese: 'Vietnamese',
  en: 'English',
  english: 'English',
  ko: 'Korean',
  korean: 'Korean',
  ja: 'Japanese',
  japanese: 'Japanese',
  zh: 'Chinese',
  chinese: 'Chinese',
}

/**
 * Format language code or raw name into friendly full name (e.g. 'vi' -> 'Vietnamese').
 */
export function formatLanguage(codeOrName?: string | null, fallback = ''): string {
  if (!codeOrName) return fallback
  const normalized = codeOrName.trim().toLowerCase()
  return LANGUAGE_MAP[normalized] ?? (codeOrName.charAt(0).toUpperCase() + codeOrName.slice(1))
}
