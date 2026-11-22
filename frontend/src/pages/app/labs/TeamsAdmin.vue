<script setup lang="ts">
/** Equipos de un lab (docente): ver, reasignar integrantes y fijar. */
import { computed, onMounted, ref } from 'vue'
import { coursesApi, teamsApi, type Lab, type Member, type Team } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdBadge from '@/components/LdBadge.vue'
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import { courseErrorMessage } from '../courses/courseErrors'

const props = defineProps<{ lab: Lab }>()

const teams = ref<Team[]>([])
const students = ref<Member[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const busy = ref<string | null>(null)
const editing = ref<Team | null>(null)
const selection = ref<string[]>([])

const teamOf = computed(() => {
  const map = new Map<string, Team>()
  for (const tm of teams.value) for (const m of tm.members) map.set(m.id, tm)
  return map
})
const withoutTeam = computed(() => students.value.filter((s) => !teamOf.value.has(s.user_id)))

async function load() {
  loading.value = true
  error.value = null
  try {
    const [tms, members] = await Promise.all([
      teamsApi.list(props.lab.id),
      coursesApi.members(props.lab.course_id, 'active'),
    ])
    teams.value = tms
    students.value = members.filter((m) => m.role === 'estudiante')
  } catch (e) {
    error.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

function replace(team: Team | undefined, fallback: Team, patch?: Partial<Team>) {
  const next = team ?? { ...fallback, ...patch }
  teams.value = teams.value.map((x) => (x.id === next.id ? next : x))
}

async function lock(team: Team) {
  status.value = null
  busy.value = team.id
  try {
    replace(await teamsApi.lock(team.id), team, { locked: true })
    status.value = { kind: 'success', text: t('teams.lockedDone', { name: team.name }) }
  } catch (e) {
    status.value = { kind: 'danger', text: courseErrorMessage(e) }
  } finally {
    busy.value = null
  }
}

function openReassign(team: Team) {
  editing.value = team
  selection.value = team.members.map((m) => m.id)
}

async function saveMembers() {
  const team = editing.value
  if (!team) return
  status.value = null
  busy.value = 'members'
  try {
    await teamsApi.setMembers(team.id, selection.value)
    await load() // otros equipos pueden haber perdido integrantes
    status.value = { kind: 'success', text: t('teams.reassigned', { name: team.name }) }
    editing.value = null
  } catch (e) {
    status.value = { kind: 'danger', text: courseErrorMessage(e) }
  } finally {
    busy.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="ld-stack" data-test="teams-admin">
    <p class="ld-muted">{{ t('teams.adminHelp') }}</p>
    <LdAlert v-if="status" :variant="status.kind" data-test="teams-status">{{
      status.text
    }}</LdAlert>
    <LdSpinner v-if="loading" :label="t('common2.loading')" />
    <LdAlert v-else-if="error" variant="danger">{{ error }}</LdAlert>
    <template v-else>
      <LdEmptyState v-if="teams.length === 0" :title="t('teams.adminEmpty')" />
      <ul v-else class="ld-tadmin">
        <li v-for="team in teams" :key="team.id" class="ld-tadmin__item" data-test="team-item">
          <div>
            <p class="ld-tadmin__name">
              <strong>{{ team.name }}</strong>
              <span class="ld-muted">· {{ team.join_code }}</span>
              <LdBadge v-if="team.locked" tone="info">{{ t('teams.locked') }}</LdBadge>
            </p>
            <p class="ld-muted ld-tadmin__members">
              {{
                lab.max_team_size
                  ? t('teams.members', { n: team.members.length, max: lab.max_team_size })
                  : t('teams.membersNoMax', { n: team.members.length })
              }}:
              {{ team.members.map((m) => m.full_name).join(', ') || '—' }}
            </p>
          </div>
          <div class="ld-row">
            <LdButton
              size="sm"
              variant="secondary"
              data-test="team-reassign"
              @click="openReassign(team)"
            >
              {{ t('teams.reassign') }}
            </LdButton>
            <LdButton
              v-if="!team.locked"
              size="sm"
              variant="ghost"
              :loading="busy === team.id"
              :aria-label="t('teams.lockLabel', { name: team.name })"
              data-test="team-lock"
              @click="lock(team)"
            >
              {{ t('teams.lock') }}
            </LdButton>
          </div>
        </li>
      </ul>
      <p v-if="withoutTeam.length" class="ld-muted" data-test="without-team">
        {{ t('teams.withoutTeam', { names: withoutTeam.map((s) => s.full_name).join(', ') }) }}
      </p>
    </template>

    <LdDialog
      v-if="editing"
      :title="t('teams.reassignTitle', { name: editing.name })"
      :persistent="busy === 'members'"
      @close="editing = null"
    >
      <fieldset class="ld-tadmin__pick">
        <legend class="ld-muted">{{ t('teams.reassignHelp') }}</legend>
        <label v-for="s in students" :key="s.user_id" class="ld-tadmin__check">
          <input v-model="selection" type="checkbox" :value="s.user_id" />
          {{ s.full_name }}
          <span
            v-if="teamOf.get(s.user_id) && teamOf.get(s.user_id)!.id !== editing.id"
            class="ld-muted"
          >
            ({{ t('teams.otherTeam', { name: teamOf.get(s.user_id)!.name }) }})
          </span>
        </label>
      </fieldset>
      <template #footer>
        <LdButton variant="ghost" :disabled="busy === 'members'" @click="editing = null">
          {{ t('common2.cancel') }}
        </LdButton>
        <LdButton :loading="busy === 'members'" data-test="team-save-members" @click="saveMembers">
          {{ t('teams.reassignSave') }}
        </LdButton>
      </template>
    </LdDialog>
  </div>
</template>

<style scoped>
.ld-tadmin {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
}

.ld-tadmin__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-3);
  padding: var(--ld-space-3) var(--ld-space-4);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  background: var(--ld-color-surface);
}

.ld-tadmin__name {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
}

.ld-tadmin__members {
  margin: var(--ld-space-1) 0 0;
  font-size: var(--ld-text-sm);
}

.ld-tadmin__pick {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
}

.ld-tadmin__check {
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  cursor: pointer;
}
</style>
