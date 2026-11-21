<script setup lang="ts">
/** Editor de la escala de nota del lab: numérica (mín., máx., decimales, aprobación) o aprobado/no aprobado. */
import { computed, ref, useId, watch } from 'vue'
import type { GradeScale } from '@/api/courses'
import { t } from '@/i18n'
import { describeScale, parseDecimal, validateScale } from './labRules'

const scale = defineModel<GradeScale>({ required: true })
defineProps<{ errors?: Record<string, string> }>()

const uid = useId()
const id = (k: string) => `gs-${uid}-${k}`

// Campos como texto para admitir coma decimal («3,0»).
const text = ref({
  min: String(scale.value.min ?? 0),
  max: String(scale.value.max ?? 5),
  decimals: String(scale.value.decimals ?? 1),
  pass_mark: scale.value.pass_mark === undefined ? '' : String(scale.value.pass_mark),
})

function sync(type: GradeScale['type'] = scale.value.type) {
  if (type === 'pass_fail') {
    scale.value = { type: 'pass_fail' }
    return
  }
  const pm = text.value.pass_mark.trim()
  scale.value = {
    type: 'numeric',
    min: parseDecimal(text.value.min) ?? Number.NaN,
    max: parseDecimal(text.value.max) ?? Number.NaN,
    decimals: /^\d+$/.test(text.value.decimals.trim()) ? Number(text.value.decimals) : Number.NaN,
    ...(pm ? { pass_mark: parseDecimal(pm) ?? Number.NaN } : {}),
  }
}

function setType(type: GradeScale['type']) {
  sync(type)
}

watch(text, () => sync(), { deep: true })

const localErrors = computed(() => validateScale(scale.value))
const preview = computed(() =>
  Object.keys(localErrors.value).length ? null : describeScale(scale.value),
)
</script>

<template>
  <fieldset class="ld-scale" data-test="grade-scale">
    <legend class="ld-field__label">{{ t('labEditor.scaleTitle') }}</legend>
    <div class="ld-scale__types" role="radiogroup">
      <label class="ld-scale__radio">
        <input
          type="radio"
          :name="id('type')"
          value="numeric"
          :checked="scale.type === 'numeric'"
          data-test="scale-numeric"
          @change="setType('numeric')"
        />
        {{ t('labEditor.scaleNumeric') }}
      </label>
      <label class="ld-scale__radio">
        <input
          type="radio"
          :name="id('type')"
          value="pass_fail"
          :checked="scale.type === 'pass_fail'"
          data-test="scale-pass-fail"
          @change="setType('pass_fail')"
        />
        {{ t('labEditor.scalePassFail') }}
      </label>
    </div>

    <div v-if="scale.type === 'numeric'" class="ld-scale__grid">
      <div
        v-for="field in ['min', 'max', 'decimals', 'pass_mark'] as const"
        :key="field"
        class="ld-field"
        :class="{ 'ld-field--invalid': !!(errors?.[field] ?? localErrors[field]) }"
      >
        <label class="ld-field__label" :for="id(field)">
          {{
            field === 'min'
              ? t('labEditor.min')
              : field === 'max'
                ? t('labEditor.max')
                : field === 'decimals'
                  ? t('labEditor.decimals')
                  : t('labEditor.passMark')
          }}
        </label>
        <input
          :id="id(field)"
          v-model="text[field]"
          class="ld-field__input"
          :name="`scale_${field}`"
          :inputmode="field === 'decimals' ? 'numeric' : 'decimal'"
          :placeholder="field === 'pass_mark' ? t('labEditor.passMarkHelp') : undefined"
          :aria-invalid="(errors?.[field] ?? localErrors[field]) ? 'true' : undefined"
          :aria-describedby="`${id(field)}-err`"
        />
        <p :id="`${id(field)}-err`" class="ld-field__error" aria-live="polite">
          {{ errors?.[field] ?? localErrors[field] ?? '' }}
        </p>
      </div>
    </div>
    <p v-if="preview" class="ld-muted ld-scale__preview" data-test="scale-preview">
      {{ t('labEditor.scalePreview', { desc: preview }) }}
    </p>
  </fieldset>
</template>

<style scoped>
.ld-scale {
  margin: 0;
  padding: var(--ld-space-4);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-md);
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-3);
}

.ld-scale legend {
  padding: 0 var(--ld-space-2);
}

.ld-scale__types {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-4);
}

.ld-scale__radio {
  display: inline-flex;
  align-items: center;
  gap: var(--ld-space-2);
  cursor: pointer;
}

.ld-scale__grid {
  display: grid;
  gap: var(--ld-space-3);
  grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
}

.ld-scale__preview {
  margin: 0;
  font-size: var(--ld-text-sm);
}
</style>
