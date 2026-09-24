<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  BookOpen,
  BookMarked,
  Package,
  ScrollText,
  Activity,
  AlertCircle,
  AlertTriangle,
  RotateCw,
  Filter,
  CheckCheck
} from '@lucide/vue'
import { useJobsStore } from '@/composables/jobs'
import { useNovelsStore } from '@/composables/novels'
import { useSettingsStore } from '@/composables/settings'
import type { MetadataDisplay, TargetLanguage } from '@/composables/metadata'
import type { NovelTranslationProgress } from '@/api/types'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import ArtifactPanel from '@/components/ArtifactPanel.vue'
import ChapterPanel from '@/components/ChapterPanel.vue'
import DetailPanelHeader from '@/components/DetailPanelHeader.vue'
import GlossaryEditor from '@/components/GlossaryEditor.vue'
import JobMonitor from '@/components/JobMonitor.vue'
import MetadataPanel from '@/components/MetadataPanel.vue'
import NovelHeader from '@/components/NovelHeader.vue'
import RulesPanel from '@/components/RulesPanel.vue'
import { formatLanguage } from '@/language'

const props = defineProps<{ name: string }>()
const route = useRoute()
const router = useRouter()
const novels = useNovelsStore()
const settings = useSettingsStore()
const jobs = useJobsStore()
const tab = ref<'chapters' | 'glossary' | 'artifacts' | 'rules'>('chapters')
const jobId = ref<string | null>(null)
const metadataOpen = ref(false)
const packOpen = ref(false)
const metadataPanel = ref<InstanceType<typeof MetadataPanel> | null>(null)
const metadataDisplay = ref<MetadataDisplay>({
  exists: false,
  loadError: null,
  title: '',
  author: '',
  sourceLanguage: '',
  genres: [],
  summary: '',
  targetTitle: '',
  targetSummary: '',
  illustrationSrc: null,
  hasAny: false
})

const novelName = computed(() => props.name || String(route.params.name || ''))
const targetLanguage = computed<TargetLanguage>(() => (
  settings.settings?.target_language === 'en' ? 'en' : 'vi'
))
const targetLanguageLabel = computed(() => formatLanguage(targetLanguage.value))
const translatedChapterCount = computed(() => (
  novels.detail?.targets.find((progress) => progress.target === targetLanguage.value)?.completed ?? 0
))
const displayTitle = computed(() => (
  metadataDisplay.value.targetTitle.trim() ||
  metadataDisplay.value.title.trim() ||
  novels.detail?.title ||
  novelName.value
))
const metadataJobStatus = computed(() => (
  jobId.value ? jobs.findJob(jobId.value)?.status : null
))

const translationProgress = ref<NovelTranslationProgress | null>(null)
const currentFilter = ref<'all' | 'issues' | 'completed' | 'untranslated'>('all')

async function loadProgress() {
  if (!novelName.value) return
  try {
    translationProgress.value = await novels.progress(novelName.value, targetLanguage.value)
  } catch (err) {
    console.error('Failed to load novel progress:', err)
  }
}

const failedChapters = computed(() => translationProgress.value?.failed ?? [])
const warningChapters = computed(() => translationProgress.value?.warnings ?? [])
const totalIssues = computed(() => failedChapters.value.length + warningChapters.value.length)

function retranslateFailed() {
  void router.push({
    name: 'translate',
    query: { novel: novelName.value, failed_only: 'true' }
  })
}

function retranslateNovel() {
  void router.push({
    name: 'translate',
    query: { novel: novelName.value, force: 'true' }
  })
}

const showIgnoreDialog = ref(false)
const ignoringWarnings = ref(false)

async function confirmIgnoreWarnings() {
  if (!novelName.value) return
  ignoringWarnings.value = true
  try {
    await novels.ignoreWarnings(novelName.value, targetLanguage.value)
    showIgnoreDialog.value = false
    await loadProgress()
    await novels.load(novelName.value)
  } catch (err) {
    console.error('Failed to ignore warnings:', err)
  } finally {
    ignoringWarnings.value = false
  }
}

function showIssues() {
  tab.value = 'chapters'
  currentFilter.value = 'issues'
}

watch(displayTitle, (title) => {
  document.title = `${title} — Novel AI Translation`
}, { immediate: true })

watch(metadataJobStatus, (status, previous) => {
  if (status === 'completed' && previous !== 'completed') {
    void metadataPanel.value?.load()
    void novels.load(novelName.value)
    void loadProgress()
  }
})

watch([novelName, targetLanguage], () => {
  void loadProgress()
})

onMounted(async () => {
  await Promise.all([novels.load(novelName.value), settings.refresh()])
  await loadProgress()
  if (route.query.job) jobId.value = String(route.query.job)
  if (route.query.filter === 'issues') {
    tab.value = 'chapters'
    currentFilter.value = 'issues'
  }
})

function openChapter(chapter: number) {
  void router.push({
    name: 'chapter-reader',
    params: { name: novelName.value, chapter }
  })
}

function startMetadataJob(id: string) {
  jobId.value = id
}

function startPackJob(id: string) {
  jobId.value = id
  void router.replace({ query: { job: id } })
}

function startInsertJob(id: string) {
  jobId.value = id
  void router.replace({ query: { job: id } })
}
</script>

<template>
  <section class="novel-detail-root">
    <!-- Error banner -->
    <div v-if="novels.error" class="card-panel error-panel">
      <AlertCircle :size="18" />
      <span>{{ novels.error }}</span>
    </div>

    <!-- Main Novel Studio View -->
    <div v-else-if="novels.detail" class="detail-container">
      <!-- Top Novel Header Banner -->
      <NovelHeader
        :novel="novels.detail"
        :metadata="metadataDisplay"
        :target-language="targetLanguage"
        :translated-count="translatedChapterCount"
        @translate="router.push({ name: 'translate', query: { novel: novelName } })"
        @pack="packOpen = true"
        @metadata="metadataOpen = true"
      />

      <!-- Translation Quality Attention Banner -->
      <section v-if="totalIssues > 0" class="card-panel attention-banner">
        <div class="attention-banner-left">
          <div class="attention-icon-box">
            <AlertTriangle :size="24" />
          </div>
          <div class="attention-banner-info">
            <div class="attention-banner-heading">
              <h4 class="attention-banner-title">{{ $t("translation_attention_required") }}</h4>
            </div>
            <p class="attention-banner-desc">
              <span v-if="failedChapters.length > 0" class="desc-failed">
                {{ failedChapters.length === 1 ? $t('single_chapter_failed') : $t('chapters_failed_count', { count: failedChapters.length }) }}
              </span>
              <span v-if="warningChapters.length > 0" class="desc-warning">
                {{ warningChapters.length === 1 ? $t('single_chapter_warning') : $t('chapters_warning_count', { count: warningChapters.length }) }}
              </span>
            </p>
          </div>
        </div>

        <div class="attention-banner-actions">
          <button
            v-if="failedChapters.length > 0"
            type="button"
            class="danger banner-action-btn"
            @click="retranslateFailed"
          >
            <RotateCw :size="14" />
            <span>{{ $t("retranslate_failed", { count: failedChapters.length }) }}</span>
          </button>
          <button
            v-else
            type="button"
            class="secondary banner-action-btn"
            @click="retranslateNovel"
          >
            <RotateCw :size="14" />
            <span>{{ $t("retranslate") }}</span>
          </button>

          <button
            v-if="warningChapters.length > 0"
            type="button"
            class="secondary banner-action-btn"
            @click="showIgnoreDialog = true"
          >
            <CheckCheck :size="14" />
            <span>{{ $t("ignore_all_warnings") }}</span>
          </button>

          <button
            type="button"
            class="secondary banner-action-btn"
            :class="{ active: tab === 'chapters' && currentFilter === 'issues' }"
            @click="showIssues"
          >
            <Filter :size="14" />
            <span>{{ tab === 'chapters' && currentFilter === 'issues' ? $t('showing_problem_chapters') : $t('show_problem_chapters') }}</span>
          </button>
        </div>
      </section>

      <!-- Active / Recent Job Monitor Card -->
      <div v-if="jobId" class="card-panel job-card">
        <div class="job-card-header">
          <Activity :size="18" class="job-icon" />
          <h3>{{ $t("current_workspace_operation") }}</h3>
        </div>
        <JobMonitor :job-id="jobId" />
      </div>

      <!-- Detail Work Tabs Container -->
      <div class="detail-tabs-shell">
        <nav class="detail-tabs" :aria-label="$t('novel_details')" role="tablist">
          <button
            id="chapters-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'chapters'"
            aria-controls="chapters-panel"
            @click="tab = 'chapters'"
          >
            <BookOpen :size="16" />
            <span>{{ $t("chapters") }}</span>
            <span class="tab-badge">{{ novels.detail.total_input_chapters }}</span>
          </button>

          <button
            id="glossary-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'glossary'"
            aria-controls="glossary-panel"
            @click="tab = 'glossary'"
          >
            <BookMarked :size="16" />
            <span>{{ $t("glossary") }}</span>
            <span class="tab-badge">{{ novels.detail.glossary_terms + novels.detail.glossary_entities }}</span>
          </button>

          <button
            id="artifacts-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'artifacts'"
            aria-controls="artifacts-panel"
            @click="tab = 'artifacts'"
          >
            <Package :size="16" />
            <span>{{ $t("artifacts") }}</span>
            <span class="tab-badge">{{ novels.detail.artifacts?.length || 0 }}</span>
          </button>

          <button
            id="rules-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'rules'"
            aria-controls="rules-panel"
            @click="tab = 'rules'"
          >
            <ScrollText :size="16" />
            <span>{{ $t("rules") }}</span>
          </button>
        </nav>

        <!-- Chapter Tab Content -->
        <ChapterPanel
          :novel="novelName"
          :active="tab === 'chapters'"
          :translation-progress="translationProgress"
          :initial-filter="currentFilter"
          @update:filter="(f) => currentFilter = f"
          @open-chapter="openChapter"
          @job-started="startInsertJob"
          @ignore-warnings="showIgnoreDialog = true"
          @retranslate="failedChapters.length > 0 ? retranslateFailed() : retranslateNovel()"
        />

        <!-- Glossary Tab Content -->
        <div
          v-if="tab === 'glossary'"
          id="glossary-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="glossary-tab"
        >
          <DetailPanelHeader :title="$t('glossary_character_dictionary')" />
          <GlossaryEditor :novel="novelName" />
        </div>

        <!-- Artifacts Tab Content -->
        <ArtifactPanel
          v-model:pack-open="packOpen"
          :novel="novelName"
          :target-language="targetLanguage"
          :target-language-label="targetLanguageLabel"
          :active="tab === 'artifacts'"
          @job-started="startPackJob"
        />

        <!-- Rules Tab Content -->
        <RulesPanel :novel="novelName" :active="tab === 'rules'" />
      </div>
    </div>

    <!-- Metadata Modal / Drawer -->
    <MetadataPanel
      ref="metadataPanel"
      v-model:open="metadataOpen"
      :novel="novelName"
      :target-language="targetLanguage"
      :target-language-label="targetLanguageLabel"
      @display="metadataDisplay = $event"
      @job-started="startMetadataJob"
    />

    <!-- Confirm Ignore Warnings Dialog -->
    <ConfirmDialog
      :show="showIgnoreDialog"
      :title="$t('ignore_all_warnings')"
      :message="$t('confirm_ignore_quality_warnings', { count: warningChapters.length, title: displayTitle })"
      :confirm-label="$t('ignore_all_warnings')"
      :loading="ignoringWarnings"
      @confirm="confirmIgnoreWarnings"
      @cancel="showIgnoreDialog = false"
    />
  </section>
</template>

<style scoped>
.novel-detail-root {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.detail-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.error-panel {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--danger-subtle);
  border: 1px solid rgba(244, 63, 94, 0.3);
  color: var(--danger);
}

.job-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.job-card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.job-icon {
  color: var(--accent);
}

.job-card-header h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--fg-primary);
}

/* Tabs */
.detail-tabs-shell {
  background: var(--bg-surface);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-xl);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

.detail-tabs {
  display: flex;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--bg-surface-elevated);
  border-bottom: 1px solid var(--border-base);
  overflow-x: auto;
}

.detail-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1.15rem;
  color: var(--fg-secondary);
  font-size: 0.875rem;
  font-weight: 600;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  cursor: pointer;
  white-space: nowrap;
  transition: all var(--transition-fast);
}

.detail-tab:hover:not(:disabled) {
  color: var(--fg-primary);
  background: var(--bg-surface);
}

.detail-tab[aria-selected='true'] {
  color: var(--accent);
  background: var(--bg-surface);
  border-color: var(--border-base);
  box-shadow: var(--shadow-subtle);
}

.detail-tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.1rem 0.45rem;
  border-radius: var(--radius-pill);
  font-size: 0.725rem;
  font-weight: 600;
  background: var(--bg-surface-active);
  color: var(--fg-secondary);
}

.detail-tab[aria-selected='true'] .tab-badge {
  background: var(--accent-subtle);
  color: var(--accent);
}

.detail-tab-panel {
  padding: 1.5rem;
}

/* Translation Quality Attention Banner */
.attention-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 1.15rem 1.4rem;
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(244, 63, 94, 0.05) 100%);
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: var(--radius-xl);
  flex-wrap: wrap;
}

.attention-banner-left {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-width: 0;
  flex: 1;
}

.attention-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  border-radius: var(--radius-lg);
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #f59e0b;
  flex-shrink: 0;
}

.attention-banner-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
}

.attention-banner-heading {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.attention-banner-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--fg-primary);
}

.attention-banner-desc {
  margin: 0;
  font-size: 0.85rem;
  color: var(--fg-secondary);
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.attention-banner-desc strong {
  color: var(--fg-primary);
}

.desc-failed {
  color: var(--danger);
}

.desc-warning {
  color: #f59e0b;
}

.attention-banner-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.banner-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.85rem;
  font-size: 0.825rem;
  font-weight: 600;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.banner-action-btn.active {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
}
</style>
