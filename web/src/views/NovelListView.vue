<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useNovelsStore } from '@/stores/novels'

const novels = useNovelsStore()

onMounted(() => {
  novels.refresh()
})

const totalNovels = computed(() => novels.novels.length)
</script>

<template>
  <section>
    <div v-if="novels.error" class="error">{{ novels.error }}</div>
    <div v-else-if="!novels.novels.length" class="card">
      <p class="muted">No novels yet. Crawl a site or import an EPUB to get started.</p>
    </div>
    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Title</th>
            <th>Author</th>
            <th>Input</th>
            <th>vi (done/total)</th>
            <th>en (done/total)</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="novel in novels.novels" :key="novel.name">
            <td><code>{{ novel.name }}</code></td>
            <td>{{ novel.title ?? '—' }}</td>
            <td>{{ novel.author ?? '—' }}</td>
            <td>{{ novel.total_input_chapters }}</td>
            <td v-for="t in novel.targets" :key="novel.name + t.target">
              {{ t.completed }} / {{ t.total }}
              <span v-if="t.failed > 0" class="badge danger">{{ t.failed }} failed</span>
            </td>
            <td>
              <RouterLink :to="`/novels/${novel.name}`">Open →</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin-top: 0.5rem;">{{ totalNovels }} novels in your library.</p>
  </section>
</template>
