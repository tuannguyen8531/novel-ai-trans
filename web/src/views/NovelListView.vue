<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { useNovelsStore } from '@/stores/novels'
import { useSettingsStore } from '@/stores/settings'
import type { NovelSummary, NovelTargetProgress } from '@/api/types'

const novels = useNovelsStore()
const settings = useSettingsStore()
const deletingNovel = ref<string | null>(null)
const deleteError = ref<string | null>(null)

onMounted(() => {
  void Promise.all([novels.refresh(), settings.refresh()])
})

const totalNovels = computed(() => novels.novels.length)
const defaultTarget = computed(() => settings.settings?.target_language ?? 'vi')

function translatedProgress(novel: NovelSummary): NovelTargetProgress | undefined {
  return novel.targets.find((progress) => progress.target === defaultTarget.value)
}

async function deleteNovel(novel: NovelSummary) {
  const label = novel.title ? `"${novel.title}" (${novel.name})` : `"${novel.name}"`
  if (!confirm(
    `Delete ${label}?\n\nThis permanently removes all chapters, translations, glossary data, illustrations, and artifacts. This cannot be undone.`
  )) return

  deletingNovel.value = novel.name
  deleteError.value = null
  try {
    await novels.remove(novel.name)
  } catch (err) {
    deleteError.value = (err as Error).message
  } finally {
    deletingNovel.value = null
  }
}
</script>

<template>
  <section>
    <div v-if="deleteError" class="error delete-error">{{ deleteError }}</div>
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
            <th>Total</th>
            <th>Translated</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="novel in novels.novels" :key="novel.name">
            <td><code>{{ novel.name }}</code></td>
            <td>{{ novel.title ?? '—' }}</td>
            <td>{{ novel.author?.trim() || '—' }}</td>
            <td>{{ novel.total_input_chapters }}</td>
            <td>
              {{ translatedProgress(novel)?.completed ?? 0 }} / {{ translatedProgress(novel)?.total ?? novel.total_input_chapters }}
              <span v-if="(translatedProgress(novel)?.failed ?? 0) > 0" class="badge danger">
                {{ translatedProgress(novel)?.failed }} failed
              </span>
            </td>
            <td class="novel-actions">
              <div class="novel-actions-inner">
                <button
                  class="action-link delete-link"
                  type="button"
                  :disabled="deletingNovel !== null"
                  @click="deleteNovel(novel)"
                >
                  {{ deletingNovel === novel.name ? 'Deleting…' : 'Delete' }}
                </button>
                <RouterLink class="action-link" :to="`/novels/${novel.name}`">Open →</RouterLink>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin-top: 0.5rem;">{{ totalNovels }} novels in your library.</p>
  </section>
</template>

<style scoped>
.delete-error {
  margin-bottom: 0.75rem;
}

.novel-actions {
  text-align: right;
  vertical-align: middle;
  white-space: nowrap;
}

.novel-actions-inner {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
}

.action-link {
  padding: 0;
  background: transparent;
  color: var(--accent);
  border: 0;
  border-radius: 0;
}

.delete-link {
  color: var(--danger);
}

button.action-link:hover:not(:disabled) {
  background: transparent;
  text-decoration: underline;
}
</style>
