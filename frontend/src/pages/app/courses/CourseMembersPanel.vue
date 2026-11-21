<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { coursesApi, type Member } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import { formatBogota } from '@/lib/bogota'
import ConfirmDialog from './ConfirmDialog.vue'
import { courseErrorMessage } from './courseErrors'

/** `pending`: solicitudes (aprobar/rechazar). `active`: miembros (quitar). */
const props = defineProps<{ courseId: string; mode: 'pending' | 'active' }>()
const emit = defineEmits<{ changed: [] }>()

const members = ref<Member[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const busy = ref<string | null>(null)
const removing = ref<Member | null>(null)

async function load() {
  loading.value = true
  loadError.value = null
  try {
    members.value = await coursesApi.members(props.courseId, props.mode)
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function act(m: Member, action: 'approve' | 'reject' | 'remove') {
  status.value = null
  busy.value = `${m.user_id}:${action}`
  try {
    await coursesApi.memberAction(props.courseId, m.user_id, action)
    members.value = members.value.filter((x) => x.user_id !== m.user_id)
    const key =
      action === 'approve'
        ? 'courses.requests.approved'
        : action === 'reject'
          ? 'courses.requests.rejectedDone'
          : 'courses.members.removed'
    status.value = { kind: 'success', text: t(key, { name: m.full_name }) }
    emit('changed')
  } catch (e) {
    status.value = { kind: 'danger', text: courseErrorMessage(e) }
  } finally {
    busy.value = null
    removing.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="ld-stack">
    <LdAlert v-if="status" :variant="status.kind" data-test="members-status">{{
      status.text
    }}</LdAlert>
    <LdSpinner v-if="loading" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{ t('common2.retry') }}</LdButton>
      </template>
    </LdAlert>
    <LdEmptyState
      v-else-if="members.length === 0"
      :title="
        mode === 'pending' ? t('courses.requests.emptyTitle') : t('courses.members.emptyTitle')
      "
      :body="mode === 'pending' ? t('courses.requests.emptyBody') : t('courses.members.emptyBody')"
    />
    <ul v-else-if="mode === 'pending'" class="ld-members__list">
      <li v-for="m in members" :key="m.user_id" class="ld-members__row" data-test="request-item">
        <div>
          <strong>{{ m.full_name }}</strong>
          <span class="ld-muted"> · {{ m.email }}</span>
          <p class="ld-muted ld-members__date">
            {{ t('courses.requests.requestedAt', { date: formatBogota(m.requested_at) }) }}
          </p>
        </div>
        <div class="ld-row">
          <LdButton
            size="sm"
            :loading="busy === `${m.user_id}:approve`"
            :aria-label="t('courses.requests.approveLabel', { name: m.full_name })"
            data-test="approve"
            @click="act(m, 'approve')"
          >
            {{ t('courses.requests.approve') }}
          </LdButton>
          <LdButton
            size="sm"
            variant="secondary"
            :loading="busy === `${m.user_id}:reject`"
            :aria-label="t('courses.requests.rejectLabel', { name: m.full_name })"
            data-test="reject"
            @click="act(m, 'reject')"
          >
            {{ t('courses.requests.reject') }}
          </LdButton>
        </div>
      </li>
    </ul>
    <div v-else class="ld-members__table-wrap">
      <table class="ld-members__table">
        <thead>
          <tr>
            <th scope="col">{{ t('courses.members.name') }}</th>
            <th scope="col">{{ t('courses.members.email') }}</th>
            <th scope="col">{{ t('courses.members.role') }}</th>
            <th scope="col">
              <span class="ld-visually-hidden">{{ t('courses.members.actions') }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in members" :key="m.user_id" data-test="member-item">
            <td>{{ m.full_name }}</td>
            <td>{{ m.email }}</td>
            <td>
              {{
                m.role === 'docente'
                  ? t('courses.members.roleDocente')
                  : t('courses.members.roleEstudiante')
              }}
            </td>
            <td class="ld-members__actions">
              <LdButton
                size="sm"
                variant="ghost"
                :aria-label="t('courses.members.removeLabel', { name: m.full_name })"
                data-test="remove"
                @click="removing = m"
              >
                {{ t('courses.members.remove') }}
              </LdButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <ConfirmDialog
      v-if="removing"
      :title="t('courses.members.remove')"
      :message="t('courses.members.removeConfirm', { name: removing.full_name })"
      :confirm-label="t('courses.members.remove')"
      danger
      :busy="busy !== null"
      @cancel="removing = null"
      @confirm="act(removing, 'remove')"
    />
  </div>
</template>

<style scoped>
.ld-members__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
}

.ld-members__row {
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

.ld-members__date {
  margin: var(--ld-space-1) 0 0;
  font-size: var(--ld-text-sm);
}

.ld-members__table-wrap {
  overflow-x: auto;
}

.ld-members__table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--ld-text-sm);
}

.ld-members__table th,
.ld-members__table td {
  text-align: left;
  padding: var(--ld-space-2) var(--ld-space-3);
  border-bottom: 1px solid var(--ld-color-border);
}

.ld-members__actions {
  text-align: right;
}
</style>
