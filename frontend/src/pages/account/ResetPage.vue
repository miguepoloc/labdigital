<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { authApi } from '@/api/auth'
import { isApiError } from '@/api/errors'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdPasswordField from '@/components/LdPasswordField.vue'
import { config } from '@/config'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { errorMessage } from '@/lib/errors'
import * as v from '@/lib/validation'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const session = useSessionStore()
const token = computed(() => (typeof route.query.t === 'string' ? route.query.t : ''))

const form = reactive({ password: '', confirm: '' })
const errors = reactive<{ password: string | null; confirm: string | null }>({
  password: null,
  confirm: null,
})
const formError = ref<string | null>(null)
const tokenInvalid = ref(false)
const submitting = ref(false)
const done = ref(false)

async function submit() {
  formError.value = null
  errors.password = v.password(form.password)
  errors.confirm = v.matches(() => form.password)(form.confirm)
  if (errors.password || errors.confirm) return
  submitting.value = true
  try {
    await authApi.resetPassword({ token: token.value, password: form.password })
    session.clear() // el backend revoca todas las sesiones
    done.value = true
  } catch (e) {
    tokenInvalid.value = isApiError(e) && e.code === 'token_invalid'
    formError.value = errorMessage(e)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthLayout
    :title="t('reset.title')"
    :subtitle="done || !token ? undefined : t('reset.subtitle')"
  >
    <div v-if="!token" class="ld-stack">
      <LdAlert variant="danger">{{ t('reset.missing') }}</LdAlert>
      <LdButton :to="{ name: 'forgot' }" variant="secondary">{{ t('reset.requestNew') }}</LdButton>
    </div>
    <div v-else-if="done" class="ld-stack">
      <LdAlert variant="success" data-test="reset-done">{{ t('reset.done') }}</LdAlert>
      <LdButton :to="{ name: 'login' }" block>{{ t('reset.goLogin') }}</LdButton>
    </div>
    <form v-else class="ld-form" novalidate @submit.prevent="submit">
      <LdAlert v-if="formError" variant="danger" data-test="form-error">
        {{ formError }}
        <template v-if="tokenInvalid" #actions>
          <LdButton :to="{ name: 'forgot' }" size="sm" variant="secondary">{{
            t('reset.requestNew')
          }}</LdButton>
        </template>
      </LdAlert>
      <LdPasswordField
        v-model="form.password"
        :label="t('fields.newPassword')"
        autocomplete="new-password"
        meter
        required
        :help="t('password.hint', { min: config.passwordMinLength })"
        :error="errors.password"
      />
      <LdPasswordField
        v-model="form.confirm"
        :label="t('fields.confirmPassword')"
        autocomplete="new-password"
        required
        :error="errors.confirm"
      />
      <LdButton type="submit" block :loading="submitting">
        {{ submitting ? t('reset.submitting') : t('reset.submit') }}
      </LdButton>
    </form>
  </AuthLayout>
</template>
