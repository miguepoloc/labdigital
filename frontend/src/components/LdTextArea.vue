<script setup lang="ts">
import { computed, useId } from 'vue'

const model = defineModel<string>({ default: '' })

const props = withDefaults(
  defineProps<{
    label: string
    error?: string | null
    help?: string
    required?: boolean
    disabled?: boolean
    rows?: number
    name?: string
    placeholder?: string
    id?: string
    /** Fuente monoespaciada (Markdown, código). */
    mono?: boolean
  }>(),
  { error: null, help: undefined, rows: 4 },
)

const autoId = useId()
const inputId = computed(() => props.id ?? `ta-${autoId}`)
const helpId = computed(() => `${inputId.value}-help`)
const errorId = computed(() => `${inputId.value}-error`)
const describedBy = computed(
  () =>
    [props.help ? helpId.value : null, props.error ? errorId.value : null]
      .filter(Boolean)
      .join(' ') || undefined,
)
</script>

<template>
  <div class="ld-field" :class="{ 'ld-field--invalid': !!error }">
    <label class="ld-field__label" :for="inputId">
      {{ label }}<span v-if="required" class="ld-field__req" aria-hidden="true">*</span>
    </label>
    <textarea
      :id="inputId"
      v-model="model"
      class="ld-field__input ld-textarea"
      :class="{ 'ld-textarea--mono': mono }"
      :name="name"
      :rows="rows"
      :required="required"
      :disabled="disabled"
      :placeholder="placeholder"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="describedBy"
    />
    <p v-if="help" :id="helpId" class="ld-field__help">{{ help }}</p>
    <p :id="errorId" class="ld-field__error" aria-live="polite">{{ error ?? '' }}</p>
  </div>
</template>

<style scoped>
.ld-textarea {
  resize: vertical;
  min-height: 5rem;
  font: inherit;
  line-height: var(--ld-leading-normal);
}

.ld-textarea--mono {
  font-family: var(--ld-font-mono);
  font-size: var(--ld-text-sm);
}
</style>
