import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { api } from '@/api/client'
import type { GlossaryApplyResponse, GlossaryResponse } from '@/api/types'

export interface GlossaryEdge {
  from: string
  to: string
  relationship: string
  since: number | null
}

export interface GlossaryCharacter {
  translated_name?: string
  role?: string
  pronoun?: string
}

export type ConfirmAction = (
  title: string,
  message: string,
  options?: { confirmLabel?: string; danger?: boolean }
) => Promise<boolean>

export function useGlossary(
  novel: MaybeRefOrGetter<string>,
  askConfirm: ConfirmAction
) {
  const data = ref<GlossaryResponse | null>(null)
  const error = ref<string | null>(null)
  const actionMessage = ref<string | null>(null)
  const loading = ref(false)
  const previewLoading = ref(false)
  const previewData = ref<GlossaryApplyResponse | null>(null)
  const applyLoading = ref(false)
  const rollbackLoading = ref(false)

  const terms = computed<Record<string, string>>(() =>
    (data.value?.data.terms as Record<string, string> | undefined) ?? {}
  )

  const characters = computed<Record<string, GlossaryCharacter>>(() =>
    (data.value?.data.entities as Record<string, GlossaryCharacter> | undefined) ?? {}
  )

  const relationships = computed<GlossaryEdge[]>(() => {
    const raw = (data.value?.data.edges as unknown[] | undefined) ?? []
    const normalized: GlossaryEdge[] = []
    for (const entry of raw) {
      if (!Array.isArray(entry) || entry.length < 3) continue
      const [from, to, relationship, since] = entry
      if (typeof from !== 'string' || typeof to !== 'string' || typeof relationship !== 'string') {
        continue
      }
      normalized.push({
        from,
        to,
        relationship,
        since: typeof since === 'number' ? since : null
      })
    }
    return normalized
  })

  const pendingReplacements = computed<unknown[]>(() =>
    (data.value?.data._pending_replacements as unknown[] | undefined) ?? []
  )

  const unresolvedCount = computed(() =>
    previewData.value?.replacements.filter((replacement) =>
      ['ambiguous', 'conflict', 'missing_output'].includes(replacement.status)
    ).length ?? 0
  )

  async function load() {
    loading.value = true
    error.value = null
    try {
      data.value = await api.getGlossary(toValue(novel))
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function addTerm(original: string, translated: string): Promise<boolean> {
    try {
      data.value = await api.addTerm(toValue(novel), original, translated)
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function updateTerm(
    oldOriginal: string,
    original: string,
    translated: string
  ): Promise<boolean> {
    let overwrite = false
    if (oldOriginal !== original && terms.value[original]) {
      overwrite = await askConfirm(
        'Overwrite Term',
        `Term "${original}" already exists. Overwrite it?`,
        { confirmLabel: 'Overwrite', danger: true }
      )
      if (!overwrite) return false
    }

    error.value = null
    try {
      data.value = await api.updateTerm(toValue(novel), oldOriginal, {
        original,
        translated,
        overwrite
      })
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function removeTerm(original: string): Promise<boolean> {
    if (!await askConfirm(
      'Remove Term',
      `Remove term "${original}"?`,
      { confirmLabel: 'Remove', danger: true }
    )) return false
    try {
      data.value = await api.removeTerm(toValue(novel), original)
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function saveCharacter(
    original: string,
    translatedName: string,
    role: string,
    pronoun?: string
  ): Promise<boolean> {
    error.value = null
    try {
      data.value = await api.updateCharacter(toValue(novel), original, {
        translated_name: translatedName || undefined,
        role: role || undefined,
        pronoun
      })
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function removeCharacter(original: string): Promise<boolean> {
    if (!await askConfirm(
      'Remove Character',
      `Remove character "${original}"? This will also remove their relationships.`,
      { confirmLabel: 'Remove', danger: true }
    )) return false
    try {
      data.value = await api.removeCharacter(toValue(novel), original)
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function addRelationship(
    from: string,
    to: string,
    relationship: string,
    since: number | null
  ): Promise<boolean> {
    error.value = null
    try {
      data.value = await api.addRelationship(toValue(novel), {
        from_char: from,
        to_char: to,
        relationship,
        since: typeof since === 'number' ? since : undefined
      })
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function updateRelationship(
    from: string,
    to: string,
    relationship: string,
    since: number | null
  ): Promise<boolean> {
    error.value = null
    try {
      data.value = await api.addRelationship(toValue(novel), {
        from_char: from,
        to_char: to,
        relationship,
        since: typeof since === 'number' ? since : null
      })
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function removeRelationship(from: string, to: string): Promise<boolean> {
    if (!await askConfirm(
      'Remove Relationship',
      `Remove relationship between "${from}" and "${to}"?`,
      { confirmLabel: 'Remove', danger: true }
    )) return false
    try {
      data.value = await api.removeRelationship(toValue(novel), from, to)
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    }
  }

  async function dismissReplacements() {
    if (!await askConfirm(
      'Dismiss Pending Replacements',
      'Dismiss all pending glossary replacements? Glossary values and translated files will remain unchanged; only the pending-change notice will be cleared.',
      { confirmLabel: 'Dismiss' }
    )) return
    loading.value = true
    error.value = null
    actionMessage.value = null
    try {
      await api.dismissGlossary(toValue(novel))
      await load()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function previewReplacements(): Promise<boolean> {
    previewLoading.value = true
    previewData.value = null
    error.value = null
    actionMessage.value = null
    try {
      previewData.value = await api.applyGlossary(toValue(novel), { write: false })
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    } finally {
      previewLoading.value = false
    }
  }

  async function applyReplacements() {
    applyLoading.value = true
    error.value = null
    actionMessage.value = null
    try {
      previewData.value = await api.applyGlossary(toValue(novel), { write: true })
      await load()
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      applyLoading.value = false
    }
  }

  async function rollbackReplacements(): Promise<boolean> {
    const backupId = previewData.value?.backup_id
    if (!backupId || !await askConfirm(
      'Rollback Glossary',
      'Restore every translated chapter changed by this apply operation? Current glossary values will remain unchanged, and pending replacements will be restored.',
      { confirmLabel: 'Rollback' }
    )) return false

    rollbackLoading.value = true
    error.value = null
    actionMessage.value = null
    try {
      await api.rollbackGlossary(toValue(novel), backupId)
      await load()
      actionMessage.value = `Restored translated chapters from backup ${backupId}.`
      return true
    } catch (err) {
      error.value = (err as Error).message
      return false
    } finally {
      rollbackLoading.value = false
    }
  }

  return {
    data,
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
  }
}
