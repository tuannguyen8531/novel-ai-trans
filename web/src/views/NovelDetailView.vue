<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useJobsStore } from '@/composables/jobs'
import { useNovelsStore } from '@/composables/novels'
import { useSettingsStore } from '@/composables/settings'
import type { MetadataDisplay, TargetLanguage } from '@/composables/metadata'
import ArtifactPanel from '@/components/ArtifactPanel.vue'
import ChapterPanel from '@/components/ChapterPanel.vue'
import DetailPanelHeader from '@/components/DetailPanelHeader.vue'
import GlossaryEditor from '@/components/GlossaryEditor.vue'
import JobMonitor from '@/components/JobMonitor.vue'
import MetadataPanel from '@/components/MetadataPanel.vue'
import NovelHeader from '@/components/NovelHeader.vue'
import RulesPanel from '@/components/RulesPanel.vue'

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
const targetLanguageLabel = computed(() => (
  targetLanguage.value === 'vi' ? 'Vietnamese' : 'English'
))
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

watch(displayTitle, (title) => {
  document.title = `${title} — Novel AI Translation`
}, { immediate: true })

watch(metadataJobStatus, (status, previous) => {
  if (status === 'completed' && previous !== 'completed') {
    void metadataPanel.value?.load()
    void novels.load(novelName.value)
  }
})

onMounted(async () => {
  await Promise.all([novels.load(novelName.value), settings.refresh()])
  if (route.query.job) jobId.value = String(route.query.job)
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
</script>

<template>
  <section class="flex-col gap-3">
    <div v-if="novels.error" class="card error">{{ novels.error }}</div>
    <div v-else-if="novels.detail" class="flex-col gap-3">
      <NovelHeader
        :novel="novels.detail"
        :metadata="metadataDisplay"
        :target-language="targetLanguage"
        :translated-count="translatedChapterCount"
        @translate="router.push({ name: 'translate', query: { novel: novelName } })"
        @pack="packOpen = true"
        @metadata="metadataOpen = true"
      />

      <div v-if="jobId" class="card">
        <h3>Latest job</h3>
        <JobMonitor :job-id="jobId" />
      </div>

      <div class="detail-tabs-shell">
        <nav class="detail-tabs" aria-label="Novel details" role="tablist">
          <button
            id="chapters-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'chapters'"
            aria-controls="chapters-panel"
            @click="tab = 'chapters'"
          >Chapters</button>
          <button
            id="glossary-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'glossary'"
            aria-controls="glossary-panel"
            @click="tab = 'glossary'"
          >Glossary</button>
          <button
            id="artifacts-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'artifacts'"
            aria-controls="artifacts-panel"
            @click="tab = 'artifacts'"
          >Artifacts</button>
          <button
            id="rules-tab"
            type="button"
            class="detail-tab"
            role="tab"
            :aria-selected="tab === 'rules'"
            aria-controls="rules-panel"
            @click="tab = 'rules'"
          >Rules</button>
        </nav>

        <ChapterPanel
          :novel="novelName"
          :active="tab === 'chapters'"
          @open-chapter="openChapter"
        />

        <div
          v-if="tab === 'glossary'"
          id="glossary-panel"
          class="detail-tab-panel"
          role="tabpanel"
          aria-labelledby="glossary-tab"
        >
          <DetailPanelHeader title="Glossary" />
          <GlossaryEditor :novel="novelName" />
        </div>

        <ArtifactPanel
          v-model:pack-open="packOpen"
          :novel="novelName"
          :target-language="targetLanguage"
          :target-language-label="targetLanguageLabel"
          :active="tab === 'artifacts'"
          @job-started="startPackJob"
        />

        <RulesPanel :novel="novelName" :active="tab === 'rules'" />
      </div>
    </div>

    <MetadataPanel
      ref="metadataPanel"
      v-model:open="metadataOpen"
      :novel="novelName"
      :target-language="targetLanguage"
      :target-language-label="targetLanguageLabel"
      @display="metadataDisplay = $event"
      @job-started="startMetadataJob"
    />
  </section>
</template>

<style scoped>
.detail-tabs-shell {
  overflow: hidden;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.detail-tabs {
  display: flex;
  gap: 1.5rem;
  padding: 0 1rem;
  background: var(--bg-elev-2);
  border-bottom: 1px solid var(--border);
}

.detail-tab {
  position: relative;
  padding: 0.65rem 0.1rem 0.75rem;
  color: var(--fg-dim);
  font-weight: 600;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.detail-tab:hover:not(:disabled) {
  color: var(--fg);
  background: transparent;
}

.detail-tab[aria-selected='true'] {
  color: var(--accent);
}

.detail-tab[aria-selected='true']::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: var(--accent);
  content: '';
}

.detail-tab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}

.detail-tab-panel {
  padding: 1rem;
}
</style>
