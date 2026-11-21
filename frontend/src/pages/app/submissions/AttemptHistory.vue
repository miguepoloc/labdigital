<script setup lang="ts">
/** Historial de intentos de una entrega: fecha, versión, archivos, revisiones, nota y comentarios. */
import { computed } from 'vue'
import type { GradeScale } from '@/api/courses'
import type { Submission } from '@/api/submissions'
import LdBadge from '@/components/LdBadge.vue'
import { t } from '@/i18n'
import { formatBogota } from '@/lib/bogota'
import { formatGrade } from '../labs/labRules'
import SubmissionFiles from './SubmissionFiles.vue'
import SubmissionStatusBadge from './SubmissionStatusBadge.vue'

const props = withDefaults(
  defineProps<{
    submissions: Submission[]
    scale: GradeScale
    /** Enlace a la página de la entrega en cada intento. */
    links?: boolean
    /** Id del intento que se está viendo (se resalta). */
    currentId?: string | null
  }>(),
  { links: true, currentId: null },
)

const sorted = computed(() => [...props.submissions].sort((a, b) => b.attempt - a.attempt))
</script>

<template>
  <ol class="ld-history" data-test="attempt-history">
    <li
      v-for="s in sorted"
      :key="s.id"
      class="ld-history__item"
      :class="{ 'is-current': s.id === currentId }"
      data-test="attempt"
    >
      <header class="ld-history__head">
        <h3 class="ld-history__title">
          <RouterLink v-if="links" :to="{ name: 'submission', params: { id: s.id } }">
            {{ t('subs.attempt', { n: s.attempt }) }}
          </RouterLink>
          <template v-else>{{ t('subs.attempt', { n: s.attempt }) }}</template>
        </h3>
        <SubmissionStatusBadge :submission="s" />
        <LdBadge v-if="s.grade !== null" tone="success">
          {{ t('subs.grade', { grade: formatGrade(s.grade, scale) }) }}
        </LdBadge>
      </header>
      <p class="ld-muted ld-history__meta">
        <span>
          {{ t('subs.submittedAt', { date: formatBogota(s.submitted_at) }) }}
          <template v-if="s.is_late">({{ t('subs.late') }})</template>
        </span>
        <span>{{ t('subs.version', { v: s.version_n, project: s.project_name }) }}</span>
      </p>
      <SubmissionFiles :files="s.files" />
      <div class="ld-history__reviews">
        <p v-if="s.reviews.length === 0" class="ld-muted">{{ t('subs.noReviews') }}</p>
        <article v-for="r in s.reviews" :key="r.id" class="ld-history__review" data-test="review">
          <p class="ld-muted ld-history__review-meta">
            {{ t('subs.reviewBy', { name: r.reviewer_name, date: formatBogota(r.created_at) }) }}
            <LdBadge v-if="r.returned_for_resubmission" tone="danger">{{
              t('subs.returned')
            }}</LdBadge>
            <LdBadge v-if="r.grade !== null" tone="success">
              {{ t('subs.grade', { grade: formatGrade(r.grade, scale) }) }}
            </LdBadge>
          </p>
          <p v-if="r.comment" class="ld-history__comment">{{ r.comment }}</p>
        </article>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.ld-history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
}

.ld-history__item {
  padding: var(--ld-space-4);
  border: 1px solid var(--ld-color-border);
  border-left: 4px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  background: var(--ld-color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
}

.ld-history__item.is-current {
  border-left-color: var(--ld-color-primary);
}

.ld-history__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
}

.ld-history__title {
  margin: 0;
  font-size: var(--ld-text-md);
}

.ld-history__meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-1) var(--ld-space-4);
  font-size: var(--ld-text-sm);
}

.ld-history__reviews {
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
}

.ld-history__reviews > p {
  margin: 0;
  font-size: var(--ld-text-sm);
}

.ld-history__review {
  padding: var(--ld-space-2) var(--ld-space-3);
  border-radius: var(--ld-radius-sm);
  background: var(--ld-color-surface-2);
}

.ld-history__review-meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
  font-size: var(--ld-text-sm);
}

.ld-history__comment {
  margin: var(--ld-space-1) 0 0;
  white-space: pre-wrap;
}
</style>
