<script setup lang="ts">
import type { Lab } from '@/api/courses'
import LdBadge from '@/components/LdBadge.vue'
import { t } from '@/i18n'
import { formatBogota } from '@/lib/bogota'
import SubmissionStatusBadge from '../submissions/SubmissionStatusBadge.vue'
import { deadlineState, describeScale, type DeadlineState } from './labRules'

defineProps<{ labs: Lab[]; teacher: boolean }>()

const stateTone: Record<DeadlineState, 'info' | 'success' | 'warning' | 'danger'> = {
  not_open: 'info',
  open: 'success',
  late: 'warning',
  closed: 'danger',
}

function mode(lab: Lab) {
  if (lab.team_mode === 'individual') return t('labs.individual')
  return lab.max_team_size ? t('labs.team', { n: lab.max_team_size }) : t('labs.teamNoMax')
}
</script>

<template>
  <ul class="ld-labs">
    <li v-for="lab in labs" :key="lab.id" data-test="lab-item">
      <article class="ld-labs__item">
        <div class="ld-labs__main">
          <h3 class="ld-labs__title">
            <RouterLink :to="{ name: 'lab', params: { id: lab.id } }">{{ lab.title }}</RouterLink>
          </h3>
          <p class="ld-muted ld-labs__meta">
            <span v-if="lab.due_at">
              {{ t('labs.due', { date: formatBogota(lab.due_at) }) }}
              <abbr :title="t('labs.tzNote')">COT</abbr>
            </span>
            <span v-else>{{ t('labs.noDue') }}</span>
            <span>{{ t(`labs.policy.${lab.deadline_policy}`) }}</span>
            <span>{{ mode(lab) }}</span>
            <span v-if="teacher">{{ describeScale(lab.grade_scale) }}</span>
          </p>
        </div>
        <div class="ld-labs__status">
          <LdBadge v-if="teacher && !lab.published_at" tone="neutral">{{
            t('labs.draft')
          }}</LdBadge>
          <LdBadge v-else :tone="stateTone[deadlineState(lab)]">
            {{ t(`labs.state.${deadlineState(lab)}`) }}
          </LdBadge>
          <template v-if="!teacher">
            <SubmissionStatusBadge v-if="lab.my_submission" :submission="lab.my_submission" />
            <LdBadge v-else tone="neutral">{{ t('labs.notSubmitted') }}</LdBadge>
          </template>
        </div>
      </article>
    </li>
  </ul>
</template>

<style scoped>
.ld-labs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
}

.ld-labs__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-3);
  padding: var(--ld-space-4) var(--ld-space-5);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
  background: var(--ld-color-surface);
}

.ld-labs__main {
  min-width: 0;
  flex: 1 1 20rem;
}

.ld-labs__title {
  margin: 0 0 var(--ld-space-1);
  font-size: var(--ld-text-md);
}

.ld-labs__title a {
  color: var(--ld-color-primary);
  text-decoration: none;
}

.ld-labs__title a:hover {
  text-decoration: underline;
}

.ld-labs__meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-1) var(--ld-space-4);
  font-size: var(--ld-text-sm);
}

.ld-labs__meta abbr {
  text-decoration: none;
}

.ld-labs__status {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2);
}
</style>
