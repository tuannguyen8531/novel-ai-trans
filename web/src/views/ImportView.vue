<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import JobMonitor from '@/components/JobMonitor.vue'
import { useNovelsStore } from '@/stores/novels'

const novels = useNovelsStore()
const file = ref<File | null>(null)
const name = ref<string>('')
const selectedNovel = ref<string>('')
const keepExisting = ref<boolean>(false)
const jobId = ref<string | null>(null)
const error = ref<string | null>(null)

onMounted(() => novels.refresh())

watch(name, (value) => {
  if (selectedNovel.value && value !== selectedNovel.value) {
    selectedNovel.value = ''
  }
})

function slugFromFilename(filename: string): string {
  return filename.replace(/\.epub$/i, '').toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/-{2,}/g, '-').replace(/^[-._]+|[-._]+$/g, '')
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files && target.files.length > 0 ? target.files[0] : null
  if (file.value && !name.value) {
    name.value = slugFromFilename(file.value.name)
  }
}

function onExistingNovelChange() {
  if (!selectedNovel.value) return
  name.value = selectedNovel.value
  keepExisting.value = true
}

async function upload() {
  error.value = null
  if (!file.value) {
    error.value = 'Choose an EPUB file first.'
    return
  }
  try {
    const result = await api.uploadImport(file.value, name.value || undefined, keepExisting.value)
    jobId.value = result.job_id
  } catch (err) {
    error.value = (err as Error).message
  }
}
</script>

<template>
  <section class="flex-col gap-3">
    <div class="card">
      <h2>Import EPUB</h2>
      <p class="muted">Upload an EPUB to import chapters and illustrations into a novel's input directory.</p>
      <div class="grid">
        <div>
          <label>EPUB file</label>
          <input type="file" accept=".epub" @change="onFileChange" />
        </div>
        <div>
          <label>Existing novel (optional)</label>
          <select v-model="selectedNovel" :disabled="novels.loading" @change="onExistingNovelChange">
            <option value="">— choose an existing novel —</option>
            <option v-for="novel in novels.novels" :key="novel.name" :value="novel.name">
              {{ novel.title ? `${novel.title} (${novel.name})` : novel.name }} · {{ novel.total_input_chapters }} chapters
            </option>
          </select>
          <p v-if="novels.error" class="error">{{ novels.error }}</p>
          <p v-else class="muted">Selecting a novel fills its slug and enables Keep existing.</p>
        </div>
        <div>
          <label>Output slug (optional)</label>
          <input v-model="name" placeholder="defaults to the EPUB filename" />
        </div>
        <div>
          <label>Options</label>
          <div class="check-row">
            <label class="check">
              <input v-model="keepExisting" type="checkbox" />
              <span>Keep existing chapters in the target input directory</span>
            </label>
          </div>
        </div>
      </div>
      <div class="row gap-2" style="margin-top: 1rem;">
        <button type="button" :disabled="!file" @click="upload">Upload and import</button>
      </div>
      <p v-if="error" class="error" style="margin-top: 0.5rem;">{{ error }}</p>
    </div>
    <div v-if="jobId" class="card">
      <h3>Job</h3>
      <JobMonitor :job-id="jobId" />
    </div>
  </section>
</template>
