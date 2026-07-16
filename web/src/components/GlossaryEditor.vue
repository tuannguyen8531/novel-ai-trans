<script setup lang="ts">
import { onMounted, ref, toRef, watch } from 'vue'
import CharactersPanel from '@/components/CharactersPanel.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import RelationshipsPanel from '@/components/RelationshipsPanel.vue'
import ReplacementDialog from '@/components/ReplacementDialog.vue'
import ReplacementsPanel from '@/components/ReplacementsPanel.vue'
import TermsPanel from '@/components/TermsPanel.vue'
import { useGlossary, type ConfirmAction } from '@/composables/glossary'

const props = defineProps<{ novel: string }>()

const confirmDialog = ref<{
  show: boolean
  title: string
  message: string
  confirmLabel: string
  danger: boolean
  resolve: ((value: boolean) => void) | null
}>({
  show: false,
  title: '',
  message: '',
  confirmLabel: 'Confirm',
  danger: false,
  resolve: null
})

const askConfirm: ConfirmAction = (title, message, options = {}) =>
  new Promise((resolve) => {
    confirmDialog.value = {
      show: true,
      title,
      message,
      confirmLabel: options.confirmLabel ?? 'Confirm',
      danger: options.danger ?? false,
      resolve
    }
  })

const {
  error,
  actionMessage,
  loading,
  terms,
  characters,
  relationships,
  pendingReplacements,
  previewLoading,
  previewData,
  applyLoading,
  rollbackLoading,
  unresolvedCount,
  load,
  addTerm,
  updateTerm,
  removeTerm,
  saveCharacter,
  removeCharacter,
  addRelationship,
  updateRelationship,
  removeRelationship,
  dismissReplacements,
  previewReplacements,
  applyReplacements,
  rollbackReplacements
} = useGlossary(toRef(props, 'novel'), askConfirm)

const showReplacementDialog = ref(false)

onMounted(load)
watch(() => props.novel, load)

function resolveConfirmation(value: boolean) {
  confirmDialog.value.resolve?.(value)
  confirmDialog.value.show = false
  confirmDialog.value.resolve = null
}

async function openReplacementDialog() {
  showReplacementDialog.value = true
  if (!await previewReplacements()) showReplacementDialog.value = false
}
</script>

<template>
  <div class="glossary">
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="actionMessage" class="notice">{{ actionMessage }}</p>

    <ReplacementsPanel
      :pending-count="pendingReplacements.length"
      :loading="loading"
      @preview="openReplacementDialog"
      @dismiss="dismissReplacements"
    />

    <TermsPanel
      :terms="terms"
      :add-term="addTerm"
      :update-term="updateTerm"
      :remove-term="removeTerm"
    />
    <CharactersPanel
      :characters="characters"
      :save-character="saveCharacter"
      :remove-character="removeCharacter"
    />
    <RelationshipsPanel
      :relationships="relationships"
      :add-relationship="addRelationship"
      :update-relationship="updateRelationship"
      :remove-relationship="removeRelationship"
    />

    <ReplacementDialog
      v-model:open="showReplacementDialog"
      :error="error"
      :preview-loading="previewLoading"
      :preview-data="previewData"
      :apply-loading="applyLoading"
      :rollback-loading="rollbackLoading"
      :unresolved-count="unresolvedCount"
      :apply="applyReplacements"
      :rollback="rollbackReplacements"
    />

    <ConfirmDialog
      :show="confirmDialog.show"
      :title="confirmDialog.title"
      :message="confirmDialog.message"
      :confirm-label="confirmDialog.confirmLabel"
      :danger="confirmDialog.danger"
      @confirm="resolveConfirmation(true)"
      @cancel="resolveConfirmation(false)"
    />
  </div>
</template>

<style scoped>
.glossary {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.notice {
  color: var(--ok);
}
</style>
