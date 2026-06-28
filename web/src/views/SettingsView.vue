<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { api } from '@/api/client'
import type { ProviderInfo } from '@/api/types'
import ProviderModelField from '@/components/ProviderModelField.vue'

const settings = useSettingsStore()
const providers = ref<ProviderInfo[]>([])
const defaultProvider = ref<string>('')
const checkResult = ref<{ provider: string; ok: boolean; detail: string | null } | null>(null)
const persistResult = ref<{ path: string; changed_keys: string[] } | null>(null)
const persisting = ref(false)
const geminiKeyInput = ref('')
const openrouterKeyInput = ref('')
const keySaveStatus = ref<{ provider: string; ok: boolean; message: string } | null>(null)
const error = ref<string | null>(null)

const ALL_PROVIDER_NAMES = ['ollama', 'gemini', 'openrouter'] as const

onMounted(async () => {
  await settings.refresh()
  const list = await api.listProviders()
  providers.value = list.providers
  defaultProvider.value = list.default_provider
})

const fallbackOptions = computed(() => {
  const current = settings.settings?.llm_provider ?? ''
  return [
    { value: '', label: '(none)' },
    ...ALL_PROVIDER_NAMES.filter((name) => name !== current).map((name) => ({ value: name, label: name }))
  ]
})

async function patchSetting(key: string, value: unknown) {
  await settings.patch({ [key]: value })
}

async function runProviderCheck(provider: string) {
  checkResult.value = null
  try {
    checkResult.value = await api.checkProvider(provider)
  } catch (err) {
    checkResult.value = { provider, ok: false, detail: (err as Error).message }
  }
}

async function saveApiKey(provider: 'gemini' | 'openrouter') {
  const value = provider === 'gemini' ? geminiKeyInput.value : openrouterKeyInput.value
  if (!value.trim()) {
    keySaveStatus.value = { provider, ok: false, message: 'Enter a key first.' }
    return
  }
  keySaveStatus.value = null
  try {
    const result = await settings.patchAndPersist({
      [provider === 'gemini' ? 'gemini_api_key' : 'openrouter_api_key']: value
    })
    if (result) {
      keySaveStatus.value = { provider, ok: true, message: 'Key saved.' }
    }
    if (provider === 'gemini') geminiKeyInput.value = ''
    else openrouterKeyInput.value = ''
  } catch (err) {
    keySaveStatus.value = { provider, ok: false, message: (err as Error).message }
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
          <label>Default provider</label>
          <select :value="settings.settings.llm_provider" @change="patchSetting('llm_provider', ($event.target as HTMLSelectElement).value)">
            <option v-for="p in providers" :key="p.name" :value="p.name">{{ p.name }}</option>
          </select>
        </div>
        <div>
          <label>Fallback provider (must differ from the default)</label>
          <select
            :value="settings.settings.fallback_provider ?? ''"
            @change="patchSetting('fallback_provider', ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="opt in fallbackOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div>
          <label>Ollama model</label>
          <ProviderModelField
            provider="ollama"
            :model-value="settings.settings.ollama_model"
            @update:model-value="(v: string) => patchSetting('ollama_model', v)"
          />
        </div>
        <div>
          <label>Gemini model</label>
          <ProviderModelField
            provider="gemini"
            :model-value="settings.settings.gemini_model"
            @update:model-value="(v: string) => patchSetting('gemini_model', v)"
          />
        </div>
        <div>
          <label>OpenRouter model</label>
          <ProviderModelField
            provider="openrouter"
            :model-value="settings.settings.openrouter_model"
            @update:model-value="(v: string) => patchSetting('openrouter_model', v)"
          />
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
            <label class="check">
              <input type="checkbox" :checked="settings.settings.use_browser" @change="patchSetting('use_browser', ($event.target as HTMLInputElement).checked)" />
              <span>Use headless browser by default</span>
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
      <h2>Provider API keys</h2>
      <p class="muted">
        Current values are not displayed. Enter a new key to replace the stored value; leave blank and
        Save to keep the current one. Keys are written to <code>.env</code> when you press the
        runtime-settings Save button.
      </p>

      <div class="grid">
        <div>
          <label>Gemini API key</label>
          <div class="row gap-1" style="align-items: center;">
            <span
              class="badge"
              :class="settings.settings?.gemini_api_key_configured ? 'ok' : 'danger'"
            >{{ settings.settings?.gemini_api_key_configured ? 'configured' : 'not configured' }}</span>
            <input
              v-model="geminiKeyInput"
              type="password"
              autocomplete="off"
              placeholder="paste new key"
              style="flex: 1 1 auto;"
            />
            <button
              type="button"
              class="secondary"
              :disabled="!geminiKeyInput.trim()"
              @click="saveApiKey('gemini')"
            >Save</button>
          </div>
          <p
            v-if="keySaveStatus && keySaveStatus.provider === 'gemini'"
            class="muted"
            style="margin-top: 0.25rem; font-size: 0.85rem;"
          >{{ keySaveStatus.message }}</p>
        </div>

        <div>
          <label>OpenRouter API key</label>
          <div class="row gap-1" style="align-items: center;">
            <span
              class="badge"
              :class="settings.settings?.openrouter_api_key_configured ? 'ok' : 'danger'"
            >{{ settings.settings?.openrouter_api_key_configured ? 'configured' : 'not configured' }}</span>
            <input
              v-model="openrouterKeyInput"
              type="password"
              autocomplete="off"
              placeholder="paste new key"
              style="flex: 1 1 auto;"
            />
            <button
              type="button"
              class="secondary"
              :disabled="!openrouterKeyInput.trim()"
              @click="saveApiKey('openrouter')"
            >Save</button>
          </div>
          <p
            v-if="keySaveStatus && keySaveStatus.provider === 'openrouter'"
            class="muted"
            style="margin-top: 0.25rem; font-size: 0.85rem;"
          >{{ keySaveStatus.message }}</p>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Providers</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Configured</th>
            <th>Default model</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in providers" :key="p.name">
            <td>{{ p.name }}<span v-if="p.name === defaultProvider" class="muted"> (default)</span></td>
            <td>
              <span v-if="p.configured" class="badge ok">yes</span>
              <span v-else class="badge danger">missing key</span>
            </td>
            <td><code>{{ p.default_model ?? '—' }}</code></td>
            <td>
              <button class="secondary" type="button" @click="runProviderCheck(p.name)">Check</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="checkResult" style="margin-top: 0.5rem;">
        <span :class="checkResult.ok ? 'badge ok' : 'badge danger'">
          {{ checkResult.provider }}: {{ checkResult.ok ? 'ok' : 'failed' }}
        </span>
        <span v-if="checkResult.detail" class="muted">— {{ checkResult.detail }}</span>
      </p>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
