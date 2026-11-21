<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { authApi } from '@/api/auth'
import { isApiError } from '@/api/errors'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCheckbox from '@/components/LdCheckbox.vue'
import LdPasswordField from '@/components/LdPasswordField.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { errorMessage } from '@/lib/errors'
import { useRetryCountdown } from '@/lib/useRetryCountdown'
import * as v from '@/lib/validation'
import { goToNext } from '@/router/guards'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const form = reactive({ email: '', password: '', remember: true })
const fieldErrors = reactive<{ email: string | null; password: string | null }>({
  email: null,
  password: null,
})
const submitting = ref(false)
const errorCode = ref<string | null>(null)
const errorText = ref<string | null>(null)
const resendState = ref<'idle' | 'sending' | 'sent'>('idle')
const countdown = useRetryCountdown()

const emailRef = ref<InstanceType<typeof LdTextField> | null>(null)
const passwordRef = ref<InstanceType<typeof LdPasswordField> | null>(null)

const expired = computed(() => route.query.expired === '1')
const formError = computed(() => {
  if (errorCode.value === 'rate_limited' && countdown.waiting.value) {
    return t('errors.rate_limited_wait', { seconds: countdown.seconds.value })
  }
  return errorText.value
})
const nextQuery = computed(() =>
  typeof route.query.next === 'string' ? { next: route.query.next } : {},
)

function validate(): boolean {
  fieldErrors.email = v.email(form.email)
  fieldErrors.password = form.password ? null : t('validation.required')
  if (fieldErrors.email) emailRef.value?.focus()
  else if (fieldErrors.password) passwordRef.value?.focus()
  return !fieldErrors.email && !fieldErrors.password
}

async function submit() {
  errorCode.value = null
  errorText.value = null
  resendState.value = 'idle'
  if (!validate()) return
  submitting.value = true
  try {
    await session.login({
      email: form.email.trim(),
      password: form.password,
      remember: form.remember,
    })
    await goToNext(router, route.query.next)
  } catch (e) {
    errorCode.value = isApiError(e) ? String(e.code) : 'unknown'
    errorText.value = errorMessage(e)
    if (isApiError(e) && e.code === 'rate_limited') countdown.start(e.retryAfter)
    if (isApiError(e) && e.code === 'invalid_credentials') form.password = ''
  } finally {
    submitting.value = false
  }
}

async function resend() {
  resendState.value = 'sending'
  try {
    await authApi.resendVerification(form.email.trim())
  } catch {
    /* respuesta siempre igual (202); un fallo de red no debe revelar nada distinto */
  }
  resendState.value = 'sent'
}
</script>

<template>
  <AuthLayout :title="t('login.title')" :subtitle="t('login.subtitle')">
    <LdAlert v-if="expired && !formError" variant="info" class="ld-mb">{{
      t('login.sessionExpired')
    }}</LdAlert>

    <form class="ld-form" novalidate @submit.prevent="submit">
      <LdAlert v-if="formError" variant="danger" data-test="form-error">
        {{ formError }}
        <template v-if="errorCode === 'email_not_verified'" #actions>
          <LdButton
            v-if="resendState !== 'sent'"
            size="sm"
            variant="secondary"
            :loading="resendState === 'sending'"
            data-test="resend"
            @click="resend"
          >
            {{ t('login.resend') }}
          </LdButton>
          <span v-else role="status">{{ t('login.resent') }}</span>
        </template>
      </LdAlert>

      <LdTextField
        ref="emailRef"
        v-model="form.email"
        :label="t('fields.email')"
        type="email"
        name="email"
        autocomplete="username"
        inputmode="email"
        required
        :error="fieldErrors.email"
      />
      <LdPasswordField
        ref="passwordRef"
        v-model="form.password"
        :label="t('fields.password')"
        name="password"
        autocomplete="current-password"
        required
        :error="fieldErrors.password"
      />
      <LdCheckbox v-model="form.remember" :label="t('login.remember')" name="remember" />

      <LdButton type="submit" block :loading="submitting" :disabled="countdown.waiting.value">
        {{ submitting ? t('login.submitting') : t('login.submit') }}
      </LdButton>
      <RouterLink class="ld-center" :to="{ name: 'forgot' }">{{ t('login.forgot') }}</RouterLink>
    </form>

    <template #below>
      {{ t('login.noAccount') }}
      <RouterLink :to="{ name: 'register', query: nextQuery }">{{
        t('login.register')
      }}</RouterLink>
    </template>
  </AuthLayout>
</template>

<style scoped>
.ld-mb {
  margin-bottom: var(--ld-space-4);
}

.ld-center {
  align-self: center;
  font-size: var(--ld-text-sm);
}
</style>
