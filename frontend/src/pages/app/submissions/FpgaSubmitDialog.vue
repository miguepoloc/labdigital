<script setup lang="ts">
/**
 * Adaptador del diálogo de entrega para el envoltorio FPGA de LD-9 (`registerFpgaSubmitDialog`).
 * Recibe `context` (misma forma que `FpgaSubmitContext` de `src/pages/app/fpga/extensions.ts`, aquí descrita
 * de forma estructural para no depender de esa rama), guarda la versión con `prepareVersion()`, ofrece el
 * informe `.docx` y el último `.bit` de `window.JGFPGA` como archivos precargados y abre `SubmitDialog`.
 * Emite `close` y `submitted` con `{ submissionId }`.
 */
import { onMounted, ref } from 'vue'
import type { Submission } from '@/api/submissions'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t } from '@/i18n'
import { courseErrorMessage } from '../courses/courseErrors'
import SubmitDialog from './SubmitDialog.vue'
import type { FpgaSubmitContextLike } from './submitDialog'

const props = defineProps<{ context: FpgaSubmitContextLike }>()
const emit = defineEmits<{ close: []; submitted: [{ submissionId: string }] }>()

const preparing = ref(true)
const error = ref<string | null>(null)
const version = ref<{ project_id: string; version_id: string } | null>(null)
const report = ref<File | null>(null)
const bitstream = ref<File | null>(null)

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

async function prepare() {
  preparing.value = true
  error.value = null
  try {
    version.value = await props.context.prepareVersion()
  } catch (e) {
    error.value = courseErrorMessage(e)
    preparing.value = false
    return
  }
  // Informe y .bit son opcionales: si el módulo falla (red), se sigue sin ellos (contrato §7).
  try {
    const docx = await props.context.jgfpga.getReportDocx()
    if (docx)
      report.value = new File([docx], `informe-${props.context.project.name}.docx`, { type: DOCX })
  } catch {
    /* sin informe automático */
  }
  try {
    const bit = await props.context.jgfpga.getLastBitstream()
    // Es el último .bit de ESTE navegador: el diálogo muestra su nombre y el estudiante puede quitarlo.
    if (bit) bitstream.value = new File([bit.blob], bit.name, { type: 'application/octet-stream' })
  } catch {
    /* sin .bit automático */
  }
  preparing.value = false
}

function onSubmitted(s: Submission) {
  emit('submitted', { submissionId: s.id })
}

onMounted(prepare)
</script>

<template>
  <LdDialog v-if="preparing || error" :title="t('submit.title')" @close="emit('close')">
    <LdSpinner v-if="preparing" :label="t('submit.preparing')" />
    <LdAlert v-else variant="danger">
      {{ error }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="prepare">{{ t('common2.retry') }}</LdButton>
      </template>
    </LdAlert>
  </LdDialog>
  <SubmitDialog
    v-else-if="version"
    :lab-id="context.query.lab || undefined"
    :project-id="version.project_id"
    :version-id="version.version_id"
    :prefill="{ report, bitstream, bitstreamFromBrowser: !!bitstream }"
    @close="emit('close')"
    @submitted="onSubmitted"
  />
</template>
