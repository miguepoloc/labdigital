<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { meApi } from '@/api/auth'
import { isApiError } from '@/api/errors'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdPasswordField from '@/components/LdPasswordField.vue'
import LdTextField from '@/components/LdTextField.vue'
import { config } from '@/config'
import { t } from '@/i18n'
import { errorMessage, fieldErrors } from '@/lib/errors'
import * as v from '@/lib/validation'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()

// ---- Nombre ----
const name = ref(session.me?.full_name ?? '')
watch(
  () => session.me?.full_name,
  (n) => {
    if (n !== undefined) name.value = n
  },
)
const nameError = ref<string | null>(null)
const nameStatus = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const savingName = ref(false)

async function saveName() {
  nameStatus.value = null
  nameError.value = v.fullName(name.value)
  if (nameError.value) return
  savingName.value = true
  try {
    const full_name = name.value.trim()
    const updated = await meApi.update({ full_name })
    // PROPUESTA AL CONTRATO: que PATCH /me devuelva `Me`; si no, se actualiza localmente.
    if (session.me) session.setMe(updated ?? { ...session.me, full_name })
    nameStatus.value = { kind: 'success', text: t('profile.nameSaved') }
  } catch (e) {
    nameError.value = fieldErrors(e).full_name ?? null
    nameStatus.value = { kind: 'danger', text: errorMessage(e) }
  } finally {
    savingName.value = false
  }
}

// ---- Contraseña ----
const pw = reactive({ current: '', next: '', confirm: '' })
const pwErrors = reactive<{ current: string | null; next: string | null; confirm: string | null }>({
  current: null,
  next: null,
  confirm: null,
})
const pwStatus = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const savingPw = ref(false)

async function changePassword() {
  pwStatus.value = null
  pwErrors.current = pw.current ? null : t('validation.required')
  pwErrors.next = v.password(pw.next)
  pwErrors.confirm = v.matches(() => pw.next)(pw.confirm)
  if (pwErrors.current || pwErrors.next || pwErrors.confirm) return
  savingPw.value = true
  try {
    await meApi.changePassword({ current: pw.current, new: pw.next })
    pw.current = pw.next = pw.confirm = ''
    pwStatus.value = { kind: 'success', text: t('profile.passwordSaved') }
  } catch (e) {
    if (isApiError(e) && e.code === 'invalid_credentials') {
      pwErrors.current = t('profile.wrongCurrent')
    } else {
      const fe = fieldErrors(e)
      pwErrors.next = fe.new ?? null
      pwStatus.value = { kind: 'danger', text: errorMessage(e) }
    }
  } finally {
    savingPw.value = false
  }
}
</script>

<template>
  <div class="ld-stack ld-profile">
    <h1>{{ t('profile.title') }}</h1>

    <LdCard :title="t('profile.dataTitle')">
      <form class="ld-form" novalidate data-test="name-form" @submit.prevent="saveName">
        <LdAlert v-if="nameStatus" :variant="nameStatus.kind">{{ nameStatus.text }}</LdAlert>
        <LdTextField
          :model-value="session.me?.email ?? ''"
          :label="t('fields.email')"
          type="email"
          readonly
          :help="t('profile.emailHelp')"
        />
        <LdTextField
          v-model="name"
          :label="t('fields.fullName')"
          name="full_name"
          autocomplete="name"
          required
          :error="nameError"
        />
        <div class="ld-form__actions">
          <LdButton type="submit" :loading="savingName">
            {{ savingName ? t('profile.saving') : t('profile.saveName') }}
          </LdButton>
        </div>
      </form>
    </LdCard>

    <LdCard :title="t('profile.passwordTitle')">
      <form class="ld-form" novalidate data-test="password-form" @submit.prevent="changePassword">
        <LdAlert v-if="pwStatus" :variant="pwStatus.kind">{{ pwStatus.text }}</LdAlert>
        <LdPasswordField
          v-model="pw.current"
          :label="t('fields.currentPassword')"
          autocomplete="current-password"
          required
          :error="pwErrors.current"
        />
        <LdPasswordField
          v-model="pw.next"
          :label="t('fields.newPassword')"
          autocomplete="new-password"
          meter
          required
          :help="t('password.hint', { min: config.passwordMinLength })"
          :error="pwErrors.next"
        />
        <LdPasswordField
          v-model="pw.confirm"
          :label="t('fields.confirmPassword')"
          autocomplete="new-password"
          required
          :error="pwErrors.confirm"
        />
        <div class="ld-form__actions">
          <LdButton type="submit" :loading="savingPw">
            {{ savingPw ? t('profile.saving') : t('profile.changePassword') }}
          </LdButton>
        </div>
      </form>
    </LdCard>
  </div>
</template>

<style scoped>
.ld-profile {
  max-width: 40rem;
}
</style>
