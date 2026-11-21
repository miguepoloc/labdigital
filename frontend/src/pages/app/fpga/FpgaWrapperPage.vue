<script setup lang="ts">
/**
 * `/app/fpga/:projectId?` (LD-9): barra de LabDigital + JG FPGA en un iframe del mismo origen.
 *
 * Flujo: el iframe carga en paralelo con el proyecto; al `ready` del módulo (postMessage verificado o evento
 * `ready` de `window.JGFPGA`) se llama SIEMPRE a `loadProject(content)` (contrato §7: si no, se vería la caché
 * del módulo). Sin `projectId` se crea un proyecto con lo que devuelve `getProject()`. Después, cada `change`
 * alimenta el autoguardado (`autosave.ts`).
 *
 * Solo lectura (revisión): `?ver=<versionId>` (o `?readonly=1`, o `?entrega=<submissionId>`) carga con
 * `{ readOnly: true }` y no hay autoguardado.
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { api as http } from '@/api/client'
import {
  autosaveKeepalive,
  projectsApi,
  type FpgaContent,
  type Project,
  type ProjectContent,
  type ProjectVersion,
} from '@/api/projects'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import { errorMessage } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { formatAgo } from '@/pages/app/projects/format'
import { AUTOSAVE_DEFAULTS, Autosaver, type AutosaverSnapshot, type SaveBase } from './autosave'
import { fpgaSubmitDialog, type FpgaSubmitContext } from './extensions'
import FpgaDialog from './FpgaDialog.vue'
import FpgaSubmitPlaceholder from './FpgaSubmitPlaceholder.vue'
import { fpgaFrameUrl, watchFrameReady, type JgFpgaApi } from './jgfpga'

/** Espera máxima del guardado al salir por la propia app (después se deja salir y se usa keepalive). */
const LEAVE_FLUSH_TIMEOUT_MS = 4000

interface Loaded {
  project: Project | null
  content: ProjectContent | null
  versionN?: number
}

const route = useRoute()
const router = useRouter()

const frameSrc = fpgaFrameUrl()
const frame = ref<HTMLIFrameElement | null>(null)
const jg = shallowRef<JgFpgaApi | null>(null)
const project = ref<Project | null>(null)
const phase = ref<'loading' | 'creating' | 'ready' | 'error'>('loading')
const fatal = ref<string | null>(null)
const notice = ref<{ kind: 'success' | 'warning' | 'danger'; text: string } | null>(null)
const snap = ref<AutosaverSnapshot | null>(null)
const now = ref(Date.now())
const versionN = ref<number | null>(null)
const nameDraft = ref('')
const busy = ref<string | null>(null)
const showVersions = ref(false)
const versions = ref<ProjectVersion[] | null>(null)
const versionsError = ref<string | null>(null)
const confirmRestoreId = ref<string | null>(null)
const showSubmit = ref(false)

let saver: Autosaver | null = null
let changeApi: JgFpgaApi | null = null
let latest: ProjectContent | null = null
let stopFrameWatch: (() => void) | null = null
let ticker: ReturnType<typeof setInterval> | null = null
let dataPromise: Promise<Loaded> = Promise.resolve({ project: null, content: null })
let loadToken = 0

const q = (k: string) => (typeof route.query[k] === 'string' ? (route.query[k] as string) : '')
const projectId = computed(() => (route.params.projectId as string | undefined) || null)
const versionId = computed(() => q('ver'))
const submissionId = computed(() => q('entrega'))
const readOnly = computed(
  () => !!versionId.value || !!submissionId.value || route.query.readonly === '1',
)
const routeKey = computed(
  () =>
    `${projectId.value ?? ''}|${versionId.value}|${submissionId.value}|${readOnly.value ? 1 : 0}`,
)
let currentKey = ''

const SubmitDialog = computed(() => fpgaSubmitDialog.value ?? FpgaSubmitPlaceholder)

const statusText = computed(() => {
  if (phase.value === 'creating') return t('projects.fpga.creating')
  if (phase.value === 'loading') return t('projects.fpga.status.loading')
  if (phase.value === 'error') return ''
  if (readOnly.value) {
    return submissionId.value
      ? t('projects.fpga.status.readOnlySubmission')
      : t('projects.fpga.status.readOnly', { n: versionN.value ?? '—' })
  }
  const s = snap.value
  switch (s?.status) {
    case 'pending':
      return t('projects.fpga.status.pending')
    case 'saving':
      return t('projects.fpga.status.saving')
    case 'offline':
      return t('projects.fpga.status.offline')
    case 'conflict':
      return t('projects.fpga.status.conflict')
    case 'error':
      return `${t('projects.fpga.status.error')}: ${errorMessage(s.error)}`
    default:
      return s?.lastSavedAt
        ? t('projects.fpga.status.savedAgo', { ago: formatAgo(s.lastSavedAt, now.value) })
        : t('projects.fpga.status.saved')
  }
})
const statusKind = computed(() => {
  const st = snap.value?.status
  if (readOnly.value) return 'readonly'
  if (st === 'offline' || st === 'error' || st === 'conflict') return 'bad'
  if (st === 'pending' || st === 'saving') return 'busy'
  return 'ok'
})

// ---------------------------------------------------------------- datos

async function fetchData(): Promise<Loaded> {
  if (submissionId.value) {
    // Revisión de una entrega: el contenido congelado viene de `GET /submissions/{id}` (contrato §4).
    const s = await http.get<{ content: ProjectContent }>(
      `/submissions/${encodeURIComponent(submissionId.value)}`,
    )
    return { project: null, content: s.content }
  }
  if (!projectId.value) return { project: null, content: null }
  const p = await projectsApi.get(projectId.value)
  if (versionId.value) {
    const v = await projectsApi.getVersion(p.id, versionId.value)
    return { project: p, content: v.content, versionN: v.n }
  }
  return { project: p, content: p.content }
}

function baseOf(p: Project): SaveBase {
  return { version: p.current_version_id, n: p.current_version_n, revision: p.revision }
}

function setProject(p: Project) {
  project.value = p
  nameDraft.value = p.name
}

// ---------------------------------------------------------------- módulo

function onChange(content: FpgaContent) {
  latest = content
  saver?.change(content)
}

function subscribeChanges(a: JgFpgaApi) {
  if (changeApi === a) return
  changeApi?.off('change', onChange)
  a.on('change', onChange)
  changeApi = a
}

function unsubscribeChanges() {
  changeApi?.off('change', onChange)
  changeApi = null
}

function startAutosave(p: Project) {
  saver?.dispose()
  saver = new Autosaver({
    base: baseOf(p),
    save: (body) => projectsApi.autosave(p.id, body),
    keepalive: (body) => autosaveKeepalive(p.id, body),
    debounceMs: AUTOSAVE_DEFAULTS.debounceMs,
    retryDelaysMs: AUTOSAVE_DEFAULTS.retryDelaysMs,
    onChange: (s) => (snap.value = { ...s }),
  })
  snap.value = { ...saver.snapshot }
}

/** Carga en el módulo; captura el error de formato que lanza `loadProject`. */
function loadIntoFrame(a: JgFpgaApi, content: ProjectContent, ro: boolean): boolean {
  try {
    const skipped = a.loadProject(content, { readOnly: ro })
    if (Array.isArray(skipped) && skipped.length) {
      notice.value = {
        kind: 'warning',
        text: t('projects.fpga.loadSkipped', { files: skipped.join(', ') }),
      }
    }
    return true
  } catch (e) {
    fatal.value = t('projects.fpga.loadFailed', {
      message: e instanceof Error ? e.message : String(e),
    })
    phase.value = 'error'
    return false
  }
}

/** Aplica los datos de la ruta al módulo listo. Se repite si el iframe se recarga o cambia la ruta. */
async function apply() {
  const a = jg.value
  if (!a) return
  const token = loadToken
  let data: Loaded
  try {
    data = await dataPromise
  } catch (e) {
    if (token !== loadToken) return
    fatal.value = errorMessage(e)
    phase.value = 'error'
    return
  }
  if (token !== loadToken || jg.value !== a) return
  versionN.value = data.versionN ?? null

  let content = latest ?? data.content
  if (data.project && !project.value) setProject(data.project)

  if (!readOnly.value && !project.value) {
    // Proyecto nuevo: se crea en la API con el contenido inicial que tenga el módulo.
    phase.value = 'creating'
    try {
      const initial = a.getProject()
      const wanted = q('nombre').trim()
      const name = (wanted || initial.name || '').trim() || t('projects.fpga.newProjectName')
      const p = await projectsApi.create({
        name,
        module: 'fpga',
        content: wanted ? { ...initial, name: wanted } : initial,
      })
      if (token !== loadToken) return
      setProject(p)
      content = p.content
      currentKey = `${p.id}|||0`
      await router.replace({ name: 'fpga', params: { projectId: p.id }, query: {} })
    } catch (e) {
      fatal.value = errorMessage(e)
      phase.value = 'error'
      return
    }
  }

  if (!content) return
  if (!loadIntoFrame(a, content, readOnly.value)) return
  phase.value = 'ready'
  fatal.value = null
  if (readOnly.value || !project.value) return
  if (!saver) startAutosave(project.value)
  subscribeChanges(a)
}

function onFrameReady(a: JgFpgaApi) {
  jg.value = a
  void apply()
}

// ---------------------------------------------------------------- ciclo de vida

function start() {
  loadToken++
  currentKey = routeKey.value
  phase.value = 'loading'
  fatal.value = null
  latest = null
  versionN.value = null
  project.value = null
  dataPromise = fetchData()
  dataPromise.catch(() => {}) // se informa en apply()
  if (jg.value) void apply()
}

async function stop() {
  unsubscribeChanges()
  if (saver) {
    await saver.flush().catch(() => {})
    if (saver.snapshot.dirty) saver.flushOnExit()
    saver.dispose()
  }
  saver = null
  snap.value = null
}

watch(routeKey, async (key) => {
  if (key === currentKey) return
  await stop()
  start()
})

function onVisibility() {
  if (document.visibilityState === 'hidden') void saver?.flush().catch(() => {})
}

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (!saver) return
  const sent = saver.flushOnExit()
  const st = saver.snapshot.status
  if (saver.snapshot.dirty && (!sent || st === 'conflict' || st === 'error')) {
    e.preventDefault()
    e.returnValue = ''
  }
}

function onPageHide() {
  saver?.flushOnExit()
}

function onOnline() {
  saver?.retryNow()
}

onMounted(() => {
  start()
  if (frame.value) stopFrameWatch = watchFrameReady(frame.value, onFrameReady)
  document.addEventListener('visibilitychange', onVisibility)
  window.addEventListener('beforeunload', onBeforeUnload)
  window.addEventListener('pagehide', onPageHide)
  window.addEventListener('online', onOnline)
  ticker = setInterval(() => (now.value = Date.now()), 1000)
})

onBeforeRouteLeave(async () => {
  if (!saver) return true
  const s = saver
  await Promise.race([
    s.flush().catch(() => {}),
    new Promise((r) => setTimeout(r, LEAVE_FLUSH_TIMEOUT_MS)),
  ])
  if (s.snapshot.dirty) s.flushOnExit()
  return true
})

onBeforeUnmount(() => {
  stopFrameWatch?.()
  unsubscribeChanges()
  saver?.dispose()
  saver = null
  document.removeEventListener('visibilitychange', onVisibility)
  window.removeEventListener('beforeunload', onBeforeUnload)
  window.removeEventListener('pagehide', onPageHide)
  window.removeEventListener('online', onOnline)
  if (ticker) clearInterval(ticker)
})

// ---------------------------------------------------------------- acciones de la barra

async function rename() {
  const p = project.value
  const name = nameDraft.value.trim()
  if (!p || readOnly.value) return
  if (!name || name === p.name) {
    nameDraft.value = p.name
    return
  }
  try {
    const updated = await projectsApi.rename(p.id, name)
    project.value = { ...p, name: updated.name, updated_at: updated.updated_at }
    nameDraft.value = updated.name
  } catch (e) {
    nameDraft.value = p.name
    notice.value = { kind: 'danger', text: errorMessage(e) }
  }
}

/** Guarda lo pendiente; lanza si quedó sin guardar. */
async function ensureSaved(): Promise<void> {
  if (!saver) return
  await saver.flush()
  const st = saver.snapshot.status
  if (st === 'conflict' || st === 'offline' || st === 'error') {
    throw new Error(statusText.value)
  }
}

async function saveVersion() {
  const p = project.value
  if (!p) return
  busy.value = 'version'
  notice.value = null
  try {
    await ensureSaved()
    const updated = await projectsApi.createVersion(p.id)
    setProject(updated)
    saver?.rebase(baseOf(updated))
    notice.value = {
      kind: 'success',
      text: t('projects.fpga.versionSaved', { n: updated.current_version_n }),
    }
  } catch (e) {
    notice.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busy.value = null
  }
}

async function openVersions() {
  const p = project.value
  if (!p) return
  showVersions.value = true
  versions.value = null
  versionsError.value = null
  confirmRestoreId.value = null
  try {
    versions.value = await projectsApi.listVersions(p.id)
  } catch (e) {
    versionsError.value = errorMessage(e)
  }
}

/** Sustituye lo abierto por un proyecto del servidor (recargar tras conflicto, restaurar). */
function adoptServerProject(p: Project) {
  setProject(p)
  latest = p.content
  if (jg.value) loadIntoFrame(jg.value, p.content, false)
  saver?.reset(baseOf(p))
}

async function restoreVersion(v: ProjectVersion) {
  const p = project.value
  if (!p) return
  busy.value = v.id
  try {
    await saver?.flush().catch(() => {})
    const restored = await projectsApi.restore(p.id, v.id)
    adoptServerProject(restored)
    showVersions.value = false
    notice.value = { kind: 'success', text: t('projects.fpga.restored', { n: v.n }) }
  } catch (e) {
    versionsError.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

async function conflictReload() {
  const p = project.value
  if (!p) return
  busy.value = 'conflict'
  try {
    adoptServerProject(await projectsApi.get(p.id))
  } catch (e) {
    notice.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busy.value = null
  }
}

async function conflictOverwrite() {
  const p = project.value
  if (!p || !saver) return
  busy.value = 'conflict'
  try {
    const c = saver.snapshot.conflict
    if (
      c?.current_version !== undefined &&
      c.current_revision !== undefined &&
      c.current_version_id !== undefined
    ) {
      await saver.overwrite()
    } else {
      const fresh = await projectsApi.get(p.id)
      await saver.overwrite(baseOf(fresh))
    }
  } catch (e) {
    notice.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busy.value = null
  }
}

const submitContext = computed<FpgaSubmitContext | null>(() => {
  const p = project.value
  const a = jg.value
  if (!p || !a) return null
  return {
    project: p,
    jgfpga: {
      getReport: () => a.getReport(),
      getReportDocx: () => a.getReportDocx(),
      getLastBitstream: () => a.getLastBitstream(),
    },
    query: Object.fromEntries(
      Object.entries(route.query).filter((e): e is [string, string] => typeof e[1] === 'string'),
    ),
    prepareVersion: async () => {
      await ensureSaved()
      return { project_id: p.id, version_id: saver?.currentBase.version ?? p.current_version_id }
    },
  }
})

function goBack() {
  const back = (window.history.state as { back?: unknown } | null)?.back
  if (typeof back === 'string' && back) {
    router.back()
    return
  }
  if (project.value) void router.push({ name: 'project', params: { id: project.value.id } })
  else void router.push({ name: 'projects' })
}

function exitReadOnly() {
  if (projectId.value) void router.push({ name: 'fpga', params: { projectId: projectId.value } })
}
</script>

<template>
  <div class="fw">
    <header class="fw-bar">
      <LdButton variant="ghost" size="sm" class="fw-bar__back" data-test="back" @click="goBack">
        ← {{ t('projects.fpga.back') }}
      </LdButton>

      <div class="fw-bar__name">
        <label v-if="project && !readOnly" class="fw-bar__name-field">
          <span class="ld-visually-hidden">{{ t('projects.fpga.nameLabel') }}</span>
          <input
            v-model="nameDraft"
            type="text"
            maxlength="120"
            data-test="project-name"
            @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
            @blur="rename"
          />
        </label>
        <strong v-else-if="project" class="fw-bar__name-text">{{ project.name }}</strong>
        <span
          class="fw-status"
          :class="`fw-status--${statusKind}`"
          role="status"
          aria-live="polite"
          data-test="save-status"
        >
          <LdSpinner v-if="snap?.status === 'saving' || phase !== 'ready'" size="sm" decorative />
          {{ statusText }}
        </span>
      </div>

      <div class="fw-bar__actions">
        <template v-if="!readOnly">
          <LdButton
            size="sm"
            variant="secondary"
            :disabled="phase !== 'ready'"
            :loading="busy === 'version'"
            data-test="save-version"
            @click="saveVersion"
            >{{ t('projects.fpga.saveVersion') }}</LdButton
          >
          <LdButton
            size="sm"
            variant="secondary"
            :disabled="phase !== 'ready'"
            data-test="versions"
            @click="openVersions"
            >{{ t('projects.fpga.versions') }}</LdButton
          >
          <LdButton
            size="sm"
            variant="accent"
            :disabled="phase !== 'ready'"
            data-test="submit"
            @click="showSubmit = true"
            >{{ t('projects.fpga.submit') }}</LdButton
          >
        </template>
        <LdButton
          v-else-if="projectId && !submissionId"
          size="sm"
          variant="secondary"
          data-test="exit-readonly"
          @click="exitReadOnly"
          >{{ t('projects.fpga.readOnlyExit') }}</LdButton
        >
      </div>
    </header>

    <LdAlert
      v-if="snap?.status === 'conflict'"
      variant="warning"
      :title="t('projects.fpga.conflictTitle')"
      data-test="conflict"
      class="fw-alert"
    >
      {{ t('projects.fpga.conflictBody') }}
      <template #actions>
        <LdButton
          size="sm"
          :loading="busy === 'conflict'"
          data-test="conflict-reload"
          @click="conflictReload"
          >{{ t('projects.fpga.conflictReload') }}</LdButton
        >
        <LdButton
          size="sm"
          variant="secondary"
          :disabled="busy === 'conflict'"
          data-test="conflict-overwrite"
          @click="conflictOverwrite"
          >{{ t('projects.fpga.conflictOverwrite') }}</LdButton
        >
      </template>
    </LdAlert>
    <LdAlert v-if="fatal" variant="danger" class="fw-alert" data-test="fatal">{{ fatal }}</LdAlert>
    <LdAlert
      v-if="notice"
      :variant="notice.kind"
      dismissible
      class="fw-alert"
      data-test="notice"
      @dismiss="notice = null"
      >{{ notice.text }}</LdAlert
    >

    <iframe
      ref="frame"
      class="fw-frame"
      :src="frameSrc"
      :title="t('projects.fpga.frameTitle')"
      allow="clipboard-read; clipboard-write; fullscreen"
      data-test="fpga-frame"
    />

    <FpgaDialog
      v-if="showVersions"
      :title="t('projects.fpga.versionsTitle')"
      @close="showVersions = false"
    >
      <LdSpinner v-if="!versions && !versionsError" />
      <LdAlert v-if="versionsError" variant="danger">{{ versionsError }}</LdAlert>
      <p v-if="versions && versions.length === 0" class="ld-muted">
        {{ t('projects.fpga.versionsEmpty') }}
      </p>
      <ul v-if="versions && project" class="fw-versions" data-test="versions-list">
        <li v-for="v in versions" :key="v.id">
          <div class="fw-versions__row">
            <span>
              <strong>{{ t('projects.detail.versionN', { n: v.n }) }}</strong>
              ·
              {{
                v.kind === 'manual'
                  ? t('projects.detail.kindManual')
                  : t('projects.detail.kindAutosave')
              }}
              <span v-if="v.id === project.current_version_id" class="fw-versions__current">{{
                t('projects.detail.current')
              }}</span>
              <br />
              <small class="ld-muted"
                >{{ formatDateTime(v.updated_at ?? v.created_at)
                }}<template v-if="v.label"> · {{ v.label }}</template></small
              >
            </span>
            <span class="ld-row">
              <LdButton
                size="sm"
                variant="ghost"
                :to="{
                  name: 'fpga',
                  params: { projectId: project.id },
                  query: { ver: v.id, readonly: '1' },
                }"
                >{{ t('projects.fpga.versionsOpen') }}</LdButton
              >
              <LdButton
                v-if="v.id !== project.current_version_id"
                size="sm"
                variant="secondary"
                data-test="version-restore"
                @click="confirmRestoreId = v.id"
                >{{ t('projects.fpga.versionsRestore') }}</LdButton
              >
            </span>
          </div>
          <div v-if="confirmRestoreId === v.id" class="fw-versions__confirm" role="alertdialog">
            <p>{{ t('projects.detail.confirmRestore', { n: v.n }) }}</p>
            <div class="ld-row">
              <LdButton
                size="sm"
                :loading="busy === v.id"
                data-test="version-restore-yes"
                @click="restoreVersion(v)"
                >{{ t('projects.detail.confirmRestoreYes') }}</LdButton
              >
              <LdButton size="sm" variant="ghost" @click="confirmRestoreId = null">{{
                t('common.cancel')
              }}</LdButton>
            </div>
          </div>
        </li>
      </ul>
      <template #footer>
        <LdButton
          v-if="project"
          variant="ghost"
          :to="{ name: 'project', params: { id: project.id } }"
          >{{ t('projects.fpga.versionsAll') }}</LdButton
        >
      </template>
    </FpgaDialog>

    <component
      :is="SubmitDialog"
      v-if="showSubmit && submitContext"
      :context="submitContext"
      @close="showSubmit = false"
    />
  </div>
</template>

<style scoped>
.fw {
  display: flex;
  flex-direction: column;
  height: 100vh;
  height: 100dvh;
  background: var(--ld-color-bg);
}

.fw-bar {
  flex: none;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2) var(--ld-space-3);
  min-height: var(--ld-header-h);
  padding: var(--ld-space-2) var(--ld-space-3);
  background: var(--ld-color-header-bg);
  color: var(--ld-color-header-text);
  box-shadow: var(--ld-shadow-md);
  z-index: var(--ld-z-header);
}

.fw-bar__back {
  --btn-fg: currentColor;
  --btn-bg-hover: rgb(255 255 255 / 0.12);
}

.fw-bar__name {
  flex: 1 1 14rem;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-1) var(--ld-space-3);
}

.fw-bar__name-field input {
  width: min(22rem, 100%);
  min-height: 2.25rem;
  padding: 0 var(--ld-space-2);
  border: 1px solid rgb(255 255 255 / 0.35);
  border-radius: var(--ld-radius-md);
  background: rgb(255 255 255 / 0.08);
  color: inherit;
  font-family: var(--ld-font-heading);
  font-weight: 600;
}

.fw-bar__name-field input:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 1px;
}

.fw-bar__name-text {
  font-family: var(--ld-font-heading);
  overflow-wrap: anywhere;
}

.fw-status {
  display: inline-flex;
  align-items: center;
  gap: var(--ld-space-1);
  font-size: var(--ld-text-sm);
  opacity: 0.92;
}

.fw-status::before {
  content: '';
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--um-lime);
}

.fw-status--busy::before {
  background: var(--um-gold);
}

.fw-status--bad::before {
  background: var(--lab-led);
}

.fw-status--readonly::before {
  background: var(--um-orange-300);
}

.fw-bar__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2);
}

.fw-bar__actions :deep(.ld-btn--secondary) {
  --btn-fg: currentColor;
  --btn-bg-hover: rgb(255 255 255 / 0.12);
}

.fw-alert {
  flex: none;
  margin: var(--ld-space-2) var(--ld-space-3) 0;
}

.fw-frame {
  flex: 1;
  width: 100%;
  min-height: 0;
  border: 0;
  background: var(--ld-color-surface);
}

.fw-versions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--ld-space-2);
}

.fw-versions li {
  padding: var(--ld-space-2) 0;
  border-bottom: 1px solid var(--ld-color-border);
}

.fw-versions__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-2);
}

.fw-versions__current {
  margin-left: var(--ld-space-1);
  padding: 0 var(--ld-space-2);
  border-radius: var(--ld-radius-full);
  background: var(--ld-color-success-bg);
  color: var(--ld-color-success);
  font-size: var(--ld-text-xs);
}

.fw-versions__confirm {
  margin-top: var(--ld-space-2);
}
</style>
