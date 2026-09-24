<script setup lang="ts">
import { computed, onMounted, toRef, watch } from 'vue'
import { X } from '@lucide/vue'
import { useMetadata, type MetadataDisplay, type TargetLanguage } from '@/composables/metadata'
import { useBodyScrollLock } from '@/composables/scrolllock'
import CustomSelect from '@/components/common/CustomSelect.vue'
import { t } from '@/i18n'

const sourceLanguageOptions = computed(() => [
  { value: '', label: `(${t('auto_detect')})` },
  { value: 'korean', label: t('korean') },
  { value: 'japanese', label: t('japanese') },
  { value: 'chinese', label: t('chinese') }
])

const props = defineProps<{
  novel: string
  targetLanguage: TargetLanguage
  targetLanguageLabel: string
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  display: [value: MetadataDisplay]
  jobStarted: [jobId: string]
}>()

const {
  metadata,
  loading,
  loadError,
  error,
  saving,
  title,
  author,
  sourceUrl,
  illustrationUrl,
  summary,
  sourceLanguage,
  genres,
  availableGenres,
  genreLoading,
  genreLoadError,
  force,
  coverFile,
  setCoverFile,
  targetTitle,
  targetSummary,
  display,
  load,
  save,
  localize
} = useMetadata(
  toRef(props, 'novel'),
  toRef(props, 'targetLanguage')
)

watch(display, (value) => emit('display', value), { immediate: true })
useBodyScrollLock(() => props.open)

onMounted(load)

function close() {
  setCoverFile(null)
  emit('update:open', false)
}

function selectCover(event: Event) {
  const input = event.target as HTMLInputElement
  setCoverFile(input.files?.[0] ?? null)
}

function genreLabel(genre: string) {
  return genre
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

async function saveAndClose() {
  if (await save()) close()
}

async function saveAndLocalize() {
  if (!await save()) return
  close()
  const jobId = await localize()
  if (jobId) emit('jobStarted', jobId)
}

defineExpose({ load })
</script>

<template>
  <div v-if="open" class="modal-overlay">
    <div
      class="modal-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="metadata-title"
      tabindex="-1"
    >
      <header class="modal-header">
        <h3 id="metadata-title">{{ $t("edit_metadata") }}</h3>
        <button
          type="button"
          class="modal-close"
          :aria-label="$t('close')"
          @click="close"
        >
          <X :size="18" />
        </button>
      </header>
      <div class="modal-body">
        <p v-if="loading" class="muted">{{ $t("loading_metadata") }}</p>
        <p v-else-if="loadError" class="error">{{ $t("failed_to_load_metadata", { error: loadError }) }}</p>
        <p v-else-if="!metadata" class="muted">
          {{ $t("metadata_empty_instructions") }}
        </p>

        <div v-if="!loading" class="metadata-fields">
          <div>
            <label>{{ $t("original_title") }}</label>
            <input v-model="title" :placeholder="$t('original_title_placeholder')" />
          </div>
          <div>
            <label>{{ $t("author") }}</label>
            <input v-model="author" :placeholder="$t('author_name')" />
          </div>
          <div>
            <label>{{ $t("source_url") }}</label>
            <input v-model="sourceUrl" :placeholder="$t('url_placeholder')" />
          </div>
          <div>
            <label for="metadata-cover-file">{{ $t("upload_cover") }}</label>
            <input
              id="metadata-cover-file"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              @change="selectCover"
            />
            <p class="muted cover-help">{{ $t("cover_image_formats_hint") }}</p>
            <img v-if="display.illustrationSrc" class="cover-preview" :src="display.illustrationSrc" :alt="$t('cover_preview')" />
          </div>
          <div>
            <label>{{ $t("remote_cover_url") }}</label>
            <input
              v-model="illustrationUrl"
              :disabled="Boolean(coverFile)"
              :placeholder="$t('https_alternative_to_upload')"
            />
          </div>
          <div>
            <label>{{ $t("summary") }}</label>
            <textarea v-model="summary" class="metadata-summary-input" :placeholder="$t('novel_synopsis_optional')"></textarea>
          </div>
          <div>
            <label>{{ $t("source_language") }}</label>
            <CustomSelect
              v-model="sourceLanguage"
              :options="sourceLanguageOptions"
            />
          </div>
          <fieldset
            class="genre-fieldset"
            :disabled="!sourceLanguage || genreLoading || Boolean(genreLoadError)"
          >
            <legend>{{ $t("genres") }}</legend>
            <p v-if="!sourceLanguage" class="muted genre-help">
              {{ $t("select_source_for_genres") }}
            </p>
            <p v-else-if="genreLoading" class="muted genre-help">
              {{ $t("loading_genre_profiles") }}
            </p>
            <p v-else-if="genreLoadError" class="error genre-help">
              {{ $t("failed_to_load_genre_profiles", { error: genreLoadError }) }}
            </p>
            <p v-else-if="!availableGenres.length" class="muted genre-help">
              {{ $t("no_genre_profiles") }}
            </p>
            <div v-else class="genre-options">
              <label v-for="genre in availableGenres" :key="genre" class="check genre-option">
                <input v-model="genres" type="checkbox" :value="genre" />
                <span>{{ genreLabel(genre) }}</span>
              </label>
            </div>
          </fieldset>
          <div class="localization-fields">
            <div>
              <label>{{ $t("translated_title", { language: targetLanguageLabel }) }}</label>
              <input v-model="targetTitle" :placeholder="$t('localized_title', { language: targetLanguageLabel })" />
            </div>
            <div>
              <label>{{ $t("translated_summary", { language: targetLanguageLabel }) }}</label>
              <textarea
                v-model="targetSummary"
                class="metadata-summary-input"
                :placeholder="$t('localized_summary', { language: targetLanguageLabel })"
              ></textarea>
            </div>
            <label class="check">
              <input v-model="force" type="checkbox" />
              <span>{{ $t("regenerate_existing_ai_translations") }}</span>
            </label>
            <div class="row gap-2">
              <button class="secondary" type="button" :disabled="saving" @click="saveAndLocalize">
                {{ $t("save_and_translate_into", { language: targetLanguageLabel }) }}
              </button>
            </div>
          </div>
        </div>
        <p v-if="error" class="error operation-error">{{ error }}</p>
      </div>
      <footer class="modal-footer">
        <button class="secondary" type="button" :disabled="saving" @click="close">{{ $t("cancel") }}</button>
        <button class="secondary" type="button" :disabled="saving" @click="load">{{ $t("revert") }}</button>
        <button type="button" :disabled="saving" @click="saveAndClose">
          {{ saving ? $t('saving') : $t('save_metadata') }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped src="../assets/dialog.css"></style>
<style scoped>
.metadata-fields,
.localization-fields {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.localization-fields {
  margin-top: 0.25rem;
}

.metadata-fields input:not([type='checkbox']),
.metadata-fields select {
  width: 100%;
}

.metadata-summary-input {
  width: 100%;
  height: 10rem;
  resize: none;
}

.genre-fieldset {
  padding: 0.75rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.genre-fieldset legend {
  padding: 0 0.25rem;
}

.genre-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  gap: 0.5rem 1rem;
}

.genre-option {
  margin: 0;
}

.genre-help {
  margin: 0.45rem 0 0;
  font-size: 0.85rem;
}

.operation-error {
  margin-top: 0.5rem;
}

.cover-help {
  margin: 0.35rem 0 0;
  font-size: 0.85rem;
}

.cover-preview {
  display: block;
  width: min(10rem, 100%);
  max-height: 14rem;
  margin-top: 0.65rem;
  object-fit: contain;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
</style>
