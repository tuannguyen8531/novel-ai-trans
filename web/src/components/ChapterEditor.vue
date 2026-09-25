<script setup lang="ts">
const content = defineModel<string>({ required: true })
</script>

<template>
  <textarea v-model="content" class="chapter-edit-area" />
</template>

<style scoped>
.chapter-edit-area {
  width: 100%;
  min-height: 60vh;
  box-sizing: border-box;
  font-family: 'Lora', var(--font-serif);
  font-size: 20px;
  line-height: 1.65;
  resize: vertical;
  background: var(--bg-surface-elevated);
  color: var(--fg-primary);
  border: 1px solid var(--border-base);
  border-radius: var(--radius-lg);
  padding: 1.25rem;
}
</style>
