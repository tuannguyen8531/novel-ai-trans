<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { api } from '@/api/client'
import { useNovelsStore } from '@/stores/novels'
import JobMonitor from '@/components/JobMonitor.vue'

const novels = useNovelsStore()

const novel = ref<string>('')
const target = ref<string>('vi')
const source = ref<string>('')
const provider = ref<string>('')
const start = ref<number>(0)
const end = ref<number>(0)
const limit = ref<number>(0)
const force = ref<boolean>(false)
const resume = ref<boolean>(false)
const failedOnly = ref<boolean>(false)
const review = ref<boolean>(false)
const summary = ref<boolean>(false)
const jobId = ref<string | null>(null)
const error = ref<string | null>(null)

onMounted(() => {
  novels.refresh()
})

const novelOptions = computed(() => novels.novels.map((n) => n.name))

async function startTranslation() {
  error.value = null
  if (!novel.value) {
    error.value = 'Choose a novel.'
    return
  }
  const payload: Record<string, unknown> = {
    novel: novel.value,
    target_language: target.value,
    start_chapter: start.value,
    end_chapter: end.value,
    limit: limit.value,
    force: force.value,
    resume: resume.value,
    failed_only: failedOnly.value,
    enable_review: review.value,
    enable_summary: summary.value
  }
  if (source.value) payload.source_language = source.value
  if (provider.value) payload.provider = provider.value
  try {
    const result = await api.startTranslate(payload)
    jobId.value = result.job_id
  } catch (err) {
    error.value = (err as Error).message
  }
}
</script>

<template>
  <section class="flex-col gap-3">
    <div class="card">
      <h2>Translate</h2>
      <p class="muted">Choose a novel, the target language, and translation options. Progress streams live while the job runs.</p>
      <div class="grid">
        <div>
          <label>Novel</label>
          <select v-model="novel">
            <option value="" disabled>— select —</option>
            <option v-for="name in novelOptions" :key="name" :value="name">{{ name }}</option>
          </select>
        </div>
        <div>
          <label>Target language</label>
          <select v-model="target">
            <option value="vi">Vietnamese (vi)</option>
            <option value="en">English (en)</option>
          </select>
        </div>
        <div>
          <label>Source language (optional)</label>
          <input v-model="source" placeholder="chinese / korean / japanese" />
        </div>
        <div>
          <label>Provider override (optional)</label>
          <select v-model="provider">
            <option value="">Use default</option>
            <option value="ollama">ollama</option>
            <option value="gemini">gemini</option>
            <option value="openrouter">openrouter</option>
          </select>
        </div>
        <div>
          <label>Chapter range</label>
          <div class="row gap-2">
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">Start</span>
              <input v-model.number="start" type="number" min="0" style="max-width: 6rem;" />
            </label>
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">End</span>
              <input v-model.number="end" type="number" min="0" style="max-width: 6rem;" />
            </label>
            <label class="row gap-1" style="flex: 0 0 auto;">
              <span class="muted">Limit</span>
              <input v-model.number="limit" type="number" min="0" style="max-width: 6rem;" />
            </label>
          </div>
        </div>
        <div>
          <label>Options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="force" type="checkbox" />
              <span>Force re-translate</span>
            </label>
            <label class="check">
              <input v-model="resume" type="checkbox" />
              <span>Skip completed chapters</span>
            </label>
            <label class="check">
              <input v-model="failedOnly" type="checkbox" />
              <span>Re-run failed only</span>
            </label>
            <label class="check">
              <input v-model="review" type="checkbox" />
              <span>Enable review</span>
            </label>
            <label class="check">
              <input v-model="summary" type="checkbox" />
              <span>Enable summary</span>
            </label>
          </div>
        </div>
      </div>
      <div class="row gap-2" style="margin-top: 1rem;">
        <button type="button" :disabled="!novel" @click="startTranslation">Start translation</button>
      </div>
      <p v-if="error" class="error" style="margin-top: 0.5rem;">{{ error }}</p>
    </div>
    <div v-if="jobId" class="card">
      <h3>Job</h3>
      <JobMonitor :job-id="jobId" />
    </div>
  </section>
</template>
