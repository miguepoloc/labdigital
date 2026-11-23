<script setup lang="ts">
/** «Crear varios equipos» (LD-18): N equipos vacíos «Pareja 1…N» (el prefijo se puede cambiar). */
import { computed, ref } from 'vue'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import { MAX_BULK_TEAMS } from './teamsAdmin'

const props = withDefaults(
  defineProps<{ suggested?: number; busy?: boolean; error?: string | null }>(),
  { suggested: 1, busy: false, error: null },
)
const emit = defineEmits<{ save: [{ count: number; prefix: string }]; cancel: [] }>()

const count = ref(String(Math.min(Math.max(props.suggested, 1), MAX_BULK_TEAMS)))
const prefix = ref(t('teams.bulkDefaultPrefix'))
const countError = ref<string | null>(null)
const prefixError = ref<string | null>(null)

const example = computed(() => {
  const p = prefix.value.trim() || t('teams.bulkDefaultPrefix')
  const n = Number(count.value)
  return Number.isInteger(n) && n > 1 ? `${p} 1 … ${p} ${n}` : `${p} 1`
})

function save() {
  const n = Number(count.value)
  countError.value =
    Number.isInteger(n) && n >= 1 && n <= MAX_BULK_TEAMS
      ? null
      : t('teams.bulkCountError', { max: MAX_BULK_TEAMS })
  prefixError.value = prefix.value.trim() ? null : t('validation.required')
  if (countError.value || prefixError.value) return
  emit('save', { count: n, prefix: prefix.value.trim() })
}
</script>

<template>
  <LdDialog :title="t('teams.bulkTitle')" :persistent="busy" @close="emit('cancel')">
    <form class="ld-stack" data-test="bulk-form" @submit.prevent="save">
      <LdAlert v-if="error" variant="danger" data-test="bulk-error">{{ error }}</LdAlert>
      <p class="ld-muted">{{ t('teams.bulkHelp', { example }) }}</p>
      <LdTextField
        v-model="count"
        :label="t('teams.bulkCount')"
        inputmode="numeric"
        name="bulk_count"
        :error="countError"
        required
      />
      <LdTextField
        v-model="prefix"
        :label="t('teams.bulkPrefix')"
        name="bulk_prefix"
        :error="prefixError"
        required
      />
    </form>
    <template #footer>
      <LdButton variant="ghost" :disabled="busy" @click="emit('cancel')">
        {{ t('common2.cancel') }}
      </LdButton>
      <LdButton :loading="busy" data-test="bulk-save" @click="save">
        {{ t('teams.bulkSave') }}
      </LdButton>
    </template>
  </LdDialog>
</template>
