<script setup lang="ts">
/** Entregas de un lab (docente): tabla con estado, nota y filtros. */
import { computed, onMounted, ref, useId } from 'vue'
import type { Lab } from '@/api/courses'
import { submissionsApi, type Submission } from '@/api/submissions'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCheckbox from '@/components/LdCheckbox.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import { formatBogotaShort } from '@/lib/bogota'
import { courseErrorMessage } from '../courses/courseErrors'
import SubmissionStatusBadge from '../submissions/SubmissionStatusBadge.vue'
import { formatGrade, submissionBadge, type SubmissionBadge } from './labRules'

const props = defineProps<{ lab: Lab }>()
const uid = useId()

const subs = ref<Submission[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const statusFilter = ref<'' | SubmissionBadge>('')
const search = ref('')
const latestOnly = ref(true)

const FILTERS: SubmissionBadge[] = ['submitted', 'late', 'graded', 'returned']

function who(s: Submission) {
  return s.team?.name ?? s.submitted_by.full_name
}
function key(s: Submission) {
  return s.team ? `t:${s.team.id}` : `u:${s.submitted_by.id}`
}

const latest = computed(() => {
  const map = new Map<string, Submission>()
  for (const s of subs.value) {
    const prev = map.get(key(s))
    if (!prev || s.attempt > prev.attempt) map.set(key(s), s)
  }
  return new Set(map.values())
})

const rows = computed(() => {
  const q = search.value.trim().toLocaleLowerCase('es')
  return subs.value
    .filter((s) => !latestOnly.value || latest.value.has(s))
    .filter((s) => !statusFilter.value || submissionBadge(s) === statusFilter.value)
    .filter(
      (s) =>
        !q ||
        who(s).toLocaleLowerCase('es').includes(q) ||
        s.members.some((m) => m.full_name.toLocaleLowerCase('es').includes(q)),
    )
    .sort((a, b) => who(a).localeCompare(who(b), 'es') || b.attempt - a.attempt)
})

async function load() {
  loading.value = true
  error.value = null
  try {
    subs.value = await submissionsApi.listForLab(props.lab.id)
  } catch (e) {
    error.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="ld-stack" data-test="submissions-table">
    <LdSpinner v-if="loading" :label="t('common2.loading')" />
    <LdAlert v-else-if="error" variant="danger">
      {{ error }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{ t('common2.retry') }}</LdButton>
      </template>
    </LdAlert>
    <LdEmptyState
      v-else-if="subs.length === 0"
      :title="t('table.emptyTitle')"
      :body="t('table.emptyBody')"
    />
    <template v-else>
      <div class="ld-subs__filters">
        <div class="ld-field">
          <label class="ld-field__label" :for="`st-${uid}`">{{ t('table.filterStatus') }}</label>
          <select
            :id="`st-${uid}`"
            v-model="statusFilter"
            class="ld-field__input"
            data-test="filter-status"
          >
            <option value="">{{ t('table.filterAll') }}</option>
            <option v-for="f in FILTERS" :key="f" :value="f">{{ t(`subs.status.${f}`) }}</option>
          </select>
        </div>
        <LdTextField
          v-model="search"
          type="search"
          :label="t('table.filterSearch')"
          name="search"
          data-test="filter-search"
        />
        <LdCheckbox v-model="latestOnly" :label="t('table.latestOnly')" data-test="filter-latest" />
      </div>
      <p class="ld-muted ld-subs__count" aria-live="polite">
        {{ t('table.count', { n: rows.length, total: subs.length }) }}
      </p>
      <p v-if="rows.length === 0" class="ld-muted">{{ t('table.emptyFiltered') }}</p>
      <div v-else class="ld-subs__wrap">
        <table class="ld-subs">
          <caption class="ld-visually-hidden">
            {{
              t('table.title')
            }}
          </caption>
          <thead>
            <tr>
              <th scope="col">{{ t('table.who') }}</th>
              <th scope="col">{{ t('table.attempt') }}</th>
              <th scope="col">{{ t('table.date') }}</th>
              <th scope="col">{{ t('table.status') }}</th>
              <th scope="col">{{ t('table.grade') }}</th>
              <th scope="col">
                <span class="ld-visually-hidden">{{ t('table.actions') }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in rows" :key="s.id" data-test="submission-row">
              <td>
                <strong>{{ who(s) }}</strong>
                <span v-if="s.team" class="ld-muted ld-subs__members">
                  {{ s.members.map((m) => m.full_name).join(', ') }}
                </span>
              </td>
              <td>{{ s.attempt }}</td>
              <td>{{ formatBogotaShort(s.submitted_at) }}</td>
              <td><SubmissionStatusBadge :submission="s" /></td>
              <td>{{ formatGrade(s.grade, lab.grade_scale) }}</td>
              <td>
                <RouterLink
                  :to="{ name: 'submission', params: { id: s.id } }"
                  :aria-label="t('subs.viewLabel', { name: who(s), n: s.attempt })"
                >
                  {{ t('subs.view') }}
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ld-subs__filters {
  display: grid;
  gap: var(--ld-space-3);
  align-items: end;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 14rem), 1fr));
}

.ld-subs__count {
  margin: 0;
  font-size: var(--ld-text-sm);
}

.ld-subs__wrap {
  overflow-x: auto;
}

.ld-subs {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--ld-text-sm);
}

.ld-subs th,
.ld-subs td {
  text-align: left;
  vertical-align: top;
  padding: var(--ld-space-2) var(--ld-space-3);
  border-bottom: 1px solid var(--ld-color-border);
}

.ld-subs th {
  font-weight: 600;
  white-space: nowrap;
}

.ld-subs__members {
  display: block;
  font-size: var(--ld-text-xs);
}
</style>
