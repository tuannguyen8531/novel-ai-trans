<script setup lang="ts">
import ChapterContent from '@/components/ChapterContent.vue'

defineProps<{
  novel: string
  content: string
  loading: boolean
  viewLoading: boolean
}>()
</script>

<template>
  <div v-if="loading" class="chapter-loading muted">Loading…</div>
  <div v-else-if="viewLoading" class="chapter-loading muted">Loading translation…</div>
  <ChapterContent v-else :content="content" :novel="novel" />
</template>

<style scoped>
.chapter-loading {
  text-align: center;
  padding: 3rem 1rem;
}
</style>
