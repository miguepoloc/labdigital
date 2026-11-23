<script setup lang="ts">
/**
 * Nombre (y, al crear, integrantes iniciales) de un equipo del docente (LD-18). Si se pasan
 * `candidates` se muestran como casillas, con el tope de `maxSize`.
 */
import { computed, ref } from 'vue'
import type { TeamMember } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'

const props = withDefaults(
  defineProps<{
    title: string
    saveLabel: string
    initialName?: string
    candidates?: TeamMember[] | null
    maxSize?: number | null
    busy?: boolean
    error?: string | null
  }>(),
  { initialName: '', candidates: null, maxSize: null, busy: false, error: null },
)
const emit = defineEmits<{ save: [{ name: string; memberIds: string[] }]; cancel: [] }>()

const name = ref(props.initialName)
const selection = ref<string[]>([])
const nameError = ref<string | null>(null)

const full = computed(() => props.maxSize !== null && selection.value.length >= props.maxSize)

function save() {
  nameError.value = name.value.trim() ? null : t('validation.required')
  if (nameError.value) return
  emit('save', { name: name.value.trim(), memberIds: [...selection.value] })
}
</script>

<template>
  <LdDialog :title="title" :persistent="busy" @close="emit('cancel')">
    <form class="ld-stack" data-test="team-form" @submit.prevent="save">
      <LdAlert v-if="error" variant="danger" data-test="team-form-error">{{ error }}</LdAlert>
      <LdTextField
        v-model="name"
        :label="t('teams.nameLabel')"
        :placeholder="t('teams.namePlaceholder')"
        :error="nameError"
        name="team_name"
        required
      />
      <fieldset v-if="candidates" class="ld-tform__pick">
        <legend class="ld-field__label">
          {{ t('teams.newTeamMembers', { max: maxSize ?? '—' }) }}
        </legend>
        <p v-if="candidates.length === 0" class="ld-muted">{{ t('teams.newTeamNoCandidates') }}</p>
        <label v-for="s in candidates" :key="s.id" class="ld-tform__check">
          <input
            v-model="selection"
            type="checkbox"
            :value="s.id"
            :disabled="full && !selection.includes(s.id)"
          />
          {{ s.full_name }}
        </label>
      </fieldset>
    </form>
    <template #footer>
      <LdButton variant="ghost" :disabled="busy" @click="emit('cancel')">
        {{ t('common2.cancel') }}
      </LdButton>
      <LdButton :loading="busy" data-test="team-form-save" @click="save">
        {{ saveLabel }}
      </LdButton>
    </template>
  </LdDialog>
</template>

<style scoped>
.ld-tform__pick {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
  max-height: 16rem;
  overflow-y: auto;
}

.ld-tform__check {
  display: flex;
  align-items: center;
  gap: var(--ld-space-2);
  cursor: pointer;
}
</style>
