<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { authApi } from '@/api/auth'
import type { Session } from '@/api/types'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import { errorMessage } from '@/lib/errors'
import { describeUserAgent, formatDateTime } from '@/lib/format'

const sessions = ref<Session[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const busyId = ref<string | null>(null)
const revokingOthers = ref(false)

const sorted = computed(() =>
  [...sessions.value].sort((a, b) =>
    a.current === b.current ? b.last_used_at.localeCompare(a.last_used_at) : a.current ? -1 : 1,
  ),
)
const others = computed(() => sessions.value.filter((s) => !s.current))

function device(s: Session) {
  return describeUserAgent(s.user_agent) ?? t('sessions.unknownDevice')
}

async function load() {
  loading.value = true
  loadError.value = null
  try {
    sessions.value = await authApi.listSessions()
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function revoke(s: Session) {
  status.value = null
  busyId.value = s.id
  try {
    await authApi.revokeSession(s.id)
    sessions.value = sessions.value.filter((x) => x.id !== s.id)
    status.value = { kind: 'success', text: t('sessions.revoked') }
  } catch (e) {
    status.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    busyId.value = null
  }
}

async function revokeOthers() {
  status.value = null
  revokingOthers.value = true
  try {
    await authApi.revokeOtherSessions()
    sessions.value = sessions.value.filter((x) => x.current)
    status.value = { kind: 'success', text: t('sessions.revokedOthers') }
  } catch (e) {
    status.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    revokingOthers.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="ld-stack ld-sessions">
    <header class="ld-sessions__head">
      <div>
        <h1>{{ t('sessions.title') }}</h1>
        <p class="ld-muted">{{ t('sessions.subtitle') }}</p>
      </div>
      <LdButton
        v-if="others.length > 0"
        variant="secondary"
        :loading="revokingOthers"
        data-test="revoke-others"
        @click="revokeOthers"
      >
        {{ t('sessions.revokeOthers') }}
      </LdButton>
    </header>

    <LdAlert v-if="status" :variant="status.kind">{{ status.text }}</LdAlert>

    <LdSpinner v-if="loading" size="lg" />
    <LdAlert v-else-if="loadError" variant="danger">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{ t('sessions.reload') }}</LdButton>
      </template>
    </LdAlert>
    <template v-else>
      <ul class="ld-sessions__list">
        <li v-for="s in sorted" :key="s.id" data-test="session-item">
          <LdCard as="article" :padded="true">
            <div class="ld-sessions__item">
              <div>
                <h2 class="ld-sessions__device">
                  {{ device(s) }}
                  <span v-if="s.current" class="ld-sessions__badge">{{
                    t('sessions.current')
                  }}</span>
                </h2>
                <p class="ld-muted ld-sessions__meta">
                  <span>{{
                    t('sessions.lastUsed', { date: formatDateTime(s.last_used_at) })
                  }}</span>
                  <span>{{ t('sessions.createdAt', { date: formatDateTime(s.created_at) }) }}</span>
                  <span v-if="s.ip">{{ t('sessions.ip', { ip: s.ip }) }}</span>
                </p>
              </div>
              <LdButton
                v-if="!s.current"
                size="sm"
                variant="danger"
                :loading="busyId === s.id"
                :aria-label="t('sessions.revokeLabel', { device: device(s) })"
                data-test="revoke"
                @click="revoke(s)"
              >
                {{ t('sessions.revoke') }}
              </LdButton>
            </div>
          </LdCard>
        </li>
      </ul>
      <LdEmptyState v-if="others.length === 0" :title="t('sessions.empty')" />
    </template>
  </div>
</template>

<style scoped>
.ld-sessions__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ld-space-3);
}

.ld-sessions__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
}

.ld-sessions__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-3);
}

.ld-sessions__device {
  font-size: var(--ld-text-md);
  margin-bottom: var(--ld-space-1);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ld-space-2);
}

.ld-sessions__badge {
  font-size: var(--ld-text-xs);
  font-weight: 600;
  padding: 0.1rem var(--ld-space-2);
  border-radius: var(--ld-radius-full);
  background: var(--ld-color-success-bg);
  color: var(--ld-color-success);
}

.ld-sessions__meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-1) var(--ld-space-4);
  font-size: var(--ld-text-sm);
}
</style>
