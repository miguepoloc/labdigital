<script setup lang="ts">
/**
 * Equipos de un lab (docente, LD-18): crear uno o varios, renombrar, eliminar, mover estudiantes entre
 * equipos o asignar a quienes no tienen, repartir al azar y fijar/quitar fijación.
 */
import { computed, onMounted, ref } from 'vue'
import { teamsApi, type Lab, type Team, type TeamMember } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdBadge from '@/components/LdBadge.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import ConfirmDialog from '../courses/ConfirmDialog.vue'
import MemberMove from './MemberMove.vue'
import TeamFormDialog from './TeamFormDialog.vue'
import TeamsBulkDialog from './TeamsBulkDialog.vue'
import { isFull, moveOptions, suggestedTeamCount, teamsErrorMessage } from './teamsAdmin'

const props = defineProps<{ lab: Lab }>()

type Dialog =
  | { kind: 'create' }
  | { kind: 'bulk' }
  | { kind: 'rename'; team: Team }
  | { kind: 'delete'; team: Team }

const teams = ref<Team[]>([])
const unassigned = ref<TeamMember[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
/** Qué operación está en curso (id de equipo/estudiante o nombre de la acción). */
const busy = ref<string | null>(null)
const dialog = ref<Dialog | null>(null)
const dialogError = ref<string | null>(null)

const maxSize = computed(() => props.lab.max_team_size)
const suggested = computed(() => suggestedTeamCount(unassigned.value.length, maxSize.value))
const assignOptions = computed(() => moveOptions(teams.value, maxSize.value))
const canAutoAssign = computed(
  () =>
    unassigned.value.length > 0 &&
    teams.value.some((tm) => !tm.locked && !isFull(tm, maxSize.value)),
)

async function load() {
  error.value = null
  try {
    const [tms, free] = await Promise.all([
      teamsApi.list(props.lab.id),
      teamsApi.unassigned(props.lab.id),
    ])
    teams.value = tms
    unassigned.value = free
  } catch (e) {
    error.value = teamsErrorMessage(e)
  } finally {
    loading.value = false
  }
}

/** Ejecuta una acción con su indicador de espera; recarga y muestra el resultado. */
async function run(key: string, action: () => Promise<string>) {
  status.value = null
  busy.value = key
  try {
    const text = await action()
    await load()
    status.value = { kind: 'success', text }
  } catch (e) {
    status.value = { kind: 'danger', text: teamsErrorMessage(e) }
  } finally {
    busy.value = null
  }
}

/** Igual que `run`, pero el error se muestra dentro del diálogo abierto (que sigue abierto). */
async function runDialog(action: () => Promise<string>) {
  dialogError.value = null
  busy.value = 'dialog'
  try {
    const text = await action()
    dialog.value = null
    await load()
    status.value = { kind: 'success', text }
  } catch (e) {
    dialogError.value = teamsErrorMessage(e)
  } finally {
    busy.value = null
  }
}

function open(next: Dialog) {
  status.value = null
  dialogError.value = null
  dialog.value = next
}

function createTeam({ name, memberIds }: { name: string; memberIds: string[] }) {
  return runDialog(async () => {
    const team = await teamsApi.createAsTeacher(props.lab.id, { name, member_ids: memberIds })
    return t('teams.newTeamDone', { name: team.name })
  })
}

function createBulk(body: { count: number; prefix: string }) {
  return runDialog(async () => {
    const created = await teamsApi.bulk(props.lab.id, body)
    return created.length ? t('teams.bulkDone', { n: created.length }) : t('teams.bulkNone')
  })
}

function rename(team: Team, { name }: { name: string }) {
  return runDialog(async () => {
    const renamed = await teamsApi.rename(team.id, name)
    return t('teams.renamed', { name: renamed.name })
  })
}

function remove(team: Team) {
  return runDialog(async () => {
    await teamsApi.remove(team.id)
    return t('teams.deleted', { name: team.name })
  })
}

function toggleLock(team: Team) {
  return run(`lock:${team.id}`, async () => {
    if (team.locked) {
      await teamsApi.unlock(team.id)
      return t('teams.unlockedDone', { name: team.name })
    }
    await teamsApi.lock(team.id)
    return t('teams.lockedDone', { name: team.name })
  })
}

/** Mover o asignar: el backend saca al estudiante de su equipo anterior en la misma operación. */
function moveTo(student: TeamMember, targetId: string) {
  const target = teams.value.find((tm) => tm.id === targetId)
  if (!target) return
  return run(`member:${student.id}`, async () => {
    await teamsApi.setMembers(target.id, [...target.members.map((m) => m.id), student.id])
    return t('teams.moved', { student: student.full_name, team: target.name })
  })
}

function removeMember(team: Team, student: TeamMember) {
  return run(`member:${student.id}`, async () => {
    const rest = team.members.filter((m) => m.id !== student.id).map((m) => m.id)
    await teamsApi.setMembers(team.id, rest)
    return t('teams.removedMember', { student: student.full_name })
  })
}

function autoAssign() {
  return run('auto', async () => {
    await teamsApi.autoAssign(props.lab.id)
    const left = (await teamsApi.unassigned(props.lab.id)).length
    return left ? t('teams.autoAssignDone', { n: left }) : t('teams.autoAssignAll')
  })
}

function membersLabel(team: Team) {
  return maxSize.value
    ? t('teams.members', { n: team.members.length, max: maxSize.value })
    : t('teams.membersNoMax', { n: team.members.length })
}

onMounted(load)
</script>

<template>
  <div class="ld-stack" data-test="teams-admin">
    <p class="ld-muted">{{ t('teams.adminHelp') }}</p>
    <div class="ld-row ld-tadmin__toolbar">
      <LdButton data-test="team-new" @click="open({ kind: 'create' })">
        {{ t('teams.newTeam') }}
      </LdButton>
      <LdButton variant="secondary" data-test="team-bulk" @click="open({ kind: 'bulk' })">
        {{ t('teams.bulk') }}
      </LdButton>
      <LdButton
        variant="ghost"
        :disabled="!canAutoAssign"
        :loading="busy === 'auto'"
        :title="t('teams.autoAssignHelp')"
        data-test="team-auto"
        @click="autoAssign"
      >
        {{ t('teams.autoAssign') }}
      </LdButton>
    </div>
    <div aria-live="polite">
      <LdAlert v-if="status" :variant="status.kind" data-test="teams-status">{{
        status.text
      }}</LdAlert>
    </div>
    <LdSpinner v-if="loading" :label="t('common2.loading')" />
    <LdAlert v-else-if="error" variant="danger">{{ error }}</LdAlert>
    <div v-else class="ld-tadmin">
      <LdCard
        :title="t('teams.panelTitle')"
        :heading-level="3"
        class="ld-tadmin__teams"
        data-test="teams-list"
      >
        <LdEmptyState
          v-if="teams.length === 0"
          :title="t('teams.adminEmpty')"
          :body="t('teams.adminEmptyBody')"
        />
        <ul v-else class="ld-tadmin__list">
          <li v-for="team in teams" :key="team.id" class="ld-tadmin__item" data-test="team-item">
            <div class="ld-tadmin__head">
              <p class="ld-tadmin__name">
                <strong data-test="team-name">{{ team.name }}</strong>
                <span v-if="team.join_code" class="ld-muted">
                  {{ t('teams.codeLabel', { code: team.join_code }) }}
                </span>
                <LdBadge v-if="team.locked" tone="info">{{ t('teams.locked') }}</LdBadge>
                <LdBadge v-if="isFull(team, maxSize)" tone="neutral">{{ t('teams.full') }}</LdBadge>
              </p>
              <div class="ld-row ld-tadmin__actions">
                <LdButton
                  size="sm"
                  variant="ghost"
                  :aria-label="t('teams.renameLabel', { name: team.name })"
                  data-test="team-rename"
                  @click="open({ kind: 'rename', team })"
                >
                  {{ t('teams.rename') }}
                </LdButton>
                <LdButton
                  size="sm"
                  variant="ghost"
                  :loading="busy === `lock:${team.id}`"
                  :aria-label="
                    t(team.locked ? 'teams.unlockLabel' : 'teams.lockLabel', { name: team.name })
                  "
                  data-test="team-lock"
                  @click="toggleLock(team)"
                >
                  {{ team.locked ? t('teams.unlock') : t('teams.lock') }}
                </LdButton>
                <LdButton
                  size="sm"
                  variant="ghost"
                  class="ld-tadmin__danger"
                  :aria-label="t('teams.deleteLabel', { name: team.name })"
                  data-test="team-delete"
                  @click="open({ kind: 'delete', team })"
                >
                  {{ t('teams.delete') }}
                </LdButton>
              </div>
            </div>
            <p class="ld-muted ld-tadmin__count">{{ membersLabel(team) }}</p>
            <p v-if="team.members.length === 0" class="ld-muted ld-tadmin__count">
              {{ t('teams.emptyTeam') }}
            </p>
            <ul v-else class="ld-tadmin__members">
              <li
                v-for="m in team.members"
                :key="m.id"
                class="ld-tadmin__member"
                data-test="team-member"
              >
                <span>{{ m.full_name }}</span>
                <div class="ld-row ld-tadmin__member-actions">
                  <MemberMove
                    :options="moveOptions(teams, maxSize, team.id)"
                    :placeholder="t('teams.moveTo')"
                    :select-label="t('teams.moveToLabel', { student: m.full_name })"
                    :submit-text="t('teams.moveSubmit')"
                    :submit-label="t('teams.moveSubmitLabel', { student: m.full_name })"
                    :busy="busy === `member:${m.id}`"
                    @move="moveTo(m, $event)"
                  />
                  <LdButton
                    size="sm"
                    variant="ghost"
                    :disabled="busy === `member:${m.id}`"
                    :aria-label="
                      t('teams.removeMemberLabel', { student: m.full_name, team: team.name })
                    "
                    data-test="member-remove"
                    @click="removeMember(team, m)"
                  >
                    {{ t('teams.removeMember') }}
                  </LdButton>
                </div>
              </li>
            </ul>
          </li>
        </ul>
      </LdCard>

      <LdCard
        :title="t('teams.unassignedTitle')"
        :heading-level="3"
        class="ld-tadmin__free"
        data-test="unassigned"
      >
        <p class="ld-muted ld-tadmin__count">
          {{
            unassigned.length
              ? t('teams.unassignedCount', { n: unassigned.length })
              : t('teams.unassignedEmpty')
          }}
        </p>
        <ul v-if="unassigned.length" class="ld-tadmin__members">
          <li
            v-for="s in unassigned"
            :key="s.id"
            class="ld-tadmin__member"
            data-test="unassigned-student"
          >
            <span>{{ s.full_name }}</span>
            <MemberMove
              v-if="teams.length"
              :options="assignOptions"
              :placeholder="t('teams.assignTo')"
              :select-label="t('teams.assignToLabel', { student: s.full_name })"
              :submit-text="t('teams.assignSubmit')"
              :submit-label="t('teams.assignSubmitLabel', { student: s.full_name })"
              :busy="busy === `member:${s.id}`"
              @move="moveTo(s, $event)"
            />
          </li>
        </ul>
      </LdCard>
    </div>

    <TeamFormDialog
      v-if="dialog?.kind === 'create'"
      :title="t('teams.newTeamTitle')"
      :save-label="t('teams.newTeamSave')"
      :candidates="unassigned"
      :max-size="maxSize"
      :busy="busy === 'dialog'"
      :error="dialogError"
      @save="createTeam"
      @cancel="dialog = null"
    />
    <TeamFormDialog
      v-else-if="dialog?.kind === 'rename'"
      :title="t('teams.renameTitle', { name: dialog.team.name })"
      :save-label="t('teams.renameSave')"
      :initial-name="dialog.team.name"
      :busy="busy === 'dialog'"
      :error="dialogError"
      @save="rename(dialog.team, $event)"
      @cancel="dialog = null"
    />
    <TeamsBulkDialog
      v-else-if="dialog?.kind === 'bulk'"
      :suggested="suggested"
      :busy="busy === 'dialog'"
      :error="dialogError"
      @save="createBulk"
      @cancel="dialog = null"
    />
    <ConfirmDialog
      v-else-if="dialog?.kind === 'delete'"
      :title="t('teams.deleteTitle', { name: dialog.team.name })"
      :message="dialogError ?? t('teams.deleteConfirm')"
      :confirm-label="t('teams.delete')"
      danger
      :busy="busy === 'dialog'"
      @confirm="remove(dialog.team)"
      @cancel="dialog = null"
    />
  </div>
</template>

<style scoped>
.ld-tadmin {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--ld-space-4);
  align-items: start;
}

@media (min-width: 60rem) {
  .ld-tadmin {
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  }
}

.ld-tadmin__toolbar {
  flex-wrap: wrap;
}

.ld-tadmin__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
}

.ld-tadmin__item {
  padding: var(--ld-space-3) var(--ld-space-4);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  background: var(--ld-color-surface);
}

.ld-tadmin__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-2);
}

.ld-tadmin__name {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
}

.ld-tadmin__actions,
.ld-tadmin__member-actions {
  flex-wrap: wrap;
  gap: var(--ld-space-1);
}

.ld-tadmin__danger {
  color: var(--ld-color-danger);
}

.ld-tadmin__count {
  margin: var(--ld-space-1) 0 0;
  font-size: var(--ld-text-sm);
}

.ld-tadmin__members {
  list-style: none;
  margin: var(--ld-space-2) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
}

.ld-tadmin__member {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-2);
  padding: var(--ld-space-2) var(--ld-space-3);
  border-radius: var(--ld-radius-sm);
  background: var(--ld-color-surface-2);
}
</style>
