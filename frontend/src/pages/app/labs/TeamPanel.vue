<script setup lang="ts">
/** Equipo del estudiante en un lab: crear con nombre (→ código), unirse con código, salir. */
import { computed, onMounted, ref } from 'vue'
import { teamsApi, type Lab, type Team } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdBadge from '@/components/LdBadge.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import ConfirmDialog from '../courses/ConfirmDialog.vue'
import { courseErrorMessage } from '../courses/courseErrors'

const props = defineProps<{ lab: Lab; userId: string }>()
const emit = defineEmits<{ change: [Team | null] }>()

const teams = ref<Team[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const status = ref<string | null>(null)
const name = ref('')
const code = ref('')
const busy = ref<'create' | 'join' | 'leave' | null>(null)
const confirmLeave = ref(false)

const mine = computed(
  () => teams.value.find((tm) => tm.members.some((m) => m.id === props.userId)) ?? null,
)

async function load() {
  loading.value = true
  error.value = null
  try {
    teams.value = await teamsApi.list(props.lab.id)
    emit('change', mine.value)
  } catch (e) {
    error.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function create() {
  error.value = null
  status.value = null
  if (!name.value.trim()) {
    error.value = t('validation.required')
    return
  }
  busy.value = 'create'
  try {
    const res = await teamsApi.create(props.lab.id, name.value.trim())
    name.value = ''
    await load()
    status.value = t('teams.created', { code: res.join_code })
  } catch (e) {
    error.value = courseErrorMessage(e)
  } finally {
    busy.value = null
  }
}

async function join() {
  error.value = null
  status.value = null
  if (!code.value.trim()) {
    error.value = t('validation.required')
    return
  }
  busy.value = 'join'
  try {
    await teamsApi.join(props.lab.id, code.value.trim())
    code.value = ''
    await load()
    if (mine.value) status.value = t('teams.joined', { name: mine.value.name })
  } catch (e) {
    error.value = courseErrorMessage(e)
  } finally {
    busy.value = null
  }
}

async function leave() {
  if (!mine.value) return
  error.value = null
  status.value = null
  busy.value = 'leave'
  try {
    await teamsApi.leave(mine.value.id)
    await load()
    status.value = t('teams.left')
  } catch (e) {
    error.value = courseErrorMessage(e)
  } finally {
    busy.value = null
    confirmLeave.value = false
  }
}

onMounted(load)
</script>

<template>
  <LdCard :title="t('teams.title')" data-test="team-panel">
    <LdSpinner v-if="loading" :label="t('common2.loading')" />
    <template v-else>
      <LdAlert v-if="status" variant="success" data-test="team-status">{{ status }}</LdAlert>
      <LdAlert v-if="error" variant="danger" data-test="team-error">{{ error }}</LdAlert>

      <div v-if="mine" class="ld-stack" data-test="my-team">
        <p class="ld-team__name">
          <strong>{{ mine.name }}</strong>
          <LdBadge v-if="mine.locked" tone="info">{{ t('teams.locked') }}</LdBadge>
        </p>
        <p v-if="mine.join_code" class="ld-team__code">
          {{ t('teams.code', { code: mine.join_code }) }}
        </p>
        <div>
          <p class="ld-field__label">
            {{
              lab.max_team_size
                ? t('teams.members', { n: mine.members.length, max: lab.max_team_size })
                : t('teams.membersNoMax', { n: mine.members.length })
            }}
          </p>
          <ul class="ld-team__members">
            <li v-for="m in mine.members" :key="m.id">{{ m.full_name }}</li>
          </ul>
        </div>
        <p v-if="mine.locked" class="ld-muted">{{ t('teams.lockedHelp') }}</p>
        <div v-else>
          <LdButton
            size="sm"
            variant="secondary"
            :loading="busy === 'leave'"
            data-test="team-leave"
            @click="confirmLeave = true"
          >
            {{ t('teams.leave') }}
          </LdButton>
        </div>
      </div>

      <div v-else class="ld-stack">
        <p class="ld-muted">{{ t('teams.none') }}</p>
        <div class="ld-team__forms">
          <form class="ld-team__form" novalidate data-test="team-create" @submit.prevent="create">
            <LdTextField
              v-model="name"
              :label="t('teams.createLabel')"
              name="team_name"
              :placeholder="t('teams.createPlaceholder')"
            />
            <LdButton type="submit" size="sm" :loading="busy === 'create'">
              {{ t('teams.create') }}
            </LdButton>
          </form>
          <form class="ld-team__form" novalidate data-test="team-join" @submit.prevent="join">
            <LdTextField
              v-model="code"
              :label="t('teams.joinLabel')"
              name="team_code"
              autocomplete="off"
            />
            <LdButton type="submit" size="sm" variant="secondary" :loading="busy === 'join'">
              {{ t('teams.join') }}
            </LdButton>
          </form>
        </div>
      </div>
    </template>
    <ConfirmDialog
      v-if="confirmLeave && mine"
      :title="t('teams.leave')"
      :message="t('teams.leaveConfirm', { name: mine.name })"
      :confirm-label="t('teams.leave')"
      danger
      :busy="busy === 'leave'"
      @cancel="confirmLeave = false"
      @confirm="leave"
    />
  </LdCard>
</template>

<style scoped>
.ld-team__name {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  font-size: var(--ld-text-lg);
}

.ld-team__code {
  margin: 0;
  font-family: var(--ld-font-mono);
}

.ld-team__members {
  margin: var(--ld-space-1) 0 0;
  padding-left: var(--ld-space-5);
}

.ld-team__forms {
  display: grid;
  gap: var(--ld-space-4);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr));
}

.ld-team__form {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--ld-space-2);
}

.ld-team__form > :first-child {
  align-self: stretch;
}
</style>
