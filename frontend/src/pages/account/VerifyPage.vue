<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { authApi } from '@/api/auth'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { errorMessage } from '@/lib/errors'
import * as v from '@/lib/validation'

const route = useRoute()
const state = ref<'verifying' | 'ok' | 'error'>('verifying')
const errorText = ref<string | null>(null)
const resendEmail = ref('')
const resendError = ref<string | null>(null)
const resendState = ref<'idle' | 'sending' | 'sent'>('idle')

onMounted(async () => {
  const token = typeof route.query.t === 'string' ? route.query.t : ''
  if (!token) {
    state.value = 'error'
    errorText.value = t('verify.missing')
    return
  }
  try {
    await authApi.verifyEmail(token)
    state.value = 'ok'
  } catch (e) {
    state.value = 'error'
    errorText.value = errorMessage(e)
  }
})

async function resend() {
  resendError.value = v.email(resendEmail.value)
  if (resendError.value) return
  resendState.value = 'sending'
  try {
    await authApi.resendVerification(resendEmail.value.trim())
  } catch {
    /* respuesta siempre igual */
  }
  resendState.value = 'sent'
}
</script>

<template>
  <AuthLayout :title="t('verify.title')">
    <div v-if="state === 'verifying'" class="ld-row">
      <LdSpinner :label="t('verify.verifying')" />
      <span aria-hidden="true">{{ t('verify.verifying') }}</span>
    </div>

    <div v-else-if="state === 'ok'" class="ld-stack">
      <LdAlert variant="success" data-test="verify-ok">{{ t('verify.ok') }}</LdAlert>
      <LdButton :to="{ name: 'login' }" block>{{ t('verify.goLogin') }}</LdButton>
    </div>

    <div v-else class="ld-stack">
      <LdAlert variant="danger" data-test="verify-error">{{ errorText }}</LdAlert>
      <h2>{{ t('verify.resendTitle') }}</h2>
      <LdAlert v-if="resendState === 'sent'" variant="success">{{ t('verify.resent') }}</LdAlert>
      <form v-else class="ld-form" novalidate @submit.prevent="resend">
        <LdTextField
          v-model="resendEmail"
          :label="t('fields.email')"
          type="email"
          autocomplete="email"
          required
          :error="resendError"
        />
        <LdButton type="submit" variant="secondary" :loading="resendState === 'sending'">
          {{ t('verify.resend') }}
        </LdButton>
      </form>
    </div>
  </AuthLayout>
</template>
