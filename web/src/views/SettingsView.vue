<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  SlidersHorizontal,
  Cpu,
  Send,
  Save,
  RotateCw,
  Check,
  Server
} from '@lucide/vue'
import { useSettingsStore } from '@/composables/settings'
import type { OllamaAccount, ProviderInfo, SettingsPatch } from '@/api/types'
import ProviderModelField from '@/components/ProviderModelField.vue'
import CustomSelect from '@/components/common/CustomSelect.vue'
import { t } from '@/i18n'

const settings = useSettingsStore()
const activeTab = ref<'general' | 'providers' | 'telegram'>('providers')

const providers = ref<ProviderInfo[]>([])
const persistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const persisting = ref(false)
const telegramPersistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const telegramPersisting = ref(false)
const providerPersistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const providerPersisting = ref(false)
const providerRefreshKey = ref(0)
const ollamaAccount = ref<OllamaAccount | null>(null)
const ollamaAccountLoading = ref(false)

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

const primaryProviderOptions = computed(() => [
  { value: 'ollama', label: t('ollama') },
  { value: 'gemini', label: t('gemini') },
  { value: 'openrouter', label: t('openrouter') }
])

const fallbackOptions = computed(() => {
  const current = providerForm.llm_provider
  return [
    { value: '', label: `(${t('none')})` },
    ...ALL_PROVIDER_NAMES.filter((name) => name !== current).map((name) => ({
      value: name,
      label: t(name)
    }))
  ]
})

const targetLanguageOptions = computed(() => [
  { value: 'vi', label: t('vietnamese') },
  { value: 'en', label: t('english') }
])

const chunkModeOptions = computed(() => [
  { value: 'chars', label: t('text_characters') },
  { value: 'tokens', label: t('tokens_estimated') }
])

const telegramParseModeOptions = computed(() => [
  { value: 'HTML', label: t('html') },
  { value: '', label: t('plain_text') }
])

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
  providers.value = await settings.listProviders()
  await refreshOllamaAccount()
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

async function patchSetting(key: keyof SettingsPatch, value: SettingsPatch[keyof SettingsPatch]) {
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
    return result.ok ? t('check_ok') : t('check_failed')
  }
  return providerConfigured(provider) ? t('configured') : t('missing_key')
}

function getOllamaStatusClass(): string {
  const result = checkResults.value.ollama
  if (result) {
    return result.ok ? 'ok' : 'danger'
  }
  return ollamaAccount.value?.signed_in ? 'ok' : 'danger'
}

function getOllamaStatusText(): string {
  const result = checkResults.value.ollama
  if (result) {
    return result.ok ? t('check_ok') : t('check_failed')
  }
  if (ollamaAccountLoading.value) {
    return t('checking_account')
  }
  return ollamaAccount.value?.signed_in ? t('signed_in') : t('not_signed_in')
}

function getOllamaAccountText(): string {
  if (ollamaAccountLoading.value) {
    return t('checking')
  }
  if (ollamaAccount.value?.username) {
    return ollamaAccount.value.username
  }
  if (ollamaAccount.value?.detail === 'Not signed in') {
    return t('not_signed_in_to_ollama_cloud')
  }
  return t('unavailable')
}

async function refreshOllamaAccount() {
  ollamaAccountLoading.value = true
  try {
    ollamaAccount.value = await settings.ollamaAccount()
  } catch (err) {
    ollamaAccount.value = {
      signed_in: false,
      username: null,
      detail: (err as Error).message
    }
  } finally {
    ollamaAccountLoading.value = false
  }
}

async function runProviderCheck(provider: string) {
  clearProviderCheck(provider)
  checkingProviders.value = { ...checkingProviders.value, [provider]: true }
  try {
    const res = await settings.checkProvider(provider, {
      ollama_base_url: providerForm.ollama_base_url,
      gemini_api_key: geminiKeyInput.value.trim() || undefined,
      openrouter_api_key: openrouterKeyInput.value.trim() || undefined
    })
    if (provider === 'ollama') {
      if (res.ok) {
        await refreshOllamaAccount()
      } else if (res.detail?.toLowerCase().includes('not_signed_in')) {
        ollamaAccount.value = {
          signed_in: false,
          username: null,
          detail: 'Not signed in'
        }
      } else {
        ollamaAccount.value = {
          signed_in: false,
          username: null,
          detail: res.detail
        }
      }
    }
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
      providers.value = await settings.listProviders()
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
  <div class="settings-view-root">
    <!-- Header -->
    <header class="settings-header card-panel">
      <div class="header-icon-box">
        <SlidersHorizontal :size="22" />
      </div>
      <div>
        <h2 class="settings-title">{{ $t("system_settings") }}</h2>
        <p class="settings-subtitle">
          {{ $t("settings_description") }}
        </p>
      </div>
    </header>

    <!-- Nav Tabs -->
    <nav class="settings-nav-tabs" :aria-label="$t('settings_category')">
      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'providers' }"
        @click="activeTab = 'providers'"
      >
        <Cpu :size="16" />
        <span>{{ $t("llm_providers") }}</span>
      </button>

      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'general' }"
        @click="activeTab = 'general'"
      >
        <SlidersHorizontal :size="16" />
        <span>{{ $t("translation_pipeline") }}</span>
      </button>

      <button
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === 'telegram' }"
        @click="activeTab = 'telegram'"
      >
        <Send :size="16" />
        <span>{{ $t("telegram_notifications") }}</span>
      </button>
    </nav>

    <!-- Global Error -->
    <p v-if="settings.error" class="card-panel error">{{ settings.error }}</p>

    <!-- Tab 1: Providers -->
    <section v-if="activeTab === 'providers'" class="settings-section">
      <div class="card-panel config-card">
        <div class="card-title-row">
          <div>
            <h3 class="card-title">{{ $t("default_fallback_providers") }}</h3>
            <p class="card-desc">{{ $t("default_provider_help") }}</p>
          </div>
        </div>

        <div class="grid-2-cols">
          <div>
            <label>{{ $t("primary_provider") }}</label>
            <CustomSelect
              v-model="providerForm.llm_provider"
              :options="primaryProviderOptions"
            />
          </div>
          <div>
            <label>{{ $t("fallback_provider") }}</label>
            <CustomSelect
              v-model="providerForm.fallback_provider"
              :options="fallbackOptions"
            />
          </div>
        </div>
      </div>

      <!-- Ollama Provider Card -->
      <div class="card-panel provider-item-card">
        <div class="provider-card-header">
          <div class="provider-title-group">
            <Server :size="20" class="provider-icon" />
            <div>
              <h3 class="provider-title">{{ $t("ollama_local_cloud") }}</h3>
              <p class="provider-desc">{{ $t("ollama_connection_description") }}</p>
            </div>
          </div>

          <div class="provider-status-actions">
            <span class="badge" :class="getOllamaStatusClass()">
              {{ getOllamaStatusText() }}
            </span>
            <button
              class="secondary btn-check"
              type="button"
              :disabled="checkingProviders['ollama']"
              @click="runProviderCheck('ollama')"
            >
              <RotateCw :size="13" :class="{ 'spinning': checkingProviders['ollama'] }" />
              <span>{{ checkingProviders['ollama'] ? $t('testing') : $t('test_connection') }}</span>
            </button>
          </div>
        </div>

        <p v-if="checkResults['ollama']?.detail" class="error check-error">
          {{ checkResults['ollama'].detail }}
        </p>

        <div class="provider-form-body">
          <div class="grid-2-cols">
            <div>
              <label>{{ $t("api_base_url") }}</label>
              <input v-model="providerForm.ollama_base_url" />
            </div>
            <div>
              <label>{{ $t("cloud_account") }}</label>
              <input disabled :value="getOllamaAccountText()" />
              <p v-if="!ollamaAccountLoading && ollamaAccount?.detail && ollamaAccount.detail !== 'Not signed in'" class="muted account-hint">
                {{ ollamaAccount.detail }}
              </p>
            </div>
          </div>

          <div>
            <ProviderModelField
              :key="`ollama-${providerRefreshKey}`"
              provider="ollama"
              :label="$t('default_model')"
              :model-value="providerForm.ollama_model"
              @update:model-value="(value: string) => providerForm.ollama_model = value"
            />
          </div>
        </div>
      </div>

      <!-- Gemini Provider Card -->
      <div class="card-panel provider-item-card">
        <div class="provider-card-header">
          <div class="provider-title-group">
            <Cpu :size="20" class="provider-icon" />
            <div>
              <h3 class="provider-title">{{ $t("google_gemini") }}</h3>
              <p class="provider-desc">{{ $t("google_ai_studio_api_key_integration") }}</p>
            </div>
          </div>

          <div class="provider-status-actions">
            <span class="badge" :class="getProviderStatusClass('gemini')">
              {{ getProviderStatusText('gemini') }}
            </span>
            <button
              class="secondary btn-check"
              type="button"
              :disabled="checkingProviders['gemini']"
              @click="runProviderCheck('gemini')"
            >
              <RotateCw :size="13" :class="{ 'spinning': checkingProviders['gemini'] }" />
              <span>{{ checkingProviders['gemini'] ? $t('testing') : $t('test_key') }}</span>
            </button>
          </div>
        </div>

        <p v-if="checkResults['gemini']?.detail" class="error check-error">
          {{ checkResults['gemini'].detail }}
        </p>

        <div class="provider-form-body">
          <div>
            <label>{{ $t("api_key") }}</label>
            <input
              v-model="geminiKeyInput"
              type="password"
              autocomplete="off"
              :placeholder="$t('gemini_key_placeholder')"
            />
          </div>

          <div>
            <ProviderModelField
              :key="`gemini-${providerRefreshKey}`"
              provider="gemini"
              :label="$t('default_model')"
              :model-value="providerForm.gemini_model"
              @update:model-value="(value: string) => providerForm.gemini_model = value"
            />
          </div>
        </div>
      </div>

      <!-- OpenRouter Provider Card -->
      <div class="card-panel provider-item-card">
        <div class="provider-card-header">
          <div class="provider-title-group">
            <Cpu :size="20" class="provider-icon" />
            <div>
              <h3 class="provider-title">{{ $t("openrouter") }}</h3>
              <p class="provider-desc">{{ $t("openrouter_unified_model_routing_api") }}</p>
            </div>
          </div>

          <div class="provider-status-actions">
            <span class="badge" :class="getProviderStatusClass('openrouter')">
              {{ getProviderStatusText('openrouter') }}
            </span>
            <button
              class="secondary btn-check"
              type="button"
              :disabled="checkingProviders['openrouter']"
              @click="runProviderCheck('openrouter')"
            >
              <RotateCw :size="13" :class="{ 'spinning': checkingProviders['openrouter'] }" />
              <span>{{ checkingProviders['openrouter'] ? $t('testing') : $t('test_key') }}</span>
            </button>
          </div>
        </div>

        <p v-if="checkResults['openrouter']?.detail" class="error check-error">
          {{ checkResults['openrouter'].detail }}
        </p>

        <div class="provider-form-body">
          <div>
            <label>{{ $t("api_key") }}</label>
            <input
              v-model="openrouterKeyInput"
              type="password"
              autocomplete="off"
              :placeholder="$t('openrouter_key_placeholder')"
            />
          </div>

          <div>
            <ProviderModelField
              :key="`openrouter-${providerRefreshKey}`"
              provider="openrouter"
              :label="$t('default_model')"
              :model-value="providerForm.openrouter_model"
              @update:model-value="(value: string) => providerForm.openrouter_model = value"
            />
          </div>
        </div>
      </div>

      <!-- Save Providers Bottom Bar -->
      <div class="save-bar">
        <button
          type="button"
          class="btn-primary"
          :disabled="providerPersisting"
          @click="saveProviderSettings"
        >
          <Save :size="16" />
          <span>{{ providerPersisting ? $t('saving_changes') : $t('save_provider_settings') }}</span>
        </button>
        <span v-if="providerPersistResult" class="save-feedback">
          <Check :size="16" />
          <span>{{ $t("provider_settings_saved_successfully") }}</span>
        </span>
      </div>
    </section>

    <!-- Tab 2: General / Translation Pipeline Parameters -->
    <section v-else-if="activeTab === 'general'" class="settings-section">
      <div v-if="settings.settings" class="card-panel config-card">
        <h3 class="card-title">{{ $t("runtime_translation_defaults") }}</h3>
        <p class="card-desc">{{ $t("chunk_parameters_description") }}</p>

        <div class="grid-2-cols">
          <div>
            <label>{{ $t("default_target_language") }}</label>
            <CustomSelect
              :model-value="settings.settings.target_language"
              :options="targetLanguageOptions"
              @change="(val) => patchSetting('target_language', String(val))"
            />
          </div>

          <div>
            <label>{{ $t("chunk_splitting_mode") }}</label>
            <CustomSelect
              :model-value="settings.settings.chunk_mode"
              :options="chunkModeOptions"
              @change="(val) => patchSetting('chunk_mode', String(val))"
            />
          </div>

          <div>
            <label>{{ $t("chunk_size", { unit: settings.settings.chunk_mode === 'tokens' ? $t('tokens') : $t('text_characters') }) }}</label>
            <input
              type="number"
              :value="settings.settings.chunk_size"
              @change="patchSetting('chunk_size', Number(($event.target as HTMLInputElement).value))"
            />
          </div>

          <div>
            <label>{{ $t("review_threshold") }}</label>
            <input
              type="number"
              step="0.05"
              :value="settings.settings.review_threshold"
              @change="patchSetting('review_threshold', Number(($event.target as HTMLInputElement).value))"
            />
          </div>

          <div>
            <label>{{ $t("translation_temperature_range") }}</label>
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              :value="settings.settings.translation_temperature"
              @change="patchSetting('translation_temperature', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>

        <div class="save-bar" style="margin-top: 1.5rem;">
          <button type="button" class="btn-primary" :disabled="persisting" @click="saveSettings">
            <Save :size="16" />
            <span>{{ persisting ? $t('saving') : $t('save_pipeline_defaults') }}</span>
          </button>
          <span v-if="persistResult" class="save-feedback">
            <Check :size="16" />
            <span>{{ $t("runtime_defaults_saved") }}</span>
          </span>
        </div>
      </div>
    </section>

    <!-- Tab 3: Telegram -->
    <section v-else-if="activeTab === 'telegram'" class="settings-section">
      <div class="card-panel config-card">
        <div class="card-title-row">
          <div>
            <h3 class="card-title">{{ $t("telegram_notifications") }}</h3>
            <p class="card-desc">
              {{ $t("telegram_notifications_help") }}
            </p>
          </div>
          <span class="badge" :class="settings.settings?.telegram_configured ? 'ok' : 'danger'">
            {{ settings.settings?.telegram_configured ? $t('bot_token_configured') : $t('no_token_in_environment') }}
          </span>
        </div>

        <div class="grid-form">
          <div class="check-row">
            <label class="check">
              <input v-model="telegramForm.telegram_enabled" type="checkbox" />
              <span>{{ $t("enable_telegram_notifications") }}</span>
            </label>
            <label class="check">
              <input v-model="telegramForm.telegram_silent" type="checkbox" />
              <span>{{ $t("send_silently_no_notification_sound") }}</span>
            </label>
          </div>

          <div>
            <label>{{ $t("api_base_url") }}</label>
            <input v-model="telegramForm.telegram_api_base" />
          </div>

          <div class="grid-2-cols">
            <div>
              <label>{{ $t("parse_mode") }}</label>
              <CustomSelect
                v-model="telegramForm.telegram_parse_mode"
                :options="telegramParseModeOptions"
              />
            </div>

            <div>
              <label>{{ $t("timeout_seconds") }}</label>
              <input
                v-model.number="telegramForm.telegram_timeout_seconds"
                type="number"
                min="0.1"
                step="0.5"
              />
            </div>
          </div>
        </div>

        <div class="save-bar" style="margin-top: 1.5rem;">
          <button
            type="button"
            class="btn-primary"
            :disabled="telegramPersisting"
            @click="saveTelegramSettings"
          >
            <Save :size="16" />
            <span>{{ telegramPersisting ? $t('saving') : $t('save_telegram_settings') }}</span>
          </button>
          <span v-if="telegramPersistResult" class="save-feedback">
            <Check :size="16" />
            <span>{{ $t("telegram_settings_saved") }}</span>
          </span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.settings-view-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  max-width: 60rem;
}

.settings-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
}

.header-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-lg);
  background: var(--accent-subtle);
  border: 1px solid rgba(79, 125, 249, 0.25);
  color: var(--accent);
  flex-shrink: 0;
}

.settings-title {
  margin: 0;
  font-size: 1.45rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.settings-subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: var(--fg-secondary);
}

/* Nav Tabs */
.settings-nav-tabs {
  display: inline-flex;
  gap: 0.5rem;
  padding: 0.35rem;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  align-self: flex-start;
  flex-wrap: wrap;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1.15rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-weight: 600;
  background: transparent;
  color: var(--fg-secondary);
  border: 1px solid transparent;
  cursor: pointer;
  box-shadow: none;
  transition: all var(--transition-fast);
}

.tab-btn:hover {
  color: var(--fg-primary);
  background: var(--bg-surface);
  transform: none;
}

.tab-btn.active {
  background: var(--bg-surface);
  color: var(--accent);
  border-color: var(--border-base);
  box-shadow: var(--shadow-subtle);
}

/* Settings Section */
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  animation: modal-fade-in 0.18s ease;
}

.config-card {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
}

.card-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.card-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--fg-primary);
}

.card-desc {
  margin: 0.2rem 0 0;
  font-size: 0.85rem;
  color: var(--fg-secondary);
}

.grid-2-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.grid-form {
  display: grid;
  gap: 1rem;
}

/* Provider Item Card */
.provider-item-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
}

.provider-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.provider-title-group {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
}

.provider-icon {
  color: var(--accent);
  margin-top: 0.2rem;
  flex-shrink: 0;
}

.provider-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--fg-primary);
}

.provider-desc {
  margin: 0.15rem 0 0;
  font-size: 0.85rem;
  color: var(--fg-secondary);
}

.provider-status-actions {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.btn-check {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  padding: 0.35rem 0.75rem;
}

.spinning {
  animation: spin 1s linear infinite;
}

.check-error {
  margin: 0;
  font-size: 0.85rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  background: var(--danger-subtle);
}

.provider-form-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-subtle);
}

.account-hint {
  font-size: 0.75rem;
  margin-top: 0.25rem;
}

.save-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding-top: 0.5rem;
}

.save-feedback {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--ok);
  font-size: 0.85rem;
  font-weight: 500;
}

@media (max-width: 640px) {
  .grid-2-cols {
    grid-template-columns: 1fr;
  }
}
</style>
