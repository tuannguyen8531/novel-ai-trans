<script setup lang="ts">
import JobMonitor from '@/components/JobMonitor.vue'
import { useImporting } from '@/composables/importing'

const { novels, file, name, selectedNovel, keepExisting, jobId, error, onFileChange, onExistingNovelChange, upload } = useImporting()
</script>

<template>
  <section class="import-source flex-col gap-3">
    <div class="card">
      <div class="source-heading">
        <h2>Import EPUB</h2>
        <p class="muted">Upload an EPUB to import chapters and illustrations into a novel's input directory.</p>
      </div>
      <div class="grid import-grid">
        <div>
          <label>EPUB file</label>
          <input type="file" accept=".epub" @change="onFileChange" />
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
        <div class="import-full-row">
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
        <div class="import-full-row">
          <label>Output slug (optional)</label>
          <input v-model="name" placeholder="defaults to the EPUB filename" />
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

<style scoped>
.source-heading {
  margin-bottom: 1rem;
}

.source-heading h2 {
  margin: 0 0 0.35rem;
}

.source-heading p {
  margin: 0;
}

.import-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.import-full-row {
  grid-column: 1 / -1;
}

@media (max-width: 640px) {
  .import-grid {
    grid-template-columns: 1fr;
  }
}
</style>
