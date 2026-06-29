<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { api } from '@/api/client'
import type { ProviderInfo } from '@/api/types'
import ProviderModelField from '@/components/ProviderModelField.vue'

const settings = useSettingsStore()
const providers = ref<ProviderInfo[]>([])
const persistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const persisting = ref(false)
const telegramPersistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const telegramPersisting = ref(false)
const providerPersistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const providerPersisting = ref(false)
const providerRefreshKey = ref(0)
const telegramForm = reactive({
  telegram_enabled: false,
  telegram_api_base: 'https://api.telegram.org',
  telegram_parse_mode: 'HTML' as '' | 'HTML',
  telegram_silent: false,
  telegram_timeout_seconds: 10
})
const geminiKeyInput = ref('')
const openrouterKeyInput = ref('')
const providerForm = reactive({
  llm_provider: 'ollama' as 'ollama' | 'gemini' | 'openrouter',
  fallback_provider: '' as '' | 'ollama' | 'gemini' | 'openrouter',
  ollama_base_url: 'http://localhost:11434',
  ollama_model: '',
  gemini_model: '',
  openrouter_model: ''
})

const ALL_PROVIDER_NAMES = ['ollama', 'gemini', 'openrouter'] as const

onMounted(async () => {
  await settings.refresh()
  if (settings.settings) {
    telegramForm.telegram_enabled = settings.settings.telegram_enabled
    telegramForm.telegram_api_base = settings.settings.telegram_api_base
    telegramForm.telegram_parse_mode = settings.settings.telegram_parse_mode
    telegramForm.telegram_silent = settings.settings.telegram_silent
    telegramForm.telegram_timeout_seconds = settings.settings.telegram_timeout_seconds
    providerForm.llm_provider = settings.settings.llm_provider as typeof providerForm.llm_provider
    providerForm.fallback_provider = settings.settings.fallback_provider as typeof providerForm.fallback_provider
    providerForm.ollama_base_url = settings.settings.ollama_base_url
    providerForm.ollama_model = settings.settings.ollama_model
    providerForm.gemini_model = settings.settings.gemini_model
    providerForm.openrouter_model = settings.settings.openrouter_model
  }
  const list = await api.listProviders()
  providers.value = list.providers
})

const fallbackOptions = computed(() => {
  const current = providerForm.llm_provider
  return [
    { value: '', label: '(none)' },
    ...ALL_PROVIDER_NAMES.filter((name) => name !== current).map((name) => ({ value: name, label: name }))
  ]
})

watch(
  () => providerForm.llm_provider,
  (current) => {
    if (providerForm.fallback_provider === current) {
      providerForm.fallback_provider = ''
    }
  }
)

function providerConfigured(provider: string): boolean {
  return providers.value.find((item) => item.name === provider)?.configured ?? false
}

async function patchSetting(key: string, value: unknown) {
  await settings.patch({ [key]: value })
}

const checkResults = ref<Record<string, { ok: boolean; detail: string | null }>>({})
const checkingProviders = ref<Record<string, boolean>>({})

function clearProviderCheck(provider: string) {
  const next = { ...checkResults.value }
  delete next[provider]
  checkResults.value = next
}

watch(() => providerForm.ollama_base_url, () => clearProviderCheck('ollama'))
watch(geminiKeyInput, () => clearProviderCheck('gemini'))
watch(openrouterKeyInput, () => clearProviderCheck('openrouter'))

function getProviderStatusClass(provider: string): string {
  const result = checkResults.value[provider]
  if (result) {
    return result.ok ? 'ok' : 'danger'
  }
  return providerConfigured(provider) ? 'ok' : 'danger'
}

function getProviderStatusText(provider: string): string {
  const result = checkResults.value[provider]
  if (result) {
    return result.ok ? 'check: ok' : 'check: failed'
  }
  return providerConfigured(provider) ? 'configured' : 'missing key'
}

async function runProviderCheck(provider: string) {
  clearProviderCheck(provider)
  checkingProviders.value = { ...checkingProviders.value, [provider]: true }
  try {
    const res = await api.checkProvider(provider, {
      ollama_base_url: providerForm.ollama_base_url,
      gemini_api_key: geminiKeyInput.value.trim() || undefined,
      openrouter_api_key: openrouterKeyInput.value.trim() || undefined
    })
    checkResults.value = {
      ...checkResults.value,
      [provider]: { ok: res.ok, detail: res.detail }
    }
  } catch (err) {
    checkResults.value = {
      ...checkResults.value,
      [provider]: { ok: false, detail: (err as Error).message }
    }
  } finally {
    checkingProviders.value = { ...checkingProviders.value, [provider]: false }
  }
}

async function saveProviderSettings() {
  providerPersisting.value = true
  providerPersistResult.value = null
  try {
    providerPersistResult.value = await settings.persistProviders({
      ...providerForm,
      gemini_api_key: geminiKeyInput.value.trim() || undefined,
      openrouter_api_key: openrouterKeyInput.value.trim() || undefined
    })
    if (providerPersistResult.value) {
      geminiKeyInput.value = ''
      openrouterKeyInput.value = ''
      providers.value = (await api.listProviders()).providers
      checkResults.value = {}
      providerRefreshKey.value += 1
    }
  } finally {
    providerPersisting.value = false
  }
}

async function saveSettings() {
  persisting.value = true
  persistResult.value = null
  try {
    const result = await settings.persist()
    if (result) {
      persistResult.value = result
    }
  } finally {
    persisting.value = false
  }
}

async function saveTelegramSettings() {
  telegramPersisting.value = true
  telegramPersistResult.value = null
  try {
    telegramPersistResult.value = await settings.persistTelegram({ ...telegramForm })
  } finally {
    telegramPersisting.value = false
  }
}
</script>

<template>
  <section class="flex-col gap-3">
    <div v-if="settings.settings" class="card">
      <h2>Runtime settings</h2>
      <p class="muted">
        These defaults are used by future jobs. Secrets are not displayed and cannot be
        changed through this interface.
      </p>
      <div class="grid">
        <div>
          <label>Target language</label>
          <select :value="settings.settings.target_language" @change="patchSetting('target_language', ($event.target as HTMLSelectElement).value)">
            <option value="vi">vi</option>
            <option value="en">en</option>
          </select>
        </div>
        <div>
          <label>Translated root</label>
          <input :value="settings.settings.translated_dir" @change="patchSetting('translated_dir', ($event.target as HTMLInputElement).value)" />
        </div>
        <div>
          <label>Chunk size</label>
          <input type="number" :value="settings.settings.chunk_size" @change="patchSetting('chunk_size', Number(($event.target as HTMLInputElement).value))" />
        </div>
        <div>
          <label>Review threshold</label>
          <input type="number" step="0.05" :value="settings.settings.review_threshold" @change="patchSetting('review_threshold', Number(($event.target as HTMLInputElement).value))" />
        </div>
        <div>
          <label>Translation temperature (0.0 – 1.0)</label>
          <input
            type="number"
            step="0.05"
            min="0"
            max="1"
            :value="settings.settings.translation_temperature"
            @change="patchSetting('translation_temperature', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div>
          <label>Default behaviour</label>
          <div class="check-row">
            <label class="check">
              <input type="checkbox" :checked="settings.settings.enable_review" @change="patchSetting('enable_review', ($event.target as HTMLInputElement).checked)" />
              <span>Enable review step by default</span>
            </label>
            <label class="check">
              <input type="checkbox" :checked="settings.settings.enable_summary" @change="patchSetting('enable_summary', ($event.target as HTMLInputElement).checked)" />
              <span>Generate chapter summaries by default</span>
            </label>
          </div>
        </div>
        <div class="row gap-2" style="margin-top: 0.5rem; align-items: center;">
          <button type="button" :disabled="persisting" @click="saveSettings">
            {{ persisting ? 'Saving…' : 'Save' }}
          </button>
          <span v-if="persistResult" class="muted">
            Saved {{ persistResult.changed_keys.length }} config(s).
          </span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Telegram notifications</h2>
      <p class="muted">
        Bot token and chat ID are read from <code>.env</code> and are never displayed here.
        Credentials are
        <span class="badge" :class="settings.settings?.telegram_configured ? 'ok' : 'danger'">
          {{ settings.settings?.telegram_configured ? 'configured' : 'not configured' }}
        </span>.
      </p>
      <div class="grid">
        <div class="check-row">
          <label class="check">
            <input v-model="telegramForm.telegram_enabled" type="checkbox" />
            <span>Enable notifications</span>
          </label>
          <label class="check">
            <input v-model="telegramForm.telegram_silent" type="checkbox" />
            <span>Send silently</span>
          </label>
        </div>
        <div>
          <label>API base</label>
          <input v-model="telegramForm.telegram_api_base" />
        </div>
        <div>
          <label>Parse mode</label>
          <select v-model="telegramForm.telegram_parse_mode">
            <option value="HTML">HTML</option>
            <option value="">Plain text</option>
          </select>
        </div>
        <div>
          <label>Timeout seconds</label>
          <input v-model.number="telegramForm.telegram_timeout_seconds" type="number" min="0.1" step="0.5" />
        </div>
        <div class="row gap-2" style="margin-top: 0.5rem; align-items: center;">
          <button type="button" :disabled="telegramPersisting" @click="saveTelegramSettings">
            {{ telegramPersisting ? 'Saving…' : 'Save Telegram' }}
          </button>
          <span v-if="telegramPersistResult" class="muted">
            Saved {{ telegramPersistResult.changed_keys.length }} Telegram setting(s).
          </span>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Providers</h2>
      <p class="muted">
        API keys are never displayed. Leave a key blank to keep its current value.
        Check uses the values currently shown and verifies connectivity and credentials, not the selected model.
      </p>
      <div class="grid">
        <div>
          <label>Default provider</label>
          <select v-model="providerForm.llm_provider">
            <option v-for="name in ALL_PROVIDER_NAMES" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
        <div>
          <label>Fallback provider</label>
          <select v-model="providerForm.fallback_provider">
            <option v-for="option in fallbackOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </div>

        <div>
          <div class="row" style="justify-content: space-between; align-items: center;">
            <h3>Ollama</h3>
            <div class="row gap-1" style="align-items: center;">
              <span v-if="checkResults['ollama']" class="badge" :class="checkResults['ollama'].ok ? 'ok' : 'danger'">
                {{ checkResults['ollama'].ok ? 'check: ok' : 'check: failed' }}
              </span>
              <button class="secondary" type="button" :disabled="checkingProviders['ollama']" @click="runProviderCheck('ollama')">
                {{ checkingProviders['ollama'] ? 'Checking…' : 'Check' }}
              </button>
            </div>
          </div>
          <p v-if="checkResults['ollama']?.detail" class="error" style="margin-top: 0.25rem; font-size: 0.85rem;">
            {{ checkResults['ollama'].detail }}
          </p>
          <label>API base</label>
          <input v-model="providerForm.ollama_base_url" />
          <ProviderModelField
            :key="`ollama-${providerRefreshKey}`"
            provider="ollama"
            label="Model"
            :model-value="providerForm.ollama_model"
            @update:model-value="(value: string) => providerForm.ollama_model = value"
          />
        </div>

        <div>
          <div class="row" style="justify-content: space-between; align-items: center;">
            <h3>Gemini</h3>
            <div class="row gap-1" style="align-items: center;">
              <span class="badge" :class="getProviderStatusClass('gemini')">
                {{ getProviderStatusText('gemini') }}
              </span>
              <button class="secondary" type="button" :disabled="checkingProviders['gemini']" @click="runProviderCheck('gemini')">
                {{ checkingProviders['gemini'] ? 'Checking…' : 'Check' }}
              </button>
            </div>
          </div>
          <p v-if="checkResults['gemini']?.detail" class="error" style="margin-top: 0.25rem; font-size: 0.85rem;">
            {{ checkResults['gemini'].detail }}
          </p>
          <label>API key</label>
          <input v-model="geminiKeyInput" type="password" autocomplete="off" placeholder="paste new key or leave blank" />
          <ProviderModelField
            :key="`gemini-${providerRefreshKey}`"
            provider="gemini"
            label="Model"
            :model-value="providerForm.gemini_model"
            @update:model-value="(value: string) => providerForm.gemini_model = value"
          />
        </div>

        <div>
          <div class="row" style="justify-content: space-between; align-items: center;">
            <h3>OpenRouter</h3>
            <div class="row gap-1" style="align-items: center;">
              <span class="badge" :class="getProviderStatusClass('openrouter')">
                {{ getProviderStatusText('openrouter') }}
              </span>
              <button class="secondary" type="button" :disabled="checkingProviders['openrouter']" @click="runProviderCheck('openrouter')">
                {{ checkingProviders['openrouter'] ? 'Checking…' : 'Check' }}
              </button>
            </div>
          </div>
          <p v-if="checkResults['openrouter']?.detail" class="error" style="margin-top: 0.25rem; font-size: 0.85rem;">
            {{ checkResults['openrouter'].detail }}
          </p>
          <label>API key</label>
          <input v-model="openrouterKeyInput" type="password" autocomplete="off" placeholder="paste new key or leave blank" />
          <ProviderModelField
            :key="`openrouter-${providerRefreshKey}`"
            provider="openrouter"
            label="Model"
            :model-value="providerForm.openrouter_model"
            @update:model-value="(value: string) => providerForm.openrouter_model = value"
          />
        </div>

        <div class="row gap-2" style="align-items: center;">
          <button type="button" :disabled="providerPersisting" @click="saveProviderSettings">
            {{ providerPersisting ? 'Saving…' : 'Save Providers' }}
          </button>
          <span v-if="providerPersistResult" class="muted">
            Saved {{ providerPersistResult.changed_keys.length }} provider setting(s).
          </span>
        </div>
      </div>
    </div>

    <p v-if="settings.error" class="error">{{ settings.error }}</p>
  </section>
</template>
