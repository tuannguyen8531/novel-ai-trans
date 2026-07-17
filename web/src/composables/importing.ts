import { onMounted, ref, watch } from 'vue'
import { api } from '@/api/client'
import { useNovelsStore } from '@/composables/novels'

export function useImporting() {
  const novels = useNovelsStore()
  const file = ref<File | null>(null)
  const name = ref('')
  const selectedNovel = ref('')
  const keepExisting = ref(false)
  const jobId = ref<string | null>(null)
  const error = ref<string | null>(null)

  function slugFromFilename(filename: string): string {
    return filename.replace(/\.epub$/i, '').toLowerCase().replace(/[^a-z0-9._-]+/g, '-').replace(/-{2,}/g, '-').replace(/^[-._]+|[-._]+$/g, '')
  }

  function onFileChange(event: Event) {
    const target = event.target as HTMLInputElement
    file.value = target.files && target.files.length > 0 ? target.files[0] : null
    if (file.value && !name.value) name.value = slugFromFilename(file.value.name)
  }

  function onExistingNovelChange() {
    if (!selectedNovel.value) return
    name.value = selectedNovel.value
    keepExisting.value = true
  }

  async function upload() {
    error.value = null
    if (!file.value) {
      error.value = 'Choose an EPUB file first.'
      return
    }
    try {
      jobId.value = (await api.uploadImport(file.value, name.value || undefined, keepExisting.value)).job_id
    } catch (err) {
      error.value = (err as Error).message
    }
  }

  onMounted(() => novels.refresh())
  watch(name, (value) => {
    if (selectedNovel.value && value !== selectedNovel.value) selectedNovel.value = ''
  })

  return { novels, file, name, selectedNovel, keepExisting, jobId, error, onFileChange, onExistingNovelChange, upload }
}
