<script setup lang="ts">
import { onMounted, onUnmounted, computed } from 'vue'
import { useNovelsStore } from '@/composables/novels'
import { useJobsStore } from '@/composables/jobs'
import JobMonitor from '@/components/JobMonitor.vue'

const novels = useNovelsStore()
const jobs = useJobsStore()

onMounted(() => {
  novels.refresh()
  jobs.refresh()
  jobs.startPolling()
})

onUnmounted(() => {
  jobs.stopPolling()
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

const activeJobs = computed(() => jobs.activeJobs)
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
        <RouterLink to="/translate"><button>Translate</button></RouterLink>
        <RouterLink to="/sources">
          <button class="secondary">Add source</button>
        </RouterLink>
      </div>
    </div>
    <div class="card">
      <h2>Active jobs</h2>
      <div v-if="activeJobs.length" class="active-jobs">
        <div v-for="job in activeJobs" :key="job.id" class="active-job-entry">
          <JobMonitor :job="job" :live="false" />
        </div>
      </div>
      <p v-else class="muted">No active job. Start one from the Translate or Sources page.</p>
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

.active-jobs {
  display: flex;
  flex-direction: column;
}

.active-job-entry + .active-job-entry {
  border-top: 1px solid var(--border);
  margin-top: 0.75rem;
  padding-top: 0.75rem;
}
</style>
