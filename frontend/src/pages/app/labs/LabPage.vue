<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { coursesApi, labsApi, type Course, type Lab, type Team } from '@/api/courses'
import { submissionsApi, type Submission } from '@/api/submissions'
import LdAlert from '@/components/LdAlert.vue'
import LdBadge from '@/components/LdBadge.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdMarkdown from '@/components/LdMarkdown.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTabs, { type TabItem } from '@/components/LdTabs.vue'
import { config } from '@/config'
import { t } from '@/i18n'
import { formatBogota } from '@/lib/bogota'
import { useSessionStore } from '@/stores/session'
import ConfirmDialog from '../courses/ConfirmDialog.vue'
import { courseErrorMessage } from '../courses/courseErrors'
import AttemptHistory from '../submissions/AttemptHistory.vue'
import SubmitDialog from '../submissions/SubmitDialog.vue'
import { deadlineState, describeScale, type DeadlineState } from './labRules'
import SubmissionsTable from './SubmissionsTable.vue'
import TeamPanel from './TeamPanel.vue'
import TeamsAdmin from './TeamsAdmin.vue'

const route = useRoute()
const session = useSessionStore()
const labId = computed(() => String(route.params.id))

const lab = ref<Lab | null>(null)
const course = ref<Course | null>(null)
const history = ref<Submission[]>([])
const myTeam = ref<Team | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const submitting = ref(false)
const tab = ref('statement')
const confirmPublish = ref(false)
const publishing = ref(false)

/** Enlace al envoltorio FPGA de LD-8a (`/labdigital/app/fpga/`): recarga completa, sólo se enlaza. */
const simulatorUrl = `${config.basePath}app/fpga/`

const isTeacher = computed(() => course.value?.my_role === 'docente')
const state = computed<DeadlineState | null>(() => (lab.value ? deadlineState(lab.value) : null))
const lastAttempt = computed(() =>
  history.value.reduce<Submission | null>(
    (acc, s) => (!acc || s.attempt > acc.attempt ? s : acc),
    null,
  ),
)
const teacherTabs = computed<TabItem[]>(() => [
  { id: 'statement', label: t('labs.teacherTabs.statement') },
  { id: 'submissions', label: t('labs.teacherTabs.submissions') },
  ...(lab.value?.team_mode === 'team' ? [{ id: 'teams', label: t('labs.teacherTabs.teams') }] : []),
])

/** Motivo por el que no se puede entregar (null = se puede). */
const blockReason = computed<string | null>(() => {
  if (!lab.value) return null
  if (state.value === 'closed') return t('labs.closedTitle')
  if (state.value === 'not_open') return t('labs.notOpenTitle')
  if (lab.value.team_mode === 'team' && !myTeam.value) return t('labs.needTeam')
  const last = lastAttempt.value
  if (last && !lab.value.allow_resubmission && last.status !== 'returned')
    return t('labs.alreadySubmitted')
  return null
})

const modeText = computed(() => {
  if (!lab.value) return ''
  if (lab.value.team_mode === 'individual') return t('labs.individual')
  return lab.value.max_team_size
    ? t('labs.team', { n: lab.value.max_team_size })
    : t('labs.teamNoMax')
})

async function loadHistory() {
  if (!lab.value || isTeacher.value) return
  history.value = await submissionsApi.listForLab(lab.value.id)
}

async function load() {
  if (route.name !== 'lab') return // saliendo de la página
  loading.value = true
  loadError.value = null
  lab.value = null
  try {
    lab.value = await labsApi.get(labId.value)
    course.value = await coursesApi.get(lab.value.course_id)
    await loadHistory()
    if (route.query.guardado === '1') status.value = { kind: 'success', text: t('labEditor.saved') }
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function onSubmitted() {
  try {
    await loadHistory()
  } catch {
    /* el diálogo ya mostró el resultado */
  }
}

async function publish() {
  if (!lab.value) return
  publishing.value = true
  status.value = null
  try {
    lab.value = await labsApi.publish(lab.value.id)
    status.value = { kind: 'success', text: t('labs.publishedDone') }
  } catch (e) {
    status.value = { kind: 'danger', text: courseErrorMessage(e) }
  } finally {
    publishing.value = false
    confirmPublish.value = false
  }
}

watch(labId, load, { immediate: true })
</script>

<template>
  <div class="ld-stack ld-lab">
    <RouterLink
      v-if="course"
      :to="{ name: 'course', params: { id: course.id } }"
      class="ld-lab__back"
    >
      ← {{ t('labs.backToCourse') }}: {{ course.name }}
    </RouterLink>

    <LdSpinner v-if="loading" size="lg" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger" data-test="lab-error">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{ t('common2.retry') }}</LdButton>
      </template>
    </LdAlert>

    <template v-else-if="lab && course">
      <header class="ld-lab__head">
        <h1>{{ lab.title }}</h1>
        <div class="ld-row ld-lab__badges">
          <LdBadge v-if="!lab.published_at" tone="neutral">{{ t('labs.draft') }}</LdBadge>
          <LdBadge
            v-else-if="state"
            :tone="
              state === 'open'
                ? 'success'
                : state === 'closed'
                  ? 'danger'
                  : state === 'late'
                    ? 'warning'
                    : 'info'
            "
          >
            {{ t(`labs.state.${state}`) }}
          </LdBadge>
          <LdBadge>{{ modeText }}</LdBadge>
          <LdBadge>{{ t(`labs.policy.${lab.deadline_policy}`) }}</LdBadge>
        </div>
      </header>

      <LdAlert v-if="status" :variant="status.kind" data-test="lab-status">{{
        status.text
      }}</LdAlert>

      <LdCard :title="t('labs.details')" :heading-level="2">
        <dl class="ld-lab__dl">
          <template v-if="lab.opens_at">
            <dt>{{ t('labEditor.opensAt') }}</dt>
            <dd>{{ formatBogota(lab.opens_at) }} ({{ t('labs.tzNote') }})</dd>
          </template>
          <dt>{{ t('labEditor.dueAt') }}</dt>
          <dd data-test="lab-due">
            <template v-if="lab.due_at">
              {{ formatBogota(lab.due_at) }} ({{ t('labs.tzNote') }})
            </template>
            <template v-else>{{ t('labs.noDue') }}</template>
          </dd>
          <dt>{{ t('labEditor.policy') }}</dt>
          <dd>{{ t(`labs.policyHelp.${lab.deadline_policy}`) }}</dd>
          <dt>{{ t('labs.scale') }}</dt>
          <dd>{{ describeScale(lab.grade_scale) }}</dd>
          <dt>{{ t('labs.resubmission') }}</dt>
          <dd>
            {{ lab.allow_resubmission ? t('labs.resubmissionYes') : t('labs.resubmissionNo') }}
          </dd>
        </dl>
      </LdCard>

      <!-- ===== Estudiante ===== -->
      <template v-if="!isTeacher">
        <LdAlert
          v-if="state === 'closed'"
          variant="danger"
          :title="t('labs.closedTitle')"
          data-test="lab-closed"
        >
          {{ t('labs.closedBody', { date: formatBogota(lab.due_at) }) }}
        </LdAlert>
        <LdAlert v-else-if="state === 'late'" variant="warning" :title="t('labs.lateTitle')">
          {{ t('labs.lateBody') }}
        </LdAlert>
        <LdAlert v-else-if="state === 'not_open'" variant="info" :title="t('labs.notOpenTitle')">
          {{ t('labs.notOpenBody', { date: formatBogota(lab.opens_at) }) }}
        </LdAlert>
        <LdAlert v-if="lastAttempt?.status === 'returned' && state !== 'closed'" variant="info">
          {{ t('labs.returnedNotice') }}
        </LdAlert>

        <section class="ld-stack">
          <h2>{{ t('labs.statement') }}</h2>
          <LdMarkdown
            v-if="lab.statement_md.trim()"
            :source="lab.statement_md"
            data-test="statement"
          />
          <p v-else class="ld-muted">{{ t('labs.statementEmpty') }}</p>
        </section>

        <TeamPanel
          v-if="lab.team_mode === 'team' && session.me"
          :lab="lab"
          :user-id="session.me.id"
          @change="myTeam = $event"
        />

        <div class="ld-lab__actions">
          <LdButton variant="secondary" :href="simulatorUrl" data-test="open-simulator">
            {{ t('labs.workInSimulator') }}
          </LdButton>
          <LdButton
            variant="accent"
            :disabled="!!blockReason"
            :aria-describedby="blockReason ? 'lab-block-reason' : undefined"
            data-test="open-submit"
            @click="submitting = true"
          >
            {{ t('labs.submit') }}
          </LdButton>
          <p v-if="blockReason" id="lab-block-reason" class="ld-muted" data-test="block-reason">
            {{ blockReason }}
          </p>
        </div>

        <section class="ld-stack">
          <h2>{{ t('labs.historyTitle') }}</h2>
          <LdEmptyState v-if="history.length === 0" :title="t('labs.historyEmpty')" />
          <AttemptHistory v-else :submissions="history" :scale="lab.grade_scale" />
        </section>

        <SubmitDialog
          v-if="submitting"
          :lab="lab"
          @close="submitting = false"
          @submitted="onSubmitted"
        />
      </template>

      <!-- ===== Docente ===== -->
      <template v-else>
        <LdAlert v-if="!lab.published_at" variant="info" data-test="draft-notice">
          {{ t('labs.draftNotice') }}
        </LdAlert>
        <div class="ld-lab__actions">
          <LdButton
            variant="secondary"
            :to="{ name: 'lab-edit', params: { id: lab.id } }"
            data-test="edit-lab"
          >
            {{ t('labs.edit') }}
          </LdButton>
          <LdButton
            v-if="!lab.published_at"
            variant="accent"
            :loading="publishing"
            data-test="publish-lab"
            @click="confirmPublish = true"
          >
            {{ t('labs.publish') }}
          </LdButton>
        </div>
        <LdTabs
          v-model="tab"
          :tabs="teacherTabs"
          :label="t('labs.teacherTabs.label')"
          data-test="lab-teacher"
        >
          <template #default="{ active }">
            <section v-if="active === 'statement'">
              <LdMarkdown v-if="lab.statement_md.trim()" :source="lab.statement_md" />
              <p v-else class="ld-muted">{{ t('labs.statementEmpty') }}</p>
            </section>
            <SubmissionsTable v-else-if="active === 'submissions'" :lab="lab" />
            <TeamsAdmin v-else-if="active === 'teams'" :lab="lab" />
          </template>
        </LdTabs>
        <ConfirmDialog
          v-if="confirmPublish"
          :title="t('labs.publish')"
          :message="t('labs.publishConfirm')"
          :confirm-label="t('labs.publish')"
          :busy="publishing"
          @cancel="confirmPublish = false"
          @confirm="publish"
        />
      </template>
    </template>
  </div>
</template>

<style scoped>
.ld-lab__back {
  align-self: flex-start;
  font-size: var(--ld-text-sm);
}

.ld-lab__head h1 {
  margin-bottom: var(--ld-space-2);
}

.ld-lab__badges {
  gap: var(--ld-space-2);
}

.ld-lab__dl {
  margin: 0;
  display: grid;
  grid-template-columns: minmax(8rem, max-content) 1fr;
  gap: var(--ld-space-2) var(--ld-space-4);
}

.ld-lab__dl dt {
  font-weight: 600;
}

.ld-lab__dl dd {
  margin: 0;
}

@media (max-width: 560px) {
  .ld-lab__dl {
    grid-template-columns: 1fr;
  }

  .ld-lab__dl dd {
    margin-bottom: var(--ld-space-2);
  }
}

.ld-lab__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-3);
}

.ld-lab__actions p {
  margin: 0;
  flex-basis: 100%;
}
</style>
