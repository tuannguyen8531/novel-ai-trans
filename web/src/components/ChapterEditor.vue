<script setup lang="ts">
const content = defineModel<string>({ required: true })
</script>

<template>
  <textarea v-model="content" class="chapter-edit-area"></textarea>
</template>

<style scoped>
.chapter-edit-area {
  width: 100%;
  min-height: 60vh;
  box-sizing: border-box;
  font-family: inherit;
  font-size: 0.95rem;
  line-height: 1.7;
  resize: vertical;
  background: var(--bg-elev-2);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
}
</style>
