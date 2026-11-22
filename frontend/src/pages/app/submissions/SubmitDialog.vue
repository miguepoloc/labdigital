<script setup lang="ts">
/**
 * Diálogo de entrega: laboratorio (si no viene dado), proyecto + versión, informe, .bit y adjuntos.
 * Valida tipos y tamaños en cliente, sube cada archivo con `POST /files` (barra de progreso) y crea la
 * entrega con `POST /labs/{id}/submissions`. No usa el router: también se monta suelto con
 * `openSubmitDialog()` desde el envoltorio FPGA.
 */
import { computed, onMounted, reactive, ref, useId, watch } from 'vue'
import { coursesApi, labsApi, type Lab } from '@/api/courses'
import { isApiError } from '@/api/errors'
import {
  projectsReadApi,
  submissionsApi,
  uploadFile,
  type FileKind,
  type ProjectSummary,
  type ProjectVersion,
  type Submission,
} from '@/api/submissions'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { config } from '@/config'
import { t } from '@/i18n'
import { formatBogota } from '@/lib/bogota'
import { courseErrorMessage, fieldErrors } from '../courses/courseErrors'
import { deadlineState } from '../labs/labRules'
import {
  KIND_EXTENSIONS,
  MAX_SUBMISSION_BYTES,
  formatBytes,
  validateFile,
  validateTotal,
} from './uploadRules'
import type { SubmitDialogProps } from './submitDialog'

const props = defineProps<SubmitDialogProps>()
const emit = defineEmits<{ close: []; submitted: [Submission] }>()
const uid = useId()

interface Picked {
  file: File
  kind: FileKind
  error: string | null
}

const loading = ref(true)
const loadError = ref<string | null>(null)
const labs = ref<Lab[]>([])
const lab = ref<Lab | null>(props.lab ?? null)
const selectedLabId = ref(props.labId ?? props.lab?.id ?? '')
const projects = ref<ProjectSummary[]>([])
const versions = ref<ProjectVersion[]>([])
const versionsLoading = ref(false)
const projectId = ref(props.projectId ?? '')
const versionId = ref(props.versionId ?? '')

const report = ref<Picked | null>(null)
const bitstream = ref<Picked | null>(null)
const attachments = ref<Picked[]>([])
const fieldErr = reactive<Record<string, string>>({})
const formError = ref<string | null>(null)
const sending = ref(false)
const progress = ref<{ name: string; loaded: number; total: number } | null>(null)
const result = ref<Submission | null>(null)
/** Archivos ya subidos en un intento anterior fallido (no se vuelven a subir). */
const uploaded = new Map<File, string>()

/** El servidor manda: si respondió `deadline_passed`, el lab se trata como cerrado aunque el reloj local no lo crea. */
const serverClosed = ref(false)
const state = computed(() =>
  serverClosed.value ? 'closed' : lab.value ? deadlineState(lab.value) : null,
)
const blocked = computed(() => state.value === 'closed' || state.value === 'not_open')
const allFiles = computed(() =>
  [report.value, bitstream.value, ...attachments.value].filter((x): x is Picked => !!x),
)
const totalBytes = computed(() => allFiles.value.reduce((acc, p) => acc + p.file.size, 0))
const totalError = computed(() => validateTotal(allFiles.value.map((p) => p.file)))
const hasFileErrors = computed(() => allFiles.value.some((p) => p.error) || !!totalError.value)

function pick(file: File, kind: FileKind): Picked {
  return { file, kind, error: validateFile(file, kind) }
}

if (props.prefill?.report) report.value = pick(props.prefill.report, 'report')
if (props.prefill?.bitstream) bitstream.value = pick(props.prefill.bitstream, 'bitstream')
for (const f of props.prefill?.attachments ?? []) attachments.value.push(pick(f, 'attachment'))

async function loadLabsToPick() {
  const courses = (await coursesApi.list()).filter(
    (c) => c.my_role === 'estudiante' && c.my_status === 'active',
  )
  const lists = await Promise.all(courses.map((c) => labsApi.list(c.id)))
  labs.value = lists
    .flat()
    .filter((l) => l.published_at && !['closed', 'not_open'].includes(deadlineState(l)))
}

async function loadVersions() {
  versions.value = []
  if (!projectId.value) return
  versionsLoading.value = true
  try {
    versions.value = await projectsReadApi.versions(projectId.value)
    if (versionId.value && !versions.value.some((v) => v.id === versionId.value))
      versionId.value = ''
  } catch (e) {
    fieldErr.version_id = courseErrorMessage(e)
  } finally {
    versionsLoading.value = false
  }
}

onMounted(async () => {
  try {
    const tasks: Promise<unknown>[] = [
      projectsReadApi.list('fpga').then((p) => (projects.value = p)),
    ]
    if (!lab.value && selectedLabId.value) {
      tasks.push(labsApi.get(selectedLabId.value).then((l) => (lab.value = l)))
    } else if (!lab.value) {
      tasks.push(loadLabsToPick())
    }
    await Promise.all(tasks)
    if (!projectId.value && projects.value.length === 1) projectId.value = projects.value[0]!.id
    await loadVersions()
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
})

watch(projectId, () => {
  delete fieldErr.project_id
  void loadVersions()
})
watch(selectedLabId, (id) => {
  delete fieldErr.lab
  lab.value = labs.value.find((l) => l.id === id) ?? null
})

function onFile(e: Event, kind: FileKind) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (kind === 'report') report.value = files[0] ? pick(files[0], kind) : report.value
  else if (kind === 'bitstream') bitstream.value = files[0] ? pick(files[0], kind) : bitstream.value
  else attachments.value.push(...files.map((f) => pick(f, kind)))
  input.value = ''
}

function removeFile(p: Picked) {
  if (p === report.value) report.value = null
  else if (p === bitstream.value) bitstream.value = null
  else attachments.value = attachments.value.filter((x) => x !== p)
}

function versionText(v: ProjectVersion) {
  const date = formatBogota(v.created_at)
  return v.label
    ? t('submit.versionLabel', { n: v.n, label: v.label, date })
    : t('submit.versionItem', { n: v.n, date })
}

async function submit() {
  formError.value = null
  for (const k of Object.keys(fieldErr)) delete fieldErr[k]
  if (!lab.value) fieldErr.lab = t('submit.errLab')
  if (!projectId.value) fieldErr.project_id = t('submit.errProject')
  if (Object.keys(fieldErr).length || hasFileErrors.value || blocked.value || !lab.value) {
    formError.value = t('validation.formHasErrors')
    return
  }
  sending.value = true
  try {
    const ids: string[] = []
    for (const p of allFiles.value) {
      let id = uploaded.get(p.file)
      if (!id) {
        progress.value = { name: p.file.name, loaded: 0, total: p.file.size }
        const res = await uploadFile(p.file, p.kind, {
          onProgress: (loaded, total) => {
            progress.value = { name: p.file.name, loaded, total }
          },
        })
        id = res.id
        uploaded.set(p.file, id)
      }
      ids.push(id)
    }
    progress.value = null
    const submission = await submissionsApi.create(lab.value.id, {
      project_id: projectId.value,
      ...(versionId.value ? { version_id: versionId.value } : {}),
      file_ids: ids,
    })
    result.value = submission
    emit('submitted', submission)
  } catch (e) {
    Object.assign(fieldErr, fieldErrors(e))
    formError.value = courseErrorMessage(e)
    if (isApiError(e) && e.code === 'deadline_passed') serverClosed.value = true
  } finally {
    sending.value = false
    progress.value = null
  }
}

const singleSlots = computed(() => [
  { kind: 'report' as const, label: t('submit.report'), item: report.value },
  { kind: 'bitstream' as const, label: t('submit.bitstream'), item: bitstream.value },
])
const fromBrowser = !!props.prefill?.bitstreamFromBrowser
const accept = (kind: FileKind) => KIND_EXTENSIONS[kind].join(',')
const submissionUrl = (id: string) => `${config.basePath}app/entregas/${encodeURIComponent(id)}`
const title = computed(() =>
  lab.value ? t('submit.titleFor', { lab: lab.value.title }) : t('submit.title'),
)
</script>

<template>
  <LdDialog :title="title" wide :persistent="sending" @close="emit('close')">
    <!-- Resultado -->
    <div v-if="result" class="ld-stack" data-test="submit-result">
      <LdAlert variant="success">
        <p>
          <strong>
            {{
              result.is_late
                ? t('submit.doneLate', { date: formatBogota(result.submitted_at) })
                : t('submit.done', { date: formatBogota(result.submitted_at) })
            }}
          </strong>
        </p>
        <p>
          {{
            t('submit.doneAttempt', {
              n: result.attempt,
              v: result.version_n,
              project: result.project_name,
            })
          }}
        </p>
      </LdAlert>
      <div class="ld-form__actions">
        <LdButton :href="submissionUrl(result.id)">{{ t('submit.viewSubmission') }}</LdButton>
        <LdButton variant="ghost" data-test="submit-close" @click="emit('close')">
          {{ t('submit.close') }}
        </LdButton>
      </div>
    </div>

    <LdSpinner v-else-if="loading" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger">{{ loadError }}</LdAlert>

    <form v-else class="ld-form" novalidate data-test="submit-form" @submit.prevent="submit">
      <!-- Laboratorio -->
      <div
        v-if="!props.lab && !props.labId"
        class="ld-field"
        :class="{ 'ld-field--invalid': !!fieldErr.lab }"
      >
        <label class="ld-field__label" :for="`lab-${uid}`">{{ t('submit.lab') }}</label>
        <p v-if="labs.length === 0" class="ld-muted">{{ t('submit.noLabs') }}</p>
        <select
          v-else
          :id="`lab-${uid}`"
          v-model="selectedLabId"
          class="ld-field__input"
          name="lab"
        >
          <option value="" disabled>{{ t('submit.labPlaceholder') }}</option>
          <option v-for="l in labs" :key="l.id" :value="l.id">{{ l.title }}</option>
        </select>
        <p class="ld-field__error" aria-live="polite">{{ fieldErr.lab ?? '' }}</p>
      </div>

      <LdAlert
        v-if="state === 'closed'"
        variant="danger"
        :title="t('labs.closedTitle')"
        data-test="submit-closed"
      >
        {{ t('labs.closedBody', { date: formatBogota(lab?.due_at) }) }}
      </LdAlert>
      <LdAlert v-else-if="state === 'not_open'" variant="info" :title="t('labs.notOpenTitle')">
        {{ t('labs.notOpenBody', { date: formatBogota(lab?.opens_at) }) }}
      </LdAlert>
      <LdAlert v-else-if="state === 'late'" variant="warning" data-test="submit-late">
        {{ t('submit.lateWarning') }}
      </LdAlert>

      <LdAlert v-if="formError" variant="danger" data-test="submit-error">{{ formError }}</LdAlert>

      <!-- Proyecto y versión -->
      <div class="ld-submit__row">
        <div class="ld-field" :class="{ 'ld-field--invalid': !!fieldErr.project_id }">
          <label class="ld-field__label" :for="`prj-${uid}`">{{ t('submit.project') }}</label>
          <p v-if="projects.length === 0" class="ld-muted" data-test="no-projects">
            {{ t('submit.noProjects') }}
          </p>
          <select
            v-else
            :id="`prj-${uid}`"
            v-model="projectId"
            class="ld-field__input"
            name="project"
            :aria-invalid="fieldErr.project_id ? 'true' : undefined"
          >
            <option value="" disabled>{{ t('submit.projectPlaceholder') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
          <p class="ld-field__error" aria-live="polite">{{ fieldErr.project_id ?? '' }}</p>
        </div>
        <div class="ld-field" :class="{ 'ld-field--invalid': !!fieldErr.version_id }">
          <label class="ld-field__label" :for="`ver-${uid}`">{{ t('submit.version') }}</label>
          <select
            :id="`ver-${uid}`"
            v-model="versionId"
            class="ld-field__input"
            name="version"
            :disabled="!projectId || versionsLoading"
          >
            <option value="">{{ t('submit.versionCurrent') }}</option>
            <!-- `selected` explícito: las opciones llegan después del montaje (versión preelegida). -->
            <option v-for="v in versions" :key="v.id" :value="v.id" :selected="v.id === versionId">
              {{ versionText(v) }}
            </option>
          </select>
          <p class="ld-field__error" aria-live="polite">{{ fieldErr.version_id ?? '' }}</p>
        </div>
      </div>

      <!-- Archivos -->
      <p class="ld-muted ld-submit__limits">{{ t('submit.limits') }}</p>
      <div v-for="slot in singleSlots" :key="slot.kind" class="ld-field">
        <label class="ld-field__label" :for="`${slot.kind}-${uid}`">{{ slot.label }}</label>
        <input
          :id="`${slot.kind}-${uid}`"
          type="file"
          class="ld-submit__file"
          :name="slot.kind"
          :accept="accept(slot.kind)"
          :data-test="`file-${slot.kind}`"
          @change="onFile($event, slot.kind)"
        />
        <div v-if="slot.item" class="ld-submit__picked" data-test="picked-file">
          <span>{{ slot.item.file.name }} ({{ formatBytes(slot.item.file.size) }})</span>
          <LdButton
            size="sm"
            variant="ghost"
            :aria-label="t('submit.removeLabel', { name: slot.item.file.name })"
            @click="removeFile(slot.item)"
          >
            {{ t('submit.remove') }}
          </LdButton>
          <p
            v-if="
              slot.kind === 'bitstream' &&
              fromBrowser &&
              slot.item.file === props.prefill?.bitstream
            "
            class="ld-field__help ld-submit__note"
            data-test="bit-from-browser"
          >
            {{
              t('submit.bitFromBrowser', {
                name: slot.item.file.name,
                date: formatBogota(new Date(slot.item.file.lastModified).toISOString()),
              })
            }}
          </p>
          <p v-if="slot.item.error" class="ld-field__error" role="alert" data-test="file-error">
            {{ slot.item.error }}
          </p>
        </div>
      </div>

      <div class="ld-field">
        <label class="ld-field__label" :for="`att-${uid}`">{{ t('submit.attachments') }}</label>
        <input
          :id="`att-${uid}`"
          type="file"
          multiple
          class="ld-submit__file"
          name="attachments"
          :accept="accept('attachment')"
          :aria-describedby="`att-${uid}-h`"
          data-test="file-attachment"
          @change="onFile($event, 'attachment')"
        />
        <p :id="`att-${uid}-h`" class="ld-field__help">{{ t('submit.attachmentsHelp') }}</p>
        <div
          v-for="(p, i) in attachments"
          :key="i"
          class="ld-submit__picked"
          data-test="picked-file"
        >
          <span>{{ p.file.name }} ({{ formatBytes(p.file.size) }})</span>
          <LdButton
            size="sm"
            variant="ghost"
            :aria-label="t('submit.removeLabel', { name: p.file.name })"
            @click="removeFile(p)"
          >
            {{ t('submit.remove') }}
          </LdButton>
          <p v-if="p.error" class="ld-field__error" role="alert" data-test="file-error">
            {{ p.error }}
          </p>
        </div>
      </div>

      <p class="ld-submit__total" :class="{ 'is-error': !!totalError }" data-test="submit-total">
        {{
          t('submit.total', {
            total: formatBytes(totalBytes),
            max: formatBytes(MAX_SUBMISSION_BYTES),
          })
        }}
      </p>
      <p v-if="totalError" class="ld-field__error" role="alert" data-test="total-error">
        {{ totalError }}
      </p>

      <div v-if="progress" class="ld-submit__progress" aria-live="polite">
        <label :for="`prog-${uid}`">{{ t('submit.uploading', { name: progress.name }) }}</label>
        <progress
          :id="`prog-${uid}`"
          :max="progress.total || 1"
          :value="progress.loaded"
          :aria-label="t('submit.uploadProgress', { name: progress.name })"
        />
      </div>

      <div class="ld-form__actions">
        <LdButton
          type="submit"
          :loading="sending"
          :disabled="blocked || hasFileErrors || projects.length === 0"
          data-test="submit-confirm"
        >
          {{ sending ? t('submit.sending') : t('submit.confirm') }}
        </LdButton>
        <LdButton variant="ghost" :disabled="sending" @click="emit('close')">
          {{ t('submit.cancel') }}
        </LdButton>
      </div>
    </form>
  </LdDialog>
</template>

<style scoped>
.ld-submit__row {
  display: grid;
  gap: var(--ld-space-3);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 18rem), 1fr));
}

.ld-submit__limits {
  margin: 0;
  font-size: var(--ld-text-sm);
}

.ld-submit__file {
  font-size: var(--ld-text-sm);
}

.ld-submit__file:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-submit__picked {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
  font-size: var(--ld-text-sm);
}

.ld-submit__picked .ld-field__error,
.ld-submit__note {
  flex-basis: 100%;
}

.ld-submit__total {
  margin: 0;
  font-size: var(--ld-text-sm);
  color: var(--ld-color-text-muted);
}

.ld-submit__total.is-error {
  color: var(--ld-color-danger);
}

.ld-submit__progress {
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-1);
  font-size: var(--ld-text-sm);
}

.ld-submit__progress progress {
  width: 100%;
  height: 0.75rem;
  accent-color: var(--ld-color-primary);
}
</style>
