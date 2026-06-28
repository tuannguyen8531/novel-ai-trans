<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { api } from '@/api/client'
import type { ProviderInfo } from '@/api/types'

const settings = useSettingsStore()
const providers = ref<ProviderInfo[]>([])
const defaultProvider = ref<string>('')
const checkResult = ref<{ provider: string; ok: boolean; detail: string | null } | null>(null)
const error = ref<string | null>(null)

onMounted(async () => {
  await settings.refresh()
  const list = await api.listProviders()
  providers.value = list.providers
  defaultProvider.value = list.default_provider
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
