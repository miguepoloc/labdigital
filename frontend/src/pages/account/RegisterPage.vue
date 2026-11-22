<script setup lang="ts">
import { reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { authApi } from '@/api/auth'
import { isApiError } from '@/api/errors'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCheckbox from '@/components/LdCheckbox.vue'
import LdPasswordField from '@/components/LdPasswordField.vue'
import LdTextField from '@/components/LdTextField.vue'
import { config } from '@/config'
import { t } from '@/i18n'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { errorMessage, fieldErrors as serverFieldErrors } from '@/lib/errors'
import * as v from '@/lib/validation'

const route = useRoute()
const form = reactive({ full_name: '', email: '', password: '', accept: false })
const errors = reactive<Record<'full_name' | 'email' | 'password' | 'accept', string | null>>({
  full_name: null,
  email: null,
  password: null,
  accept: null,
})
const submitting = ref(false)
const formError = ref<string | null>(null)
const doneEmail = ref<string | null>(null)

function validate(): boolean {
  errors.full_name = v.fullName(form.full_name)
  errors.email = v.email(form.email)
  errors.password = v.password(form.password)
  errors.accept = form.accept ? null : t('validation.acceptPolicy')
  const ok = !Object.values(errors).some(Boolean)
  if (!ok) formError.value = t('validation.formHasErrors')
  return ok
}

async function submit() {
  formError.value = null
  if (!validate()) return
  submitting.value = true
  try {
    const email = form.email.trim()
    await authApi.register({
      email,
      full_name: form.full_name.trim(),
      password: form.password,
      accept_data_policy: true,
    })
    doneEmail.value = email
  } catch (e) {
    const fe = serverFieldErrors(e)
    errors.full_name = fe.full_name ?? errors.full_name
    errors.email = fe.email ?? errors.email
    errors.password = fe.password ?? errors.password
    errors.accept = fe.accept_data_policy ?? errors.accept
    formError.value = errorMessage(e)
    if (isApiError(e) && e.code !== 'validation_error') form.password = ''
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthLayout
    :title="doneEmail ? t('register.doneTitle') : t('register.title')"
    :subtitle="doneEmail ? undefined : t('register.subtitle')"
  >
    <div v-if="doneEmail" class="ld-stack">
      <LdAlert variant="success" data-test="register-done">
        {{ t('register.doneBody', { email: doneEmail }) }}
      </LdAlert>
      <LdButton
        :to="{ name: 'login', query: route.query.next ? { next: route.query.next } : {} }"
        block
      >
        {{ t('register.doneBack') }}
      </LdButton>
    </div>

    <form v-else class="ld-form" novalidate @submit.prevent="submit">
      <LdAlert v-if="formError" variant="danger" data-test="form-error">{{ formError }}</LdAlert>
      <LdTextField
        v-model="form.full_name"
        :label="t('fields.fullName')"
        name="full_name"
        autocomplete="name"
        required
        :error="errors.full_name"
      />
      <LdTextField
        v-model="form.email"
        :label="t('fields.email')"
        type="email"
        name="email"
        autocomplete="email"
        inputmode="email"
        required
        :error="errors.email"
      />
      <LdPasswordField
        v-model="form.password"
        :label="t('fields.password')"
        name="password"
        autocomplete="new-password"
        meter
        required
        :help="t('password.hint', { min: config.passwordMinLength })"
        :error="errors.password"
      />
      <LdCheckbox v-model="form.accept" name="accept_data_policy" required :error="errors.accept">
        {{ t('register.acceptPrefix') }}
        <a :href="config.dataPolicyUrl" target="_blank" rel="noopener">{{
          t('register.policyLink')
        }}</a>
        {{ t('register.acceptSuffix') }}
      </LdCheckbox>
      <LdButton type="submit" block :loading="submitting">
        {{ submitting ? t('register.submitting') : t('register.submit') }}
      </LdButton>
    </form>

    <template v-if="!doneEmail" #below>
      {{ t('register.haveAccount') }}
      <RouterLink
        :to="{ name: 'login', query: route.query.next ? { next: route.query.next } : {} }"
      >
        {{ t('register.login') }}
      </RouterLink>
    </template>
  </AuthLayout>
</template>
