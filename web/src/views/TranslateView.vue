<script setup lang="ts">
import JobMonitor from '@/components/JobMonitor.vue'
import { useTranslation } from '@/composables/translation'

const {
  novel, target, source, provider, start, end, limit, force, resume, failedOnly, review,
  summary, translateMetadata, jobId, error, novelOptions, remainingChapters,
  startTranslation
} = useTranslation()
</script>

<template>
  <section class="flex-col gap-3">
    <div class="card">
      <h2>Translate</h2>
      <p class="muted">Choose a novel, language, and translation options.</p>
      <div class="grid">
        <div>
          <label>Novel</label>
          <select v-model="novel">
            <option value="" disabled>— select —</option>
            <option v-for="item in novelOptions" :key="item.name" :value="item.name">
              {{ item.name }} — {{ remainingChapters(item) }} chapter{{ remainingChapters(item) === 1 ? '' : 's' }} remaining
            </option>
          </select>
        </div>
        <div class="language-row">
          <div>
            <label>Source language</label>
            <select v-model="source">
              <option value="">Auto detect</option>
              <option value="chinese">Chinese</option>
              <option value="japanese">Japanese</option>
              <option value="korean">Korean</option>
            </select>
          </div>
          <div>
            <label>Target language</label>
            <select v-model="target">
              <option value="vi">Vietnamese (vi)</option>
              <option value="en">English (en)</option>
            </select>
          </div>
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
          <div class="check-row translate-options">
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
            <label class="check">
              <input v-model="translateMetadata" type="checkbox" />
              <span>Translate title and summary</span>
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

<style scoped>
.language-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.translate-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.translate-options .check {
  min-width: 0;
}

@media (max-width: 760px) {
  .translate-options {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 520px) {
  .language-row,
  .translate-options {
    grid-template-columns: 1fr;
  }
}
</style>
