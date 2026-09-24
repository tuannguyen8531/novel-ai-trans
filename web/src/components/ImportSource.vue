<script setup lang="ts">
import { ref, computed } from 'vue'
import { UploadCloud, Upload, BookOpen, FileArchive, CheckCircle2, AlertCircle } from '@lucide/vue'
import JobMonitor from '@/components/JobMonitor.vue'
import CustomSelect from '@/components/common/CustomSelect.vue'
import { useImporting } from '@/composables/importing'
import { t } from '@/i18n'

const { novels, file, name, selectedNovel, keepExisting, jobId, error, onFileChange, onExistingNovelChange, upload } = useImporting()
const fileInputRef = ref<HTMLInputElement | null>(null)

const novelOptions = computed(() => [
  { value: '', label: t('choose_an_existing_novel') },
  ...novels.novels.map((novel) => ({
    value: novel.name,
    label: novel.title
      ? t('titled_chapter_count', { title: novel.title, name: novel.name, count: novel.total_input_chapters })
      : t('named_chapter_count', { name: novel.name, count: novel.total_input_chapters })
  }))
])

function triggerFileInput() {
  fileInputRef.value?.click()
}
</script>

<template>
  <section class="import-source flex-col gap-3">
    <div class="card">
      <div class="source-heading">
        <div class="flex items-center gap-2 mb-1">
          <BookOpen :size="20" class="text-indigo-400 shrink-0" />
          <h2 class="!m-0">{{ $t("import_epub") }}</h2>
        </div>
        <p class="muted">{{ $t("epub_import_instructions") }}</p>
      </div>

      <div class="grid import-grid">
        <div class="import-full-row">
          <label>{{ $t("epub_file") }}</label>
          <div
            class="mt-1 border-2 border-dashed border-zinc-700 hover:border-indigo-500/60 rounded-xl p-5 text-center cursor-pointer transition-colors bg-zinc-900/40 hover:bg-indigo-950/10 flex flex-col items-center justify-center gap-2"
            @click="triggerFileInput"
          >
            <input
              ref="fileInputRef"
              type="file"
              accept=".epub"
              class="hidden"
              @change="onFileChange"
            />
            <div v-if="file" class="flex items-center gap-3 text-left">
              <div class="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                <FileArchive :size="24" />
              </div>
              <div>
                <p class="font-medium text-zinc-100 text-sm m-0">{{ file.name }}</p>
                <p class="text-xs text-zinc-400 m-0">{{ (file.size / 1024 / 1024).toFixed(2) }} {{ $t("mb") }}</p>
              </div>
              <span class="ml-4 text-xs font-medium text-emerald-400 flex items-center gap-1">
                <CheckCircle2 :size="14" /> {{ $t("ready") }}
              </span>
            </div>
            <div v-else class="flex flex-col items-center gap-1.5 py-2">
              <UploadCloud :size="32" class="text-zinc-500" />
              <p class="text-sm font-medium text-zinc-300 m-0">{{ $t("click_to_select_epub_file") }}</p>
              <p class="text-xs text-zinc-500 m-0">{{ $t("epub_support_hint") }}</p>
            </div>
          </div>
        </div>

        <div>
          <label>{{ $t("options") }}</label>
          <div class="check-row mt-2">
            <label class="check">
              <input v-model="keepExisting" type="checkbox" />
              <span>{{ $t("keep_chapters_already_in_the_novel") }}</span>
            </label>
          </div>
        </div>

        <div class="import-full-row">
          <label>{{ $t("existing_novel_optional") }}</label>
          <CustomSelect
            v-model="selectedNovel"
            :options="novelOptions"
            :disabled="novels.loading"
            :placeholder="$t('choose_an_existing_novel')"
            @change="onExistingNovelChange"
          />
          <p v-if="novels.error" class="error">{{ novels.error }}</p>
          <p v-else class="muted">{{ $t("select_a_novel_to_import_into_it") }}</p>
        </div>

        <div class="import-full-row">
          <label>{{ $t("short_name_optional") }}</label>
          <input v-model="name" :placeholder="$t('uses_the_epub_filename_when_blank')" />
        </div>
      </div>

      <div class="row gap-2" style="margin-top: 1.25rem;">
        <button
          type="button"
          class="flex items-center gap-1.5"
          :disabled="!file"
          @click="upload"
        >
          <Upload :size="15" />
          {{ $t("upload_and_import") }}
        </button>
      </div>
      <p v-if="error" class="error flex items-center gap-1.5" style="margin-top: 0.5rem;">
        <AlertCircle :size="15" />
        {{ error }}
      </p>
    </div>

    <div v-if="jobId" class="card">
      <h3>{{ $t("job") }}</h3>
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
