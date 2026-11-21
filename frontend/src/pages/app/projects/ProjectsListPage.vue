<script setup lang="ts">
/** `/app/proyectos` (LD-8a): lista, crear, renombrar y borrar (con confirmación en la propia página). */
import { nextTick, onMounted, ref } from 'vue'
import { projectsApi, starterFpgaContent, type ProjectSummary } from '@/api/projects'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import { errorMessage, fieldErrors } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'

const items = ref<ProjectSummary[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)

const newName = ref('')
const newNameError = ref<string | null>(null)
const creating = ref(false)

const renamingId = ref<string | null>(null)
const renameValue = ref('')
const renameError = ref<string | null>(null)
const confirmingId = ref<string | null>(null)
const busyId = ref<string | null>(null)
const renameField = ref<InstanceType<typeof LdTextField>[] | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    items.value = await projectsApi.list('fpga')
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function create() {
  status.value = null
  newNameError.value = null
  const name = newName.value.trim()
  if (!name) {
    newNameError.value = t('validation.required')
    return
  }
  creating.value = true
  try {
    const p = await projectsApi.create({ name, module: 'fpga', content: starterFpgaContent(name) })
    items.value = [p, ...items.value.filter((x) => x.id !== p.id)]
    newName.value = ''
    status.value = { kind: 'success', text: t('projects.list.created', { name: p.name }) }
  } catch (e) {
    newNameError.value = fieldErrors(e).name ?? null
    if (!newNameError.value) status.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    creating.value = false
  }
}

async function startRename(p: ProjectSummary) {
  confirmingId.value = null
  renamingId.value = p.id
  renameValue.value = p.name
  renameError.value = null
  await nextTick()
  renameField.value?.[0]?.focus()
}

async function saveRename(p: ProjectSummary) {
  const name = renameValue.value.trim()
  if (!name) {
    renameError.value = t('validation.required')
    return
  }
  status.value = null
  busyId.value = p.id
  try {
    const updated = await projectsApi.rename(p.id, name)
    items.value = items.value.map((x) =>
      x.id === p.id ? { ...x, name: updated.name, updated_at: updated.updated_at } : x,
    )
    renamingId.value = null
    status.value = { kind: 'success', text: t('projects.list.renamed') }
  } catch (e) {
    renameError.value = fieldErrors(e).name ?? errorMessage(e)
  } finally {
    busyId.value = null
  }
}

async function remove(p: ProjectSummary) {
  status.value = null
  busyId.value = p.id
  try {
    await projectsApi.remove(p.id)
    items.value = items.value.filter((x) => x.id !== p.id)
    confirmingId.value = null
    status.value = { kind: 'success', text: t('projects.list.removed', { name: p.name }) }
  } catch (e) {
    status.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busyId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="ld-stack ld-projects">
    <header>
      <h1>{{ t('projects.list.title') }}</h1>
      <p class="ld-muted">{{ t('projects.list.subtitle') }}</p>
    </header>

    <LdCard :title="t('projects.list.createTitle')">
      <form class="ld-projects__create" novalidate data-test="create-form" @submit.prevent="create">
        <LdTextField
          v-model="newName"
          name="name"
          :label="t('projects.list.createLabel')"
          :error="newNameError"
          required
        />
        <LdButton type="submit" :loading="creating">{{ t('projects.list.createSubmit') }}</LdButton>
      </form>
    </LdCard>

    <LdAlert v-if="status" :variant="status.kind" data-test="status">{{ status.text }}</LdAlert>

    <LdSpinner v-if="loading" size="lg" />
    <LdAlert v-else-if="loadError" variant="danger">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{
          t('projects.list.reload')
        }}</LdButton>
      </template>
    </LdAlert>
    <LdCard v-else-if="items.length === 0" :padded="true">
      <LdEmptyState :title="t('projects.list.empty')" :body="t('projects.list.emptyBody')" />
      <p class="ld-projects__empty-cta">
        <LdButton variant="secondary" :to="{ name: 'fpga' }">{{
          t('projects.list.openSimulatorNew')
        }}</LdButton>
      </p>
    </LdCard>
    <ul v-else class="ld-projects__list">
      <li v-for="p in items" :key="p.id" data-test="project-item">
        <LdCard as="article">
          <div class="ld-projects__item">
            <div class="ld-projects__info">
              <h2 class="ld-projects__name">
                <RouterLink :to="{ name: 'project', params: { id: p.id } }">{{
                  p.name
                }}</RouterLink>
                <span class="ld-projects__module" :title="t('projects.list.module')">{{
                  t(`projects.modules.${p.module}`)
                }}</span>
              </h2>
              <p class="ld-muted ld-projects__meta">
                {{ t('projects.list.lastEdit', { date: formatDateTime(p.updated_at) }) }}
              </p>
            </div>
            <div class="ld-row ld-projects__actions">
              <LdButton
                size="sm"
                :to="{ name: 'fpga', params: { projectId: p.id } }"
                data-test="open"
                >{{ t('projects.list.open') }}</LdButton
              >
              <LdButton
                size="sm"
                variant="secondary"
                data-test="rename"
                :disabled="busyId === p.id"
                @click="startRename(p)"
                >{{ t('projects.list.rename') }}</LdButton
              >
              <LdButton
                size="sm"
                variant="ghost"
                data-test="remove"
                :disabled="busyId === p.id"
                @click="((confirmingId = p.id), (renamingId = null))"
                >{{ t('projects.list.remove') }}</LdButton
              >
            </div>
          </div>

          <form
            v-if="renamingId === p.id"
            class="ld-projects__inline"
            novalidate
            data-test="rename-form"
            @submit.prevent="saveRename(p)"
          >
            <LdTextField
              ref="renameField"
              v-model="renameValue"
              name="rename"
              :label="t('projects.list.renameLabel', { name: p.name })"
              :error="renameError"
              required
            />
            <div class="ld-row">
              <LdButton type="submit" size="sm" :loading="busyId === p.id">{{
                t('projects.list.renameSave')
              }}</LdButton>
              <LdButton size="sm" variant="ghost" @click="renamingId = null">{{
                t('common.cancel')
              }}</LdButton>
            </div>
          </form>

          <div
            v-if="confirmingId === p.id"
            class="ld-projects__confirm"
            role="alertdialog"
            :aria-label="t('projects.list.remove')"
            data-test="confirm-remove"
          >
            <p>{{ t('projects.list.confirmRemove', { name: p.name }) }}</p>
            <div class="ld-row">
              <LdButton
                size="sm"
                variant="danger"
                :loading="busyId === p.id"
                data-test="confirm-remove-yes"
                @click="remove(p)"
                >{{ t('projects.list.confirmRemoveYes') }}</LdButton
              >
              <LdButton size="sm" variant="ghost" @click="confirmingId = null">{{
                t('common.cancel')
              }}</LdButton>
            </div>
          </div>
        </LdCard>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.ld-projects__create {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--ld-space-3);
}

.ld-projects__create > :first-child {
  flex: 1 1 16rem;
}

.ld-projects__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--ld-space-3);
}

.ld-projects__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-3);
}

.ld-projects__info {
  min-width: 0;
}

.ld-projects__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
  margin: 0;
  font-size: var(--ld-text-lg);
  overflow-wrap: anywhere;
}

.ld-projects__module {
  font-family: var(--ld-font-body);
  font-size: var(--ld-text-xs);
  font-weight: 500;
  padding: 2px var(--ld-space-2);
  border-radius: var(--ld-radius-full);
  background: color-mix(in srgb, var(--ld-color-pcb) 16%, transparent);
  color: var(--ld-color-pcb);
}

.ld-projects__meta {
  margin: var(--ld-space-1) 0 0;
  font-size: var(--ld-text-sm);
}

.ld-projects__inline,
.ld-projects__confirm {
  margin-top: var(--ld-space-3);
  padding-top: var(--ld-space-3);
  border-top: 1px solid var(--ld-color-border);
}

.ld-projects__confirm p {
  color: var(--ld-color-danger);
}

.ld-projects__empty-cta {
  display: flex;
  justify-content: center;
  margin: var(--ld-space-3) 0 0;
}
</style>
