<script setup lang="ts">
/** `/app/entregas/:id`: datos de la entrega, archivos, simulador en sólo lectura y revisión (docente). */
import { computed, reactive, ref, useId, watch } from 'vue'
import { useRoute } from 'vue-router'
import { coursesApi, labsApi, type Course, type Lab } from '@/api/courses'
import { submissionsApi, type Submission } from '@/api/submissions'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdCheckbox from '@/components/LdCheckbox.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextArea from '@/components/LdTextArea.vue'
import { config } from '@/config'
import { t } from '@/i18n'
import { formatBogota } from '@/lib/bogota'
import { courseErrorMessage, fieldErrors } from '../courses/courseErrors'
import { describeScale, formatGrade, validateGrade } from '../labs/labRules'
import AttemptHistory from './AttemptHistory.vue'
import SubmissionFiles from './SubmissionFiles.vue'
import SubmissionStatusBadge from './SubmissionStatusBadge.vue'

const route = useRoute()
const uid = useId()
const subId = computed(() => String(route.params.id))

const sub = ref<Submission | null>(null)
const lab = ref<Lab | null>(null)
const course = ref<Course | null>(null)
const attempts = ref<Submission[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

const form = reactive({ grade: '', comment: '', returnIt: false })
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const sentOk = ref(false)
const sending = ref(false)

const isTeacher = computed(() => course.value?.my_role === 'docente')
/** Envoltorio FPGA (LD-9) en sólo lectura: carga `GET /submissions/{id}` (content + version_id). */
const simulatorUrl = computed(() =>
  sub.value ? `${config.basePath}app/fpga/?entrega=${encodeURIComponent(sub.value.id)}` : '',
)

function sameGroup(a: Submission, b: Submission) {
  return a.team ? a.team.id === b.team?.id : !b.team && a.submitted_by.id === b.submitted_by.id
}

async function load() {
  if (route.name !== 'submission') return // saliendo de la página
  loading.value = true
  loadError.value = null
  try {
    sub.value = await submissionsApi.get(subId.value)
    lab.value = await labsApi.get(sub.value.lab_id)
    course.value = await coursesApi.get(lab.value.course_id)
    const all = await submissionsApi.listForLab(lab.value.id)
    attempts.value = all.filter((s) => sameGroup(s, sub.value!))
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function sendReview() {
  if (!sub.value || !lab.value) return
  errors.value = {}
  formError.value = null
  sentOk.value = false
  const check = validateGrade(form.grade, lab.value.grade_scale)
  if (!check.ok) {
    errors.value.grade = check.error
    return
  }
  if (check.value === null && !form.comment.trim() && !form.returnIt) {
    formError.value = t('review.errEmpty')
    return
  }
  sending.value = true
  try {
    await submissionsApi.review(sub.value.id, {
      ...(check.value !== null ? { grade: check.value } : {}),
      comment: form.comment.trim(),
      return_for_resubmission: form.returnIt,
    })
    form.grade = ''
    form.comment = ''
    form.returnIt = false
    sentOk.value = true
    await load()
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = courseErrorMessage(e)
  } finally {
    sending.value = false
  }
}

watch(subId, load, { immediate: true })
</script>

<template>
  <div class="ld-stack ld-review">
    <RouterLink v-if="lab" :to="{ name: 'lab', params: { id: lab.id } }" class="ld-review__back">
      ← {{ t('review.back') }}: {{ lab.title }}
    </RouterLink>

    <LdSpinner v-if="loading" size="lg" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger" data-test="submission-error">
      {{ loadError }}
    </LdAlert>

    <template v-else-if="sub && lab && course">
      <header>
        <h1>{{ isTeacher ? t('review.title') : t('review.titleStudent') }}</h1>
        <p class="ld-muted">{{ course.name }} · {{ lab.title }}</p>
      </header>

      <LdAlert v-if="sentOk" variant="success" data-test="review-sent">{{
        t('review.sent')
      }}</LdAlert>

      <div class="ld-review__grid">
        <LdCard :title="t('subs.attempt', { n: sub.attempt })" :heading-level="2">
          <dl class="ld-review__dl">
            <dt>{{ t('review.who') }}</dt>
            <dd>{{ sub.submitted_by.full_name }}</dd>
            <template v-if="sub.team">
              <dt>{{ t('review.team') }}</dt>
              <dd>{{ sub.team.name }}</dd>
              <dt>{{ t('review.members') }}</dt>
              <dd>{{ sub.members.map((m) => m.full_name).join(', ') }}</dd>
            </template>
            <dt>{{ t('review.when') }}</dt>
            <dd>
              {{ formatBogota(sub.submitted_at) }}
              <template v-if="sub.is_late">({{ t('subs.late') }})</template>
            </dd>
            <dt>{{ t('table.status') }}</dt>
            <dd><SubmissionStatusBadge :submission="sub" /></dd>
            <dt>{{ t('review.currentGrade') }}</dt>
            <dd data-test="current-grade">{{ formatGrade(sub.grade, lab.grade_scale) }}</dd>
            <dt>{{ t('submit.version') }}</dt>
            <dd>{{ t('subs.version', { v: sub.version_n, project: sub.project_name }) }}</dd>
          </dl>
          <template #footer>
            <LdButton :href="simulatorUrl" variant="secondary" data-test="open-readonly">
              {{ t('review.openInSimulator') }}
            </LdButton>
            <p class="ld-muted ld-review__hint">{{ t('review.openInSimulatorHelp') }}</p>
          </template>
        </LdCard>

        <LdCard :title="t('subs.files')" :heading-level="2">
          <SubmissionFiles :files="sub.files" />
        </LdCard>
      </div>

      <LdCard v-if="isTeacher" :title="t('review.formTitle')" :heading-level="2">
        <form class="ld-form" novalidate data-test="review-form" @submit.prevent="sendReview">
          <LdAlert v-if="formError" variant="danger" data-test="review-error">{{
            formError
          }}</LdAlert>

          <div
            v-if="lab.grade_scale.type === 'numeric'"
            class="ld-field"
            :class="{ 'ld-field--invalid': !!errors.grade }"
          >
            <label class="ld-field__label" :for="`g-${uid}`">{{ t('review.grade') }}</label>
            <input
              :id="`g-${uid}`"
              v-model="form.grade"
              class="ld-field__input ld-review__grade"
              name="grade"
              inputmode="decimal"
              autocomplete="off"
              :aria-invalid="errors.grade ? 'true' : undefined"
              :aria-describedby="`g-${uid}-h g-${uid}-e`"
            />
            <p :id="`g-${uid}-h`" class="ld-field__help">
              {{ t('review.gradeHelp', { desc: describeScale(lab.grade_scale) }) }}
            </p>
            <p
              :id="`g-${uid}-e`"
              class="ld-field__error"
              aria-live="polite"
              data-test="grade-error"
            >
              {{ errors.grade ?? '' }}
            </p>
          </div>
          <fieldset v-else class="ld-review__pf">
            <legend class="ld-field__label">{{ t('review.grade') }}</legend>
            <label
              ><input v-model="form.grade" type="radio" name="grade" value="1" />
              {{ t('review.gradePass') }}</label
            >
            <label
              ><input v-model="form.grade" type="radio" name="grade" value="0" />
              {{ t('review.gradeFail') }}</label
            >
            <label
              ><input v-model="form.grade" type="radio" name="grade" value="" />
              {{ t('review.gradeNone') }}</label
            >
            <p class="ld-field__error" aria-live="polite" data-test="grade-error">
              {{ errors.grade ?? '' }}
            </p>
          </fieldset>

          <LdTextArea
            v-model="form.comment"
            :label="t('review.comment')"
            name="comment"
            :rows="4"
            :error="errors.comment"
          />
          <LdCheckbox
            v-model="form.returnIt"
            :label="t('review.returnForResubmission')"
            name="return_for_resubmission"
          />
          <div class="ld-form__actions">
            <LdButton type="submit" :loading="sending" data-test="review-submit">
              {{ sending ? t('review.sending') : t('review.send') }}
            </LdButton>
          </div>
        </form>
      </LdCard>

      <section class="ld-stack">
        <h2>{{ t('labs.historyTitle') }}</h2>
        <AttemptHistory :submissions="attempts" :scale="lab.grade_scale" :current-id="sub.id" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.ld-review__back {
  align-self: flex-start;
  font-size: var(--ld-text-sm);
}

.ld-review__grid {
  display: grid;
  gap: var(--ld-space-4);
}

@media (min-width: 900px) {
  .ld-review__grid {
    grid-template-columns: 3fr 2fr;
  }
}

.ld-review__dl {
  margin: 0;
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--ld-space-2) var(--ld-space-4);
}

.ld-review__dl dt {
  font-weight: 600;
}

.ld-review__dl dd {
  margin: 0;
}

.ld-review__hint {
  margin: 0;
  flex-basis: 100%;
  font-size: var(--ld-text-sm);
}

.ld-review__grade {
  max-width: 10rem;
}

.ld-review__pf {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2) var(--ld-space-4);
}

.ld-review__pf legend {
  margin-bottom: var(--ld-space-2);
}

.ld-review__pf .ld-field__error {
  flex-basis: 100%;
}
</style>
