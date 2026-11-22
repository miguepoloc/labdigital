<script setup lang="ts">
import { computed, ref, useId } from 'vue'

const model = defineModel<string>({ default: '' })

const props = withDefaults(
  defineProps<{
    label: string
    type?: 'text' | 'email' | 'password' | 'search' | 'tel' | 'url'
    /** Mensaje de error (se anuncia con aria-live). */
    error?: string | null
    help?: string
    required?: boolean
    disabled?: boolean
    readonly?: boolean
    autocomplete?: string
    inputmode?: 'text' | 'email' | 'numeric' | 'tel' | 'url' | 'search'
    name?: string
    placeholder?: string
    id?: string
  }>(),
  { type: 'text', error: null, help: undefined, autocomplete: undefined },
)

const emit = defineEmits<{ blur: [FocusEvent] }>()

const autoId = useId()
const inputId = computed(() => props.id ?? `f-${autoId}`)
const helpId = computed(() => `${inputId.value}-help`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(
  () =>
    [props.help ? helpId.value : null, props.error ? errorId.value : null]
      .filter(Boolean)
      .join(' ') || undefined,
)

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
        class="ld-field__input"
        :type="type"
        :name="name"
        :required="required"
        :disabled="disabled"
        :readonly="readonly"
        :autocomplete="autocomplete"
        :inputmode="inputmode"
        :placeholder="placeholder"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
        @blur="emit('blur', $event)"
      />
    </div>
    <p v-if="help" :id="helpId" class="ld-field__help">{{ help }}</p>
    <p :id="errorId" class="ld-field__error" aria-live="polite">{{ error ?? '' }}</p>
  </div>
</template>
