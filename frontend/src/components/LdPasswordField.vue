<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { t } from '@/i18n'
import { messages } from '@/i18n'
import { passwordStrength } from '@/lib/validation'

const model = defineModel<string>({ default: '' })

const props = withDefaults(
  defineProps<{
    label: string
    error?: string | null
    help?: string
    required?: boolean
    disabled?: boolean
    autocomplete?: 'current-password' | 'new-password'
    name?: string
    /** Muestra el medidor de seguridad (para contraseñas nuevas). */
    meter?: boolean
    id?: string
  }>(),
  { error: null, help: undefined, autocomplete: 'current-password' },
)

const emit = defineEmits<{ blur: [FocusEvent] }>()

const visible = ref(false)
const autoId = useId()
const inputId = computed(() => props.id ?? `p-${autoId}`)
const helpId = computed(() => `${inputId.value}-help`)
const errorId = computed(() => `${inputId.value}-error`)
const meterId = computed(() => `${inputId.value}-meter`)
const describedBy = computed(
  () =>
    [
      props.help ? helpId.value : null,
      props.meter ? meterId.value : null,
      props.error ? errorId.value : null,
    ]
      .filter(Boolean)
      .join(' ') || undefined,
)

const score = computed(() => passwordStrength(model.value))
const levelText = computed(() => messages.password.levels[score.value] ?? '')

const input = ref<HTMLInputElement | null>(null)
defineExpose({ focus: () => input.value?.focus() })
</script>

<template>
  <div class="ld-field" :class="{ 'ld-field--invalid': !!error }">
    <label class="ld-field__label" :for="inputId">
      {{ label }}<span v-if="required" class="ld-field__req" aria-hidden="true">*</span>
    </label>
    <div class="ld-field__control">
      <input
        :id="inputId"
        ref="input"
        v-model="model"
        class="ld-field__input ld-pw__input"
        :type="visible ? 'text' : 'password'"
        :name="name"
        :required="required"
        :disabled="disabled"
        :autocomplete="autocomplete"
        autocapitalize="off"
        spellcheck="false"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
        @blur="emit('blur', $event)"
      />
      <button
        type="button"
        class="ld-pw__toggle"
        :aria-pressed="visible ? 'true' : 'false'"
        :aria-controls="inputId"
        :disabled="disabled"
        @click="visible = !visible"
      >
        {{ visible ? t('fields.hidePassword') : t('fields.showPassword') }}
      </button>
    </div>
    <p v-if="help" :id="helpId" class="ld-field__help">{{ help }}</p>
    <div v-if="meter" :id="meterId" class="ld-pw__meter" :data-score="score">
      <div class="ld-pw__bars" aria-hidden="true">
        <span v-for="i in 4" :key="i" class="ld-pw__bar" :class="{ 'is-on': i <= score }" />
      </div>
      <span class="ld-pw__level" aria-live="polite">
        {{ model ? t('password.strength', { level: levelText }) : '' }}
      </span>
    </div>
    <p :id="errorId" class="ld-field__error" aria-live="polite">{{ error ?? '' }}</p>
  </div>
</template>

<style scoped>
.ld-pw__input {
  padding-right: 6.5rem;
}

.ld-pw__toggle {
  position: absolute;
  right: var(--ld-space-1);
  top: 50%;
  transform: translateY(-50%);
  min-height: 2.25rem;
  padding: 0 var(--ld-space-2);
  border: 0;
  border-radius: var(--ld-radius-sm);
  background: transparent;
  color: var(--ld-color-link);
  font-size: var(--ld-text-sm);
  font-weight: 500;
  cursor: pointer;
}

.ld-pw__toggle:hover {
  background: var(--ld-color-surface-2);
}

.ld-pw__toggle:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-pw__meter {
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-1);
}

.ld-pw__bars {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--ld-space-1);
}

.ld-pw__bar {
  height: 4px;
  border-radius: var(--ld-radius-full);
  background: var(--ld-color-border);
}

.ld-pw__meter[data-score='1'] .is-on {
  background: var(--ld-color-danger);
}

.ld-pw__meter[data-score='2'] .is-on {
  background: var(--um-gold);
}

.ld-pw__meter[data-score='3'] .is-on,
.ld-pw__meter[data-score='4'] .is-on {
  background: var(--ld-color-success);
}

.ld-pw__level {
  font-size: var(--ld-text-xs);
  color: var(--ld-color-text-muted);
  min-height: 1em;
}
</style>
