<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { authApi } from '@/api/auth'
import { isApiError } from '@/api/errors'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { errorMessage } from '@/lib/errors'
import * as v from '@/lib/validation'

const email = ref('')
const emailError = ref<string | null>(null)
const formError = ref<string | null>(null)
const submitting = ref(false)
const doneEmail = ref<string | null>(null)

async function submit() {
  formError.value = null
  emailError.value = v.email(email.value)
  if (emailError.value) return
  submitting.value = true
  try {
    await authApi.forgotPassword(email.value.trim())
    doneEmail.value = email.value.trim()
  } catch (e) {
    // Sólo errores que no revelan nada (límite, red); el 202 es igual exista o no la cuenta.
    formError.value = errorMessage(e)
    if (isApiError(e) && e.status >= 500) formError.value = t('errors.unknown')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthLayout :title="t('forgot.title')" :subtitle="doneEmail ? undefined : t('forgot.subtitle')">
    <LdAlert v-if="doneEmail" variant="success" data-test="forgot-done">
      {{ t('forgot.done', { email: doneEmail }) }}
    </LdAlert>
    <form v-else class="ld-form" novalidate @submit.prevent="submit">
      <LdAlert v-if="formError" variant="danger" data-test="form-error">{{ formError }}</LdAlert>
      <LdTextField
        v-model="email"
        :label="t('fields.email')"
        type="email"
        name="email"
        autocomplete="email"
        inputmode="email"
        required
        :error="emailError"
      />
      <LdButton type="submit" block :loading="submitting">
        {{ submitting ? t('forgot.submitting') : t('forgot.submit') }}
      </LdButton>
    </form>
    <template #below>
      <RouterLink :to="{ name: 'login' }">{{ t('forgot.back') }}</RouterLink>
    </template>
  </AuthLayout>
</template>
