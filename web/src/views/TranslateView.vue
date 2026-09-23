<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Sparkles,
  BookOpen,
  ArrowRight,
  Sliders,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  Play,
  RotateCcw,
  CheckCircle2,
  Check
} from '@lucide/vue'
import JobMonitor from '@/components/JobMonitor.vue'
import CustomSelect from '@/components/common/CustomSelect.vue'
import { useTranslation } from '@/composables/translation'
import { getNovelCoverUrl } from '@/composables/novels'
import { formatLanguage } from '@/language'
import placeholderCover from '@/assets/placeholder-cover.png'

const {
  novel, target, source, provider, start, end, limit, force, resume, failedOnly, review,
  summary, translateMetadata, jobId, error, novelOptions, remainingChapters,
  startTranslation
} = useTranslation()

const novelSelectOptions = computed(() => {
  return novelOptions.value.map((item) => ({
    value: item.name,
    label: `${item.title || item.name} (${remainingChapters(item)} ch. remaining)`
  }))
})

const sourceOptions = [
  { value: '', label: 'Auto Detect' },
  { value: 'korean', label: 'Korean (한국어)' },
  { value: 'japanese', label: 'Japanese (日本語)' },
  { value: 'chinese', label: 'Chinese (中文)' }
]

const targetOptions = [
  { value: 'vi', label: 'Vietnamese (Tiếng Việt)' },
  { value: 'en', label: 'English' }
]

const providerOptions = [
  { value: '', label: 'Default Configured Provider' },
  { value: 'ollama', label: 'Ollama (Local)' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'openrouter', label: 'OpenRouter API' }
]

const advancedOpen = ref(false)

const selectedNovelObj = computed(() => {
  if (!novel.value) return null
  return novelOptions.value.find((item) => item.name === novel.value) ?? null
})

const completedCount = computed(() => {
  if (!selectedNovelObj.value) return 0
  const progress = selectedNovelObj.value.targets.find((t) => t.target === target.value)
  return progress?.completed ?? 0
})

const totalChapters = computed(() => {
  return selectedNovelObj.value?.total_input_chapters ?? 0
})

const remainingCount = computed(() => {
  if (!selectedNovelObj.value) return 0
  return remainingChapters(selectedNovelObj.value)
})

const activePreset = computed<'all' | 'failed' | null>(() => {
  if (start.value !== 0 || end.value !== 0 || limit.value !== 0) return null
  if (failedOnly.value && !resume.value) return 'failed'
  if (resume.value && !failedOnly.value) return 'all'
  return null
})

function toggleScopePreset(preset: 'all' | 'failed') {
  if (activePreset.value === preset) {
    if (preset === 'all') {
      resume.value = false
    } else {
      failedOnly.value = false
    }
  } else {
    start.value = 0
    end.value = 0
    limit.value = 0
    if (preset === 'all') {
      failedOnly.value = false
      resume.value = true
    } else {
      failedOnly.value = true
      resume.value = false
    }
  }
}
</script>

<template>
  <div class="translate-studio-root">
    <!-- Studio Header -->
    <header class="studio-header card-panel">
      <div class="header-icon-box">
        <Sparkles :size="22" />
      </div>
      <div>
        <h2 class="studio-title">Translation Studio</h2>
        <p class="studio-subtitle">
          Configure translation parameters, chapter ranges, and start high-fidelity AI translation pipelines.
        </p>
      </div>
    </header>

    <!-- Error Banner -->
    <div v-if="error" class="card-panel alert-error">
      <AlertCircle :size="18" />
      <span>{{ error }}</span>
    </div>

    <!-- Studio Layout -->
    <div class="studio-layout">
      <!-- Configuration Column -->
      <div class="config-column">
        <!-- 1. Novel Selection -->
        <div class="card-panel step-card">
          <div class="step-badge">1</div>
          <div class="step-content">
            <h3 class="step-title">Select Novel</h3>
            <p class="step-desc">Pick a novel from your library to translate.</p>

            <div class="field-wrap">
              <CustomSelect
                v-model="novel"
                :options="novelSelectOptions"
                placeholder="— Select novel from library —"
              />
            </div>

            <!-- Novel Preview Mini Card if selected -->
            <div v-if="selectedNovelObj" class="novel-mini-preview">
              <img
                :src="getNovelCoverUrl(selectedNovelObj.name, selectedNovelObj.illustration_url)"
                :alt="selectedNovelObj.title || selectedNovelObj.name"
                class="mini-cover"
                referrerpolicy="no-referrer"
                @error="($event.target as HTMLImageElement).src = placeholderCover"
              />
              <div class="mini-info">
                <h4 class="mini-title">{{ selectedNovelObj.title || selectedNovelObj.name }}</h4>
                <span class="mini-author">{{ selectedNovelObj.author || 'Unknown author' }}</span>
                <div class="mini-progress-row">
                  <span class="mini-stat">
                    <strong>{{ completedCount }}</strong> / {{ totalChapters }} chapters translated
                  </span>
                  <span v-if="remainingCount > 0" class="badge accent">
                    {{ remainingCount }} left
                  </span>
                  <span v-else class="badge ok">
                    Up to date
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. Language Pair & Engine Selection -->
        <div class="card-panel step-card">
          <div class="step-badge">2</div>
          <div class="step-content">
            <h3 class="step-title">Language Pair & Provider</h3>
            <p class="step-desc">Set source and target languages, and optionally select a specific provider override.</p>

            <div class="grid-2-cols">
              <div>
                <label>Source Language</label>
                <CustomSelect
                  v-model="source"
                  :options="sourceOptions"
                />
              </div>

              <div>
                <label>Target Language</label>
                <CustomSelect
                  v-model="target"
                  :options="targetOptions"
                />
              </div>
            </div>

            <div style="margin-top: 1rem;">
              <label>Provider Override (optional)</label>
              <CustomSelect
                v-model="provider"
                :options="providerOptions"
              />
            </div>
          </div>
        </div>

        <!-- 3. Chapter Scope -->
        <div class="card-panel step-card">
          <div class="step-badge">3</div>
          <div class="step-content">
            <div class="step-header-row">
              <div>
                <h3 class="step-title">Chapter Scope</h3>
                <p class="step-desc">Select which chapters to process in this run.</p>
              </div>

              <!-- Scope Presets -->
              <div class="preset-buttons">
                <button
                  type="button"
                  class="secondary preset-btn"
                  :class="{ active: activePreset === 'all' }"
                  :aria-pressed="activePreset === 'all'"
                  @click="toggleScopePreset('all')"
                >
                  <Check v-if="activePreset === 'all'" :size="13" class="preset-check" />
                  <span>All Remaining</span>
                </button>
                <button
                  type="button"
                  class="secondary preset-btn"
                  :class="{ active: activePreset === 'failed' }"
                  :aria-pressed="activePreset === 'failed'"
                  @click="toggleScopePreset('failed')"
                >
                  <Check v-if="activePreset === 'failed'" :size="13" class="preset-check" />
                  <span>Failed Only</span>
                </button>
              </div>
            </div>

            <div class="scope-inputs-row">
              <div class="scope-field">
                <label>Start Chapter</label>
                <input
                  v-model.number="start"
                  type="number"
                  min="0"
                  placeholder="0 (first)"
                />
                <span class="field-hint">0 = from beginning</span>
              </div>

              <div class="scope-field">
                <label>End Chapter</label>
                <input
                  v-model.number="end"
                  type="number"
                  min="0"
                  placeholder="0 (last)"
                />
                <span class="field-hint">0 = to the end</span>
              </div>

              <div class="scope-field">
                <label>Limit Count</label>
                <input
                  v-model.number="limit"
                  type="number"
                  min="0"
                  placeholder="0 (unlimited)"
                />
                <span class="field-hint">0 = process all in range</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Advanced Options (Collapsible) -->
        <div class="card-panel advanced-panel">
          <button
            type="button"
            class="advanced-toggle"
            @click="advancedOpen = !advancedOpen"
          >
            <div class="advanced-toggle-title">
              <Sliders :size="16" />
              <span>Advanced Pipeline Options</span>
            </div>
            <ChevronUp v-if="advancedOpen" :size="16" />
            <ChevronDown v-else :size="16" />
          </button>

          <div v-show="advancedOpen" class="advanced-body">
            <div class="options-grid">
              <label class="check">
                <input v-model="resume" type="checkbox" />
                <span>Skip chapters that already have translations (Resume)</span>
              </label>

              <label class="check">
                <input v-model="failedOnly" type="checkbox" />
                <span>Only re-translate chapters with failed status</span>
              </label>

              <label class="check">
                <input v-model="force" type="checkbox" />
                <span>Force re-translate all targeted chapters (Overwrite)</span>
              </label>

              <label class="check">
                <input v-model="review" type="checkbox" />
                <span>Run translation review validation</span>
              </label>

              <label class="check">
                <input v-model="summary" type="checkbox" />
                <span>Generate chapter summaries</span>
              </label>

              <label class="check">
                <input v-model="translateMetadata" type="checkbox" />
                <span>Translate novel title and synopsis metadata</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <!-- Action & Summary Sidebar Column -->
      <div class="action-column">
        <div class="card-panel summary-blueprint-card">
          <h3 class="blueprint-title">Job Blueprint</h3>
          <p class="blueprint-subtitle">Verify your configuration before starting.</p>

          <div class="blueprint-details">
            <div class="blueprint-item">
              <span class="bp-label">Novel</span>
              <span class="bp-val" :title="selectedNovelObj?.title || novel || 'None'">
                {{ selectedNovelObj?.title || novel || 'None selected' }}
              </span>
            </div>

            <div class="blueprint-item">
              <span class="bp-label">Language</span>
              <span class="bp-val">
                {{ formatLanguage(source, 'Auto') }} &rarr; {{ formatLanguage(target, 'Vietnamese') }}
              </span>
            </div>

            <div class="blueprint-item">
              <span class="bp-label">Engine</span>
              <span class="bp-val">
                {{ provider || 'System Default' }}
              </span>
            </div>

            <div class="blueprint-item">
              <span class="bp-label">Scope</span>
              <span class="bp-val">
                {{ failedOnly ? 'Failed chapters only' : (start || end || limit ? `Range: ${start || 1}–${end || 'end'} (limit: ${limit || 'none'})` : (resume ? 'All remaining' : 'All scheduled')) }}
              </span>
            </div>

            <div class="blueprint-item">
              <span class="bp-label">Mode</span>
              <span class="bp-val">
                {{ force ? 'Force overwrite' : (resume ? 'Skip existing (Resume)' : 'Standard') }}
              </span>
            </div>

            <div class="blueprint-item">
              <span class="bp-label">Review</span>
              <span class="bp-val" :class="{ 'bp-val-highlight': review }">
                {{ review ? 'Enabled' : 'Disabled' }}
              </span>
            </div>

            <div class="blueprint-item">
              <span class="bp-label">Summary</span>
              <span class="bp-val" :class="{ 'bp-val-highlight': summary }">
                {{ summary ? 'Enabled' : 'Disabled' }}
              </span>
            </div>
          </div>

          <button
            type="button"
            class="launch-btn"
            :disabled="!novel"
            @click="startTranslation"
          >
            <Play :size="16" />
            <span>Launch Translation Job</span>
          </button>
        </div>

        <!-- Live Job Monitor if launched -->
        <div v-if="jobId" class="card-panel active-job-card">
          <div class="job-card-header">
            <div class="live-dot" />
            <h4 class="job-card-title">Live Job Progress</h4>
          </div>
          <JobMonitor :job-id="jobId" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.translate-studio-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.studio-header {
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

.studio-title {
  margin: 0;
  font-size: 1.45rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--fg-primary);
  line-height: 1.2;
}

.studio-subtitle {
  margin: 0.2rem 0 0;
  font-size: 0.875rem;
  color: var(--fg-secondary);
}

.alert-error {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--danger-subtle);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: var(--danger);
}

.studio-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(0, 1fr);
  gap: 1.5rem;
  align-items: start;
}

.config-column {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* Step Card */
.step-card {
  display: flex;
  gap: 1.25rem;
  padding: 1.35rem 1.5rem;
}

.step-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
  color: var(--accent);
  font-weight: 700;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.step-content {
  flex: 1;
  min-width: 0;
}

.step-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--fg-primary);
}

.step-desc {
  margin: 0.2rem 0 1rem;
  font-size: 0.85rem;
  color: var(--fg-secondary);
}

.grid-2-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

/* Novel Mini Preview */
.novel-mini-preview {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md);
  background: var(--bg-surface-elevated);
  border: 1px solid var(--border-base);
}

.mini-cover {
  width: 44px;
  height: 60px;
  object-fit: cover;
  border-radius: var(--radius-xs);
  border: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.mini-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
}

.mini-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--fg-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini-author {
  font-size: 0.8rem;
  color: var(--fg-secondary);
}

.mini-progress-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.2rem;
}

.mini-stat {
  font-size: 0.8rem;
  color: var(--fg-muted);
}

.step-header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.preset-buttons {
  display: flex;
  gap: 0.4rem;
}

.preset-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.775rem;
  padding: 0.35rem 0.65rem;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.preset-btn:hover:not(:disabled):not(.active) {
  border-color: var(--accent);
  color: var(--accent);
}

.preset-btn.active {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(79, 125, 249, 0.35);
}

.preset-check {
  stroke-width: 2.5;
}

.scope-inputs-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.scope-field {
  display: flex;
  flex-direction: column;
}

.field-hint {
  font-size: 0.725rem;
  color: var(--fg-muted);
  margin-top: 0.25rem;
}

/* Advanced Options */
.advanced-panel {
  padding: 0;
  overflow: hidden;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 1.1rem 1.5rem;
  background: transparent;
  color: var(--fg-primary);
  border: none;
  border-radius: 0;
  cursor: pointer;
  box-shadow: none;
  font-size: 0.95rem;
}

.advanced-toggle:hover {
  background: var(--bg-surface-elevated);
  transform: none;
}

.advanced-toggle-title {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  font-weight: 600;
}

.advanced-body {
  padding: 1rem 1.5rem 1.5rem;
  border-top: 1px solid var(--border-base);
  background: var(--bg-surface-elevated);
}

.options-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0.75rem;
}

/* Action & Blueprint Column */
.action-column {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  position: sticky;
  top: 4.5rem;
  align-self: start;
  max-height: calc(100vh - 5.5rem);
  overflow-y: auto;
}

.summary-blueprint-card {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  background: linear-gradient(180deg, var(--bg-surface) 0%, var(--bg-surface-elevated) 100%);
  border: 1px solid var(--border-base);
}

.blueprint-title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--fg-primary);
}

.blueprint-subtitle {
  margin: -0.75rem 0 0;
  font-size: 0.825rem;
  color: var(--fg-secondary);
}

.blueprint-details {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-md);
}

.blueprint-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.bp-label {
  color: var(--fg-muted);
  font-weight: 500;
}

.bp-val {
  color: var(--fg-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 14rem;
  text-align: right;
}

.bp-val-highlight {
  color: var(--accent);
  font-weight: 700;
}

.launch-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.85rem 1.25rem;
  font-size: 0.95rem;
  font-weight: 700;
  border-radius: var(--radius-md);
  box-shadow: 0 4px 18px -2px var(--accent-glow);
}

.launch-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 22px -1px var(--accent-glow);
}

.active-job-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.job-card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
  animation: pulse 1.5s infinite;
}

.job-card-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--fg-primary);
}

@media (max-width: 900px) {
  .studio-layout {
    grid-template-columns: 1fr;
  }

  .action-column {
    position: static;
    max-height: none;
    overflow-y: visible;
  }
}
</style>
