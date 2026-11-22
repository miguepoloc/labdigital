<script setup lang="ts">
import { computed, reactive, ref, useId, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  coursesApi,
  labsApi,
  type Course,
  type DeadlinePolicy,
  type GradeScale,
  type Lab,
  type LabInput,
  type TeamMode,
} from '@/api/courses'
import { isApiError } from '@/api/errors'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCheckbox from '@/components/LdCheckbox.vue'
import LdMarkdown from '@/components/LdMarkdown.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextArea from '@/components/LdTextArea.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import { fromBogotaInput, toBogotaInput } from '@/lib/bogota'
import { courseErrorMessage, fieldErrors } from '../courses/courseErrors'
import GradeScaleEditor from './GradeScaleEditor.vue'
import { defaultScale, validateScale } from './labRules'

const route = useRoute()
const router = useRouter()
const uid = useId()
const isNew = computed(() => route.name === 'lab-new')

const course = ref<Course | null>(null)
const lab = ref<Lab | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const saving = ref<'draft' | 'publish' | null>(null)
const formError = ref<string | null>(null)
const errors = ref<Record<string, string>>({})
const scaleErrors = ref<Record<string, string>>({})
const showPreview = ref(false)

const form = reactive({
  title: '',
  statement_md: '',
  module: 'fpga',
  opens_at: '',
  due_at: '',
  deadline_policy: 'late_marked' as DeadlinePolicy,
  team_mode: 'individual' as TeamMode,
  max_team_size: '3',
  grade_scale: defaultScale() as GradeScale,
  allow_resubmission: false,
})

const POLICIES: DeadlinePolicy[] = ['strict', 'late_marked', 'none']

function fill(l: Lab) {
  form.title = l.title
  form.statement_md = l.statement_md
  form.module = l.module
  form.opens_at = toBogotaInput(l.opens_at)
  form.due_at = toBogotaInput(l.due_at)
  form.deadline_policy = l.deadline_policy
  form.team_mode = l.team_mode
  form.max_team_size = String(l.max_team_size ?? 3)
  form.grade_scale = { ...l.grade_scale }
  form.allow_resubmission = l.allow_resubmission
}

async function load() {
  if (route.name !== 'lab-new' && route.name !== 'lab-edit') return // saliendo de la página
  loading.value = true
  loadError.value = null
  try {
    if (isNew.value) {
      course.value = await coursesApi.get(String(route.params.id))
    } else {
      lab.value = await labsApi.get(String(route.params.id))
      course.value = await coursesApi.get(lab.value.course_id)
      fill(lab.value)
    }
    if (course.value.my_role !== 'docente') loadError.value = t('courseErrors.forbidden')
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

function validate(): LabInput | null {
  const e: Record<string, string> = {}
  if (!form.title.trim()) e.title = t('labEditor.errTitle')
  const opens = form.opens_at ? fromBogotaInput(form.opens_at) : null
  const due = form.due_at ? fromBogotaInput(form.due_at) : null
  if (form.deadline_policy !== 'none' && !due) e.due_at = t('labEditor.errDue')
  if (opens && due && Date.parse(due) <= Date.parse(opens))
    e.due_at = t('labEditor.errDueBeforeOpen')
  let maxTeam: number | null = null
  if (form.team_mode === 'team') {
    maxTeam = Number(form.max_team_size)
    if (!Number.isInteger(maxTeam) || maxTeam < 2 || maxTeam > 10)
      e.max_team_size = t('labEditor.errTeamSize')
  }
  scaleErrors.value = validateScale(form.grade_scale)
  errors.value = e
  if (Object.keys(e).length || Object.keys(scaleErrors.value).length) return null
  return {
    title: form.title.trim(),
    statement_md: form.statement_md,
    module: form.module,
    opens_at: opens,
    due_at: due,
    deadline_policy: form.deadline_policy,
    team_mode: form.team_mode,
    max_team_size: maxTeam,
    grade_scale: form.grade_scale,
    allow_resubmission: form.allow_resubmission,
  }
}

async function save(publish: boolean) {
  formError.value = null
  const body = validate()
  if (!body) {
    formError.value = t('validation.formHasErrors')
    return
  }
  saving.value = publish ? 'publish' : 'draft'
  try {
    let saved = lab.value
      ? await labsApi.update(lab.value.id, body)
      : await labsApi.create(course.value!.id, body)
    if (publish && !saved.published_at) saved = await labsApi.publish(saved.id)
    await router.push({ name: 'lab', params: { id: saved.id }, query: { guardado: '1' } })
  } catch (e) {
    const fields = fieldErrors(e)
    if (isApiError(e) && e.code === 'validation_error') {
      const { grade_scale, ...rest } = fields
      errors.value = rest
      if (grade_scale) scaleErrors.value = { max: grade_scale }
    }
    formError.value = courseErrorMessage(e)
  } finally {
    saving.value = null
  }
}

function cancel() {
  if (lab.value) void router.push({ name: 'lab', params: { id: lab.value.id } })
  else if (course.value) void router.push({ name: 'course', params: { id: course.value.id } })
}

watch(() => route.fullPath, load, { immediate: true })
</script>

<template>
  <div class="ld-stack ld-editor">
    <h1>{{ isNew ? t('labEditor.createTitle') : t('labEditor.editTitle') }}</h1>
    <p v-if="course" class="ld-muted">{{ course.name }}</p>

    <LdSpinner v-if="loading" size="lg" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger" data-test="editor-error">{{
      loadError
    }}</LdAlert>

    <form v-else class="ld-form" novalidate data-test="lab-form" @submit.prevent="save(false)">
      <LdAlert v-if="formError" variant="danger" data-test="form-error">{{ formError }}</LdAlert>

      <LdTextField
        v-model="form.title"
        :label="t('labEditor.title')"
        name="title"
        :placeholder="t('labEditor.titlePlaceholder')"
        :error="errors.title"
        required
      />

      <div class="ld-stack ld-editor__statement">
        <LdTextArea
          v-model="form.statement_md"
          :label="t('labEditor.statement')"
          name="statement_md"
          :rows="10"
          mono
          :help="t('labEditor.statementHelp')"
          :error="errors.statement_md"
        />
        <LdCheckbox v-model="showPreview" :label="t('labEditor.preview')" />
        <div v-if="showPreview" class="ld-editor__preview" data-test="statement-preview">
          <LdMarkdown :source="form.statement_md" />
        </div>
      </div>

      <div class="ld-field">
        <label class="ld-field__label" :for="`mod-${uid}`">{{ t('labEditor.module') }}</label>
        <select :id="`mod-${uid}`" v-model="form.module" class="ld-field__input" name="module">
          <option value="fpga">{{ t('labEditor.moduleFpga') }}</option>
        </select>
      </div>

      <fieldset class="ld-editor__group">
        <legend class="ld-field__label">{{ t('labEditor.datesTitle') }}</legend>
        <div class="ld-editor__dates">
          <div class="ld-field">
            <label class="ld-field__label" :for="`op-${uid}`">{{ t('labEditor.opensAt') }}</label>
            <input
              :id="`op-${uid}`"
              v-model="form.opens_at"
              class="ld-field__input"
              type="datetime-local"
              name="opens_at"
              :aria-describedby="`op-${uid}-h`"
            />
            <p :id="`op-${uid}-h`" class="ld-field__help">{{ t('labEditor.opensAtHelp') }}</p>
          </div>
          <div class="ld-field" :class="{ 'ld-field--invalid': !!errors.due_at }">
            <label class="ld-field__label" :for="`du-${uid}`">{{ t('labEditor.dueAt') }}</label>
            <input
              :id="`du-${uid}`"
              v-model="form.due_at"
              class="ld-field__input"
              type="datetime-local"
              name="due_at"
              :aria-invalid="errors.due_at ? 'true' : undefined"
              :aria-describedby="`du-${uid}-e`"
            />
            <p :id="`du-${uid}-e`" class="ld-field__error" aria-live="polite">
              {{ errors.due_at ?? '' }}
            </p>
          </div>
        </div>
        <fieldset class="ld-editor__radios">
          <legend class="ld-field__label">{{ t('labEditor.policy') }}</legend>
          <label v-for="p in POLICIES" :key="p" class="ld-editor__radio">
            <input v-model="form.deadline_policy" type="radio" name="deadline_policy" :value="p" />
            <span>
              <strong>{{ t(`labs.policy.${p}`) }}</strong>
              <span class="ld-muted"> — {{ t(`labs.policyHelp.${p}`) }}</span>
            </span>
          </label>
        </fieldset>
      </fieldset>

      <fieldset class="ld-editor__group">
        <legend class="ld-field__label">{{ t('labEditor.modeTitle') }}</legend>
        <div class="ld-row">
          <label class="ld-editor__radio">
            <input v-model="form.team_mode" type="radio" name="team_mode" value="individual" />
            {{ t('labEditor.individual') }}
          </label>
          <label class="ld-editor__radio">
            <input v-model="form.team_mode" type="radio" name="team_mode" value="team" />
            {{ t('labEditor.team') }}
          </label>
        </div>
        <LdTextField
          v-if="form.team_mode === 'team'"
          v-model="form.max_team_size"
          :label="t('labEditor.maxTeamSize')"
          name="max_team_size"
          inputmode="numeric"
          :error="errors.max_team_size"
        />
      </fieldset>

      <GradeScaleEditor v-model="form.grade_scale" :errors="scaleErrors" />

      <LdCheckbox
        v-model="form.allow_resubmission"
        :label="t('labEditor.allowResubmission')"
        :help="t('labEditor.allowResubmissionHelp')"
        name="allow_resubmission"
      />

      <div class="ld-form__actions">
        <LdButton type="submit" :loading="saving === 'draft'" :disabled="!!saving" data-test="save">
          {{ lab ? t('labEditor.saveChanges') : t('labEditor.save') }}
        </LdButton>
        <LdButton
          v-if="!lab?.published_at"
          variant="accent"
          :loading="saving === 'publish'"
          :disabled="!!saving"
          data-test="save-publish"
          @click="save(true)"
        >
          {{ t('labEditor.saveAndPublish') }}
        </LdButton>
        <LdButton variant="ghost" :disabled="!!saving" @click="cancel">
          {{ t('labEditor.cancel') }}
        </LdButton>
      </div>
    </form>
  </div>
</template>

<style scoped>
.ld-editor {
  max-width: 52rem;
}

.ld-editor__preview {
  padding: var(--ld-space-4);
  border: 1px dashed var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  background: var(--ld-color-surface);
}

.ld-editor__group,
.ld-editor__radios {
  margin: 0;
  padding: var(--ld-space-4);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
}

.ld-editor__radios {
  border-style: dashed;
}

.ld-editor__dates {
  display: grid;
  gap: var(--ld-space-3);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr));
}

.ld-editor__radio {
  display: inline-flex;
  align-items: flex-start;
  gap: var(--ld-space-2);
  cursor: pointer;
}

.ld-editor__radio input {
  margin-top: 0.3rem;
}
</style>
