<script setup lang="ts">
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import { t } from '@/i18n'

withDefaults(
  defineProps<{
    title: string
    message: string
    confirmLabel?: string
    danger?: boolean
    busy?: boolean
  }>(),
  { confirmLabel: undefined, danger: false, busy: false },
)
const emit = defineEmits<{ confirm: []; cancel: [] }>()
</script>

<template>
  <LdDialog :title="title" :persistent="busy" @close="emit('cancel')">
    <p>{{ message }}</p>
    <template #footer>
      <LdButton variant="ghost" :disabled="busy" @click="emit('cancel')">
        {{ t('common2.cancel') }}
      </LdButton>
      <LdButton
        :variant="danger ? 'danger' : 'primary'"
        :loading="busy"
        data-test="confirm-ok"
        @click="emit('confirm')"
      >
        {{ confirmLabel ?? t('common2.confirm') }}
      </LdButton>
    </template>
  </LdDialog>
</template>
