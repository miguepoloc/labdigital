<script setup lang="ts">
/** Diálogo "Entregar" mientras no existan cursos (ver `extensions.ts` para conectar el flujo real). */
import LdButton from '@/components/LdButton.vue'
import { t } from '@/i18n'
import type { FpgaSubmitContext } from './extensions'
import FpgaDialog from './FpgaDialog.vue'

defineProps<{ context: FpgaSubmitContext }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <FpgaDialog :title="t('projects.fpga.submitTitle')" @close="emit('close')">
    <p data-test="submit-placeholder">{{ t('projects.fpga.submitPlaceholder') }}</p>
    <template #footer>
      <LdButton @click="emit('close')">{{ t('common.close') }}</LdButton>
    </template>
  </FpgaDialog>
</template>
