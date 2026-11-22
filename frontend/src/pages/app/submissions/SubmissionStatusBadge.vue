<script setup lang="ts">
import { computed } from 'vue'
import type { SubmissionStatus } from '@/api/courses'
import LdBadge from '@/components/LdBadge.vue'
import { t } from '@/i18n'
import { submissionBadge, type SubmissionBadge } from '../labs/labRules'

const props = defineProps<{ submission: { status: SubmissionStatus; is_late: boolean } }>()

const TONES: Record<SubmissionBadge, 'info' | 'success' | 'warning' | 'danger'> = {
  submitted: 'info',
  late: 'warning',
  graded: 'success',
  returned: 'danger',
}
const badge = computed(() => submissionBadge(props.submission))
</script>

<template>
  <LdBadge :tone="TONES[badge]" data-test="submission-badge">
    {{ t(`subs.status.${badge}`) }}
    <template v-if="badge !== 'late' && submission.is_late"> · {{ t('subs.late') }}</template>
  </LdBadge>
</template>
