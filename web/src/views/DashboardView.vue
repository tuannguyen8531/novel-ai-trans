<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useNovelsStore } from '@/stores/novels'
import { useJobsStore } from '@/stores/jobs'
import JobMonitor from '@/components/JobMonitor.vue'

const novels = useNovelsStore()
const jobs = useJobsStore()

onMounted(() => {
  novels.refresh()
  jobs.refresh()
})

const totalInput = computed(() =>
  novels.novels.reduce((sum, n) => sum + n.total_input_chapters, 0)
)
const totalTranslated = computed(() =>
  novels.novels.reduce(
    (sum, n) => sum + n.targets.reduce((s, t) => s + t.completed, 0),
    0
  )
)
</script>

<template>
  <section class="grid">
    <div class="card">
      <h2>Overview</h2>
      <p class="muted">Quick glance at your novel library and active jobs.</p>
      <div class="stats">
        <div class="stat">
          <span class="stat-value">{{ novels.novels.length }}</span>
          <span class="stat-label">Novels</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ totalInput }}</span>
          <span class="stat-label">Input chapters</span>
        </div>
        <div class="stat">
          <span class="stat-value">{{ totalTranslated }}</span>
          <span class="stat-label">Translated chapters</span>
        </div>
      </div>
      <div class="row gap-2" style="margin-top: 1rem;">
        <RouterLink to="/crawl"><button>Crawl new novel</button></RouterLink>
        <RouterLink to="/import"><button class="secondary">Import EPUB</button></RouterLink>
        <RouterLink to="/translate"><button class="secondary">Translate</button></RouterLink>
      </div>
    </div>
    <div class="card">
      <h2>Current job</h2>
      <JobMonitor v-if="jobs.current" :job="jobs.current" />
      <p v-else class="muted">No active job. Start one from the Crawl, Import, or Translate pages.</p>
    </div>
  </section>
</template>

<style scoped>
.stats {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.stat {
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 1.6rem;
  font-weight: 600;
  color: var(--accent);
}

.stat-label {
  font-size: 0.85rem;
  color: var(--fg-dim);
}
</style>
