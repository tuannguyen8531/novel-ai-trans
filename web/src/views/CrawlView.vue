<script setup lang="ts">
import { useRouter } from 'vue-router'
import JobMonitor from '@/components/JobMonitor.vue'
import { useCrawl } from '@/composables/crawl'

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
</script>

<template>
  <section class="flex-col gap-3">
    <nav class="crawl-tabs" aria-label="Crawl tools" role="tablist">
      <button
        id="crawl-tab"
        type="button"
        class="crawl-tab"
        role="tab"
        :aria-selected="activeTab === 'crawl'"
        aria-controls="crawl-panel"
        @click="activeTab = 'crawl'"
      >
        Crawl Novel Chapters
      </button>
      <button
        id="generate-config-tab"
        type="button"
        class="crawl-tab"
        role="tab"
        :aria-selected="activeTab === 'generate'"
        aria-controls="generate-config-panel"
        @click="activeTab = 'generate'"
      >
        Generate Config
      </button>
    </nav>

    <div
      v-if="activeTab === 'crawl'"
      id="crawl-panel"
      class="crawl-tab-panel flex-col gap-3"
      role="tabpanel"
      aria-labelledby="crawl-tab"
    >
      <div class="card">
      <h2>Crawl Novel Chapters</h2>
      <p class="muted">
        Pick a novel config. The job fetches chapters, writes them into
        the novel input directory, and streams progress live.
      </p>

      <div class="grid">
        <div>
          <label>Config</label>
          <select v-model="selectedConfig" :disabled="!configs.length">
            <option v-if="!configs.length" disabled value="">
              {{ loadingConfigs ? 'Loading…' : 'No novel configs found' }}
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
                :checked="browser && !headed"
                @change="selectBrowserMode('headless')"
              />
              <span>Headless browser (for JS challenges)</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="browser-mode"
                :checked="headed"
                @change="selectBrowserMode('headed')"
              />
              <span>Headed browser (visible window)</span>
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
          <label>Concurrency &amp; limit</label>
          <div class="row gap-2" style="align-items: center;">
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">Workers</span>
              <input v-model.number="workers" type="number" min="1" max="8" style="max-width: 5rem;" />
            </label>
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">Max chapters (0 = unlimited)</span>
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
        <h3>Current config — <code>{{ selectedConfig }}</code></h3>
        <p v-if="loadingSelectedConfig" class="muted">Loading config...</p>
        <textarea
          v-else
          v-model="selectedConfigText"
          class="draft-editor"
          spellcheck="false"
        ></textarea>
        <p v-if="selectedConfigError" class="error" style="margin-top: 0.5rem;">{{ selectedConfigError }}</p>
        <div v-if="!loadingSelectedConfig" class="row gap-2" style="margin-top: 0.75rem;">
          <button type="button" :disabled="savingSelectedConfig" @click="saveSelectedConfig">
            {{ savingSelectedConfig ? 'Validating…' : 'Validate & save' }}
          </button>
          <button class="secondary" type="button" :disabled="savingSelectedConfig" @click="loadSelectedConfig(selectedConfig)">
            Reload
          </button>
        </div>
        <p class="muted" style="margin-top: 0.5rem;">
          JSON structure, required fields, and config name are validated by the server before the file is replaced.
        </p>
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
      class="crawl-tab-panel flex-col gap-3"
      role="tabpanel"
      aria-labelledby="generate-config-tab"
    >
      <div class="card">
        <h2>Generate config</h2>
      <p class="muted">
        Provide the novel's main information URL. The AI extracts its metadata and table of
        contents, then proposes a site config. The result is saved as a draft; review and edit it,
        then save the crawl settings to <code>translated/&lt;name&gt;/config.json</code> and the novel
        information to <code>translated/&lt;name&gt;/metadata.json</code>.
      </p>

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
                :checked="generateUseBrowser && !generateHeaded"
                @change="selectGenerateBrowserMode('headless')"
              />
              <span>Headless browser (for JS challenges)</span>
            </label>
            <label class="check">
              <input
                type="radio"
                name="generate-browser-mode"
                :checked="generateHeaded"
                @change="selectGenerateBrowserMode('headed')"
              />
              <span>Headed browser (visible window)</span>
            </label>
          </div>
        </div>
        <div>
          <label>Generation options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="generateNoCache" type="checkbox" />
              <span>Bypass the HTML cache</span>
            </label>
            <label class="check">
              <input v-model="generateIgnoreSample" type="checkbox" />
              <span>Ignore samples and known-domain configs</span>
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
            <p class="muted">Drafts remain available until they expire or are discarded.</p>
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
              <small class="muted">Expires {{ new Date(draft.expires_at).toLocaleString() }}</small>
            </div>
            <button class="secondary" type="button" @click="loadDraft(draft.draft_id)">Open</button>
            <button class="danger" type="button" @click="deleteDraft(draft.draft_id)">Delete</button>
          </div>
        </div>
      </div>

      <div v-if="generatedDraft" class="card">
        <h3>Review draft — <code>{{ generatedDraft.name }}</code></h3>
        <p class="muted">
          Edit the JSON below, then save it to
          <code>translated/{{ generatedDraft.name }}/config.json</code>.
          Extracted novel information will be merged into
          <code>translated/{{ generatedDraft.name }}/metadata.json</code>.
          Expires {{ new Date(generatedDraft.expires_at).toLocaleString() }}.
        </p>
        <textarea v-model="draftConfigText" class="draft-editor" spellcheck="false"></textarea>
        <div class="row gap-2" style="margin-top: 0.75rem;">
          <button type="button" @click="saveGeneratedDraft">Validate & save</button>
          <button class="danger" type="button" @click="discardDraft">Discard draft</button>
        </div>
        <p class="muted" style="margin-top: 0.5rem;">
          Invalid JSON or config schema errors leave both the existing config and this draft unchanged.
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.crawl-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
}

.crawl-tab {
  position: relative;
  padding: 0.65rem 1rem;
  background: transparent;
  color: var(--fg-dim);
  border: 0;
  border-radius: 0;
}

.crawl-tab:hover:not(:disabled) {
  background: var(--bg-elev);
  color: var(--fg);
}

.crawl-tab[aria-selected='true'] {
  color: var(--accent);
}

.crawl-tab[aria-selected='true']::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: var(--accent);
  content: '';
}

.crawl-tab-panel {
  min-width: 0;
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
