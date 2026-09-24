import { ref } from 'vue'
import en from '@/locales/en.json'
import vi from '@/locales/vi.json'

export type Locale = 'en' | 'vi'
type MessageValues = Record<string, string | number>

const messages: Record<Locale, Record<string, string>> = { en, vi }
const storedLocale = typeof localStorage === 'undefined' ? null : localStorage.getItem('locale')
const browserLocale = typeof navigator === 'undefined' ? '' : navigator.language.toLowerCase()

export const currentLocale = ref<Locale>(
  storedLocale === 'vi' || storedLocale === 'en'
    ? storedLocale
    : browserLocale.startsWith('vi') ? 'vi' : 'en'
)

if (typeof document !== 'undefined') document.documentElement.lang = currentLocale.value

export function setLocale(locale: Locale): void {
  currentLocale.value = locale
  localStorage.setItem('locale', locale)
  document.documentElement.lang = locale
}

export function t(key: string, values: MessageValues = {}): string {
  return (messages[currentLocale.value][key] ?? messages.en[key] ?? key).replace(
    /\{(\w+)\}/g,
    (placeholder, name: string) => String(values[name] ?? placeholder)
  )
}

export function formatJobKind(kind: string): string {
  const labels: Record<string, string> = {
    translate: 'translate',
    pack: 'pack_epub',
    crawl: 'crawl',
    import: 'import_epub',
    generate: 'generate',
    insert: 'insert'
  }
  return t(labels[kind] ?? kind)
}
