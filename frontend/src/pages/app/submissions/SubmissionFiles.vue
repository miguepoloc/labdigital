<script setup lang="ts">
import { fileUrl, type SubmissionFile } from '@/api/submissions'
import { t } from '@/i18n'
import { formatBytes } from './uploadRules'

defineProps<{ files: SubmissionFile[] }>()
</script>

<template>
  <p v-if="files.length === 0" class="ld-muted ld-files__empty">{{ t('subs.noFiles') }}</p>
  <ul v-else class="ld-files" data-test="submission-files">
    <li v-for="f in files" :key="f.id">
      <span class="ld-files__kind">{{ t(`subs.fileKind.${f.kind}`) }}</span>
      <a
        :href="fileUrl(f.id)"
        :download="f.name"
        :aria-label="t('subs.download', { name: f.name })"
        >{{ f.name }}</a
      >
      <span class="ld-muted">({{ formatBytes(f.size) }})</span>
    </li>
  </ul>
</template>

<style scoped>
.ld-files {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-1);
  font-size: var(--ld-text-sm);
}

.ld-files li {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2);
  align-items: baseline;
}

.ld-files__kind {
  min-width: 5.5rem;
  font-weight: 600;
}

.ld-files__empty {
  margin: 0;
  font-size: var(--ld-text-sm);
}
</style>
