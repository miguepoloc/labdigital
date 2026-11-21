<script setup lang="ts">
/** `/app/proyectos/:id` (LD-8a): datos del proyecto e historial de versiones con "Ver" y "Restaurar". */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { isApiError } from '@/api/errors'
import { projectsApi, type Project, type ProjectVersion } from '@/api/projects'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import { errorMessage } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import { formatBytes } from './format'

const route = useRoute()
const id = computed(() => String(route.params.id))

const project = ref<Project | null>(null)
const versions = ref<ProjectVersion[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const notFound = ref(false)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const confirmingId = ref<string | null>(null)
const busy = ref<string | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  notFound.value = false
  try {
    const [p, vs] = await Promise.all([
      projectsApi.get(id.value),
      projectsApi.listVersions(id.value),
    ])
    project.value = p
    versions.value = vs
  } catch (e) {
    if (isApiError(e) && (e.status === 404 || e.status === 403)) notFound.value = true
    else loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function refreshAfterChange() {
  const [p, vs] = await Promise.all([projectsApi.get(id.value), projectsApi.listVersions(id.value)])
  project.value = p
  versions.value = vs
}

async function saveVersion() {
  status.value = null
  busy.value = 'save'
  try {
    const updated = await projectsApi.createVersion(id.value)
    await refreshAfterChange()
    status.value = {
      kind: 'success',
      text: t('projects.detail.versionSaved', { n: updated.current_version_n }),
    }
  } catch (e) {
    status.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busy.value = null
  }
}

async function restore(v: ProjectVersion) {
  status.value = null
  busy.value = v.id
  try {
    const p = await projectsApi.restore(id.value, v.id)
    await refreshAfterChange()
    confirmingId.value = null
    status.value = {
      kind: 'success',
      text: t('projects.detail.restored', { n: v.n, m: p.current_version_n }),
    }
  } catch (e) {
    status.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busy.value = null
  }
}

watch(id, load, { immediate: true })
</script>

<template>
  <div class="ld-stack ld-project">
    <p class="ld-project__back">
      <RouterLink :to="{ name: 'projects' }">← {{ t('projects.detail.back') }}</RouterLink>
    </p>

    <LdSpinner v-if="loading" size="lg" />
    <LdAlert v-else-if="notFound" variant="warning" data-test="not-found">{{
      t('projects.detail.notFound')
    }}</LdAlert>
    <LdAlert v-else-if="loadError" variant="danger">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{
          t('projects.list.reload')
        }}</LdButton>
      </template>
    </LdAlert>
    <template v-else-if="project">
      <header class="ld-project__head">
        <div>
          <h1 data-test="project-name">{{ project.name }}</h1>
          <p class="ld-muted">
            {{ t(`projects.modules.${project.module}`) }} ·
            {{ t('projects.list.lastEdit', { date: formatDateTime(project.updated_at) }) }}
          </p>
        </div>
        <div class="ld-row">
          <LdButton :to="{ name: 'fpga', params: { projectId: project.id } }">{{
            t('projects.detail.openSimulator')
          }}</LdButton>
          <LdButton
            variant="secondary"
            :loading="busy === 'save'"
            data-test="save-version"
            @click="saveVersion"
            >{{ t('projects.detail.saveVersion') }}</LdButton
          >
        </div>
      </header>

      <LdAlert v-if="status" :variant="status.kind" data-test="status">{{ status.text }}</LdAlert>

      <LdCard :title="t('projects.detail.versionsTitle')">
        <p class="ld-muted">{{ t('projects.detail.versionsHelp') }}</p>
        <div class="ld-project__tbl">
          <table>
            <thead>
              <tr>
                <th scope="col">{{ t('projects.detail.colVersion') }}</th>
                <th scope="col">{{ t('projects.detail.colKind') }}</th>
                <th scope="col">{{ t('projects.detail.colDate') }}</th>
                <th scope="col">{{ t('projects.detail.colSize') }}</th>
                <th scope="col">
                  <span class="ld-visually-hidden">{{ t('projects.detail.colActions') }}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <template v-for="v in versions" :key="v.id">
                <tr data-test="version-row">
                  <td>
                    <strong>{{ t('projects.detail.versionN', { n: v.n }) }}</strong>
                    <span
                      v-if="v.id === project.current_version_id"
                      class="ld-project__current"
                      data-test="current"
                      >{{ t('projects.detail.current') }}</span
                    >
                  </td>
                  <td>
                    <span class="ld-project__kind" :class="`ld-project__kind--${v.kind}`">{{
                      v.kind === 'manual'
                        ? t('projects.detail.kindManual')
                        : t('projects.detail.kindAutosave')
                    }}</span>
                    <span v-if="v.label" class="ld-project__label">{{ v.label }}</span>
                  </td>
                  <td>{{ formatDateTime(v.updated_at ?? v.created_at) }}</td>
                  <td>{{ formatBytes(v.size) }}</td>
                  <td class="ld-project__acts">
                    <LdButton
                      size="sm"
                      variant="ghost"
                      :to="{
                        name: 'fpga',
                        params: { projectId: project.id },
                        query: { ver: v.id, readonly: '1' },
                      }"
                      :aria-label="t('projects.detail.viewLabel', { n: v.n })"
                      data-test="view"
                      >{{ t('projects.detail.view') }}</LdButton
                    >
                    <LdButton
                      v-if="v.id !== project.current_version_id"
                      size="sm"
                      variant="secondary"
                      data-test="restore"
                      @click="confirmingId = v.id"
                      >{{ t('projects.detail.restore') }}</LdButton
                    >
                  </td>
                </tr>
                <tr v-if="confirmingId === v.id" class="ld-project__confirm-row">
                  <td colspan="5">
                    <div role="alertdialog" data-test="confirm-restore">
                      <p>{{ t('projects.detail.confirmRestore', { n: v.n }) }}</p>
                      <div class="ld-row">
                        <LdButton
                          size="sm"
                          :loading="busy === v.id"
                          data-test="confirm-restore-yes"
                          @click="restore(v)"
                          >{{ t('projects.detail.confirmRestoreYes') }}</LdButton
                        >
                        <LdButton size="sm" variant="ghost" @click="confirmingId = null">{{
                          t('common.cancel')
                        }}</LdButton>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </LdCard>
    </template>
  </div>
</template>

<style scoped>
.ld-project__back {
  margin: 0;
}

.ld-project__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ld-space-3);
}

.ld-project__head h1 {
  overflow-wrap: anywhere;
}

.ld-project__tbl {
  overflow-x: auto;
}

.ld-project__tbl table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--ld-text-sm);
  font-variant-numeric: tabular-nums;
}

.ld-project__tbl th,
.ld-project__tbl td {
  text-align: left;
  padding: var(--ld-space-2) var(--ld-space-3);
  border-bottom: 1px solid var(--ld-color-border);
  vertical-align: middle;
}

.ld-project__tbl th {
  font-size: var(--ld-text-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ld-color-text-muted);
  background: var(--ld-color-surface-2);
}

.ld-project__current,
.ld-project__kind {
  display: inline-block;
  margin-left: var(--ld-space-2);
  padding: 1px var(--ld-space-2);
  border-radius: var(--ld-radius-full);
  font-size: var(--ld-text-xs);
  font-weight: 500;
}

.ld-project__kind {
  margin-left: 0;
  background: var(--ld-color-surface-2);
  color: var(--ld-color-text-muted);
}

.ld-project__kind--manual {
  background: var(--ld-color-info-bg);
  color: var(--ld-color-info);
}

.ld-project__current {
  background: var(--ld-color-success-bg);
  color: var(--ld-color-success);
}

.ld-project__label {
  display: block;
  color: var(--ld-color-text-muted);
}

.ld-project__acts {
  white-space: nowrap;
  text-align: right;
}

.ld-project__acts > * + * {
  margin-left: var(--ld-space-2);
}

.ld-project__confirm-row td {
  background: var(--ld-color-warning-bg);
}
</style>
