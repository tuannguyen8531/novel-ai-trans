<script setup lang="ts">
import { useRouter } from 'vue-router'
import JobMonitor from '@/components/JobMonitor.vue'
import { useCrawl } from '@/composables/crawl'
import { formatDateTime } from '@/datetime'

const router = useRouter()
const {
  activeTab, configs, configsError, loadingConfigs, selectedConfigText, selectedConfigError,
  loadingSelectedConfig, savingSelectedConfig, selectedConfigMessage, selectedConfig, browser,
  headed, ignoreRobots, overwrite, workers,
  maxChapters, crawlError, crawlJobId, generateUrl, generateName, generateProvider,
  generateUseBrowser, generateHeaded, generateNoCache, generateIgnoreSample, generateError,
  generateJobId, generatedDraft, draftConfigText, drafts, draftsError, loadingDrafts,
  selectBrowserMode, selectGenerateBrowserMode, startCrawl, startGenerate, saveSelectedConfig,
  loadSelectedConfig, loadDraft, saveGeneratedDraft, deleteDraft, discardDraft
} = useCrawl()

function isWorkflowActive(workflow: 'crawl' | 'generate') {
  return activeTab.value === workflow
}
</script>

<template>
  <section class="flex-col gap-3">
    <div
      v-if="activeTab === 'crawl'"
      id="crawl-panel"
      class="crawl-source-panel flex-col gap-3"
    >
      <div class="card">
        <div class="workflow-header">
          <div class="workflow-copy">
            <h2>Crawl Novel Chapters</h2>
            <p class="muted">
              Select a novel and start downloading its chapters.
            </p>
          </div>
          <div class="workflow-switch" role="group" aria-label="Website workflow">
            <button
              type="button"
              :class="{ active: isWorkflowActive('crawl') }"
              :aria-pressed="isWorkflowActive('crawl')"
              @click="activeTab = 'crawl'"
            >
              Crawl
            </button>
            <button
              type="button"
              :class="{ active: isWorkflowActive('generate') }"
              :aria-pressed="isWorkflowActive('generate')"
              @click="activeTab = 'generate'"
            >
              Generate
            </button>
          </div>
        </div>

      <div class="grid">
        <div>
          <label>Crawl setup</label>
          <select v-model="selectedConfig" :disabled="!configs.length">
            <option v-if="!configs.length" disabled value="">
              {{ loadingConfigs ? 'Loading…' : 'No crawl setups found' }}
            </option>
            <option v-for="cfg in configs" :key="cfg.name" :value="cfg.name">
              {{ cfg.name }} — {{ cfg.source_url }}
            </option>
          </select>
          <p v-if="configsError" class="error" style="margin-top: 0.25rem;">{{ configsError }}</p>
        </div>

        <div>
          <label>Browser mode</label>
          <div class="check-row">
            <label class="check">
              <input
                type="radio"
                name="browser-mode"
                :checked="!browser && !headed"
                @change="selectBrowserMode('none')"
              />
              <span>Do not use a browser</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="browser-mode"
                :checked="browser && !headed"
                @change="selectBrowserMode('headless')"
              />
              <span>Background browser</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="browser-mode"
                :checked="headed"
                @change="selectBrowserMode('headed')"
              />
              <span>Visible browser</span>
            </label>
          </div>
        </div>

        <div>
          <label>Options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="ignoreRobots" type="checkbox" />
              <span>Ignore robots.txt (only when you have permission)</span>
            </label>
            <label class="check">
              <input v-model="overwrite" type="checkbox" />
              <span>Overwrite already-downloaded chapters</span>
            </label>
          </div>
        </div>

        <div>
          <label>Download limits</label>
          <div class="row gap-2 download-limits">
            <label class="row gap-1 download-limit-field">
              <span class="muted">At once</span>
              <input v-model.number="workers" type="number" min="1" max="8" style="max-width: 5rem;" />
            </label>
            <label class="row gap-1 download-limit-field">
              <span class="muted">Max chapters</span>
              <input
                v-model.number="maxChapters"
                type="number"
                min="0"
                placeholder="unlimited"
                style="max-width: 8rem;"
              />
            </label>
          </div>
        </div>
      </div>

      <div class="row gap-2" style="margin-top: 1rem;">
        <button type="button" :disabled="!selectedConfig" @click="startCrawl">Start crawl</button>
        <button class="secondary" type="button" @click="router.push('/jobs')">View jobs</button>
      </div>
      <p v-if="crawlError" class="error" style="margin-top: 0.5rem;">{{ crawlError }}</p>
      </div>

      <div v-if="selectedConfig" class="card">
        <h3>Current setup — {{ selectedConfig }}</h3>
        <p v-if="loadingSelectedConfig" class="muted">Loading setup...</p>
        <textarea
          v-else
          v-model="selectedConfigText"
          class="draft-editor"
          spellcheck="false"
        ></textarea>
        <p v-if="selectedConfigError" class="error" style="margin-top: 0.5rem;">{{ selectedConfigError }}</p>
        <div v-if="!loadingSelectedConfig" class="row gap-2" style="margin-top: 0.75rem;">
          <button type="button" :disabled="savingSelectedConfig" @click="saveSelectedConfig">
            {{ savingSelectedConfig ? 'Saving…' : 'Save changes' }}
          </button>
          <button class="secondary" type="button" :disabled="savingSelectedConfig" @click="loadSelectedConfig(selectedConfig)">
            Reload
          </button>
        </div>
        <p v-if="selectedConfigMessage" class="muted" style="margin-top: 0.5rem;">{{ selectedConfigMessage }}</p>
      </div>

      <div v-if="crawlJobId" class="card">
        <h3>Crawl job</h3>
        <JobMonitor :job-id="crawlJobId" />
      </div>
    </div>

    <div
      v-else
      id="generate-config-panel"
      class="crawl-source-panel flex-col gap-3"
    >
      <div class="card">
        <div class="workflow-header">
          <div class="workflow-copy">
            <h2>Create Crawl Config</h2>
            <p class="muted">
              Enter the novel page URL, review the generated setup, then save it to start crawling.
            </p>
          </div>
          <div class="workflow-switch" role="group" aria-label="Website workflow">
            <button
              type="button"
              :class="{ active: isWorkflowActive('crawl') }"
              :aria-pressed="isWorkflowActive('crawl')"
              @click="activeTab = 'crawl'"
            >
              Crawl
            </button>
            <button
              type="button"
              :class="{ active: isWorkflowActive('generate') }"
              :aria-pressed="isWorkflowActive('generate')"
              @click="activeTab = 'generate'"
            >
              Generate
            </button>
          </div>
        </div>

      <div class="grid">
        <div>
          <label>Novel information URL</label>
          <input v-model="generateUrl" placeholder="https://example.com/novel" />
        </div>
        <div>
          <label>Config name (optional)</label>
          <input v-model="generateName" placeholder="derived from the URL if blank" />
        </div>
        <div>
          <label>LLM provider (optional)</label>
          <select v-model="generateProvider">
            <option value="">Use default</option>
            <option value="ollama">ollama</option>
            <option value="gemini">gemini</option>
            <option value="openrouter">openrouter</option>
          </select>
        </div>
        <div>
          <label>Browser mode</label>
          <div class="check-row">
            <label class="check">
              <input
                type="radio"
                name="generate-browser-mode"
                :checked="!generateUseBrowser && !generateHeaded"
                @change="selectGenerateBrowserMode('none')"
              />
              <span>Do not use a browser</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="generate-browser-mode"
                :checked="generateUseBrowser && !generateHeaded"
                @change="selectGenerateBrowserMode('headless')"
              />
              <span>Background browser</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="generate-browser-mode"
                :checked="generateHeaded"
                @change="selectGenerateBrowserMode('headed')"
              />
              <span>Visible browser</span>
            </label>
          </div>
        </div>
        <div>
          <label>Generation options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="generateNoCache" type="checkbox" />
              <span>Fetch fresh website data</span>
            </label>
            <label class="check">
              <input v-model="generateIgnoreSample" type="checkbox" />
              <span>Build a new setup from scratch</span>
            </label>
          </div>
        </div>
      </div>

      <div class="row gap-2" style="margin-top: 1rem;">
        <button type="button" :disabled="!generateUrl.trim()" @click="startGenerate">Generate</button>
        <button class="secondary" type="button" @click="router.push('/jobs')">View jobs</button>
      </div>
      <p v-if="generateError" class="error" style="margin-top: 0.5rem;">{{ generateError }}</p>
      </div>

      <div v-if="generateJobId" class="card">
        <h3>Generation job</h3>
        <JobMonitor :job-id="generateJobId" />
      </div>

      <div class="card">
        <div class="row gap-2" style="justify-content: space-between; align-items: center;">
          <div>
            <h3>Pending drafts</h3>
          </div>
        </div>
        <p v-if="loadingDrafts" class="muted">Loading drafts…</p>
        <p v-else-if="draftsError" class="error">{{ draftsError }}</p>
        <p v-else-if="!drafts.length" class="muted">No pending drafts.</p>
        <div v-else class="flex-col gap-2 draft-list">
          <div v-for="draft in drafts" :key="draft.draft_id" class="row gap-2 draft-row">
            <div class="draft-summary">
              <strong><code>{{ draft.name }}</code></strong>
              <span class="muted">{{ draft.source_url || 'No source URL' }}</span>
              <small class="muted">Expires {{ formatDateTime(draft.expires_at) }}</small>
            </div>
            <button class="secondary" type="button" @click="loadDraft(draft.draft_id)">Open</button>
            <button class="danger" type="button" @click="deleteDraft(draft.draft_id)">Delete</button>
          </div>
        </div>
      </div>

      <div v-if="generatedDraft" class="card">
        <h3>Review draft — {{ generatedDraft.name }}</h3>
        <p class="muted">
          Review the generated setup, make any changes, then save it.
          Expires {{ formatDateTime(generatedDraft.expires_at) }}.
        </p>
        <textarea v-model="draftConfigText" class="draft-editor" spellcheck="false"></textarea>
        <div class="row gap-2" style="margin-top: 0.75rem;">
          <button type="button" @click="saveGeneratedDraft">Save setup</button>
          <button class="danger" type="button" @click="discardDraft">Discard draft</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.workflow-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.workflow-copy {
  min-width: 0;
  flex: 1;
}

.workflow-header h2 {
  margin: 0 0 0.35rem;
}

.workflow-header p {
  margin: 0;
}

.workflow-switch {
  display: grid;
  grid-template-columns: repeat(2, 5rem);
  flex: 0 0 auto;
  padding: 0.2rem;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.workflow-switch button {
  min-width: 0;
  padding: 0.4rem 0.65rem;
  background: transparent;
  color: var(--fg-dim);
}

.workflow-switch button:hover:not(:disabled) {
  background: var(--bg-elev);
  color: var(--fg);
}

.workflow-switch button.active {
  background: var(--accent);
  color: #fff;
}

.workflow-switch button.active:hover:not(:disabled) {
  background: var(--accent-strong);
}

.crawl-source-panel {
  min-width: 0;
}

.download-limits {
  align-items: center;
  flex-wrap: wrap;
}

.download-limit-field {
  flex: 0 0 auto;
}

.download-limit-field > span {
  white-space: nowrap;
}

.draft-editor {
  min-height: 22rem;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.85rem;
  line-height: 1.4;
  background: var(--bg-elev-2);
}

.draft-list {
  margin-top: 0.75rem;
}

.draft-row {
  align-items: center;
  padding: 0.65rem;
  border: 1px solid var(--border);
  border-radius: 0.4rem;
}

.draft-summary {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}
</style>
