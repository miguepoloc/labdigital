<script setup lang="ts">
import { reactive, ref } from 'vue'
import { coursesApi, type Course, type CourseInput } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdDialog from '@/components/LdDialog.vue'
import LdTextArea from '@/components/LdTextArea.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import { courseErrorMessage, fieldErrors } from './courseErrors'

/** Crear (sin `course`) o editar un curso. */
const props = defineProps<{ course?: Course | null }>()
const emit = defineEmits<{ close: []; saved: [Course] }>()

const form = reactive<CourseInput>({
  name: props.course?.name ?? '',
  period: props.course?.period ?? '',
  description: props.course?.description ?? '',
})
const errors = ref<Record<string, string>>({})
const formError = ref<string | null>(null)
const saving = ref(false)

async function submit() {
  errors.value = {}
  formError.value = null
  if (!form.name.trim()) errors.value.name = t('validation.required')
  if (!form.period.trim()) errors.value.period = t('validation.required')
  if (Object.keys(errors.value).length) return
  saving.value = true
  try {
    const saved = props.course
      ? await coursesApi.update(props.course.id, { ...form })
      : await coursesApi.create({ ...form })
    emit('saved', saved)
  } catch (e) {
    errors.value = fieldErrors(e)
    formError.value = courseErrorMessage(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <LdDialog
    :title="course ? t('courses.editTitle') : t('courses.createTitle')"
    :persistent="saving"
    @close="emit('close')"
  >
    <form class="ld-form" novalidate data-test="course-form" @submit.prevent="submit">
      <p v-if="!course" class="ld-muted">{{ t('courses.createHelp') }}</p>
      <LdAlert v-if="formError" variant="danger">{{ formError }}</LdAlert>
      <LdTextField
        v-model="form.name"
        :label="t('courses.name')"
        name="name"
        :placeholder="t('courses.namePlaceholder')"
        :error="errors.name"
        required
      />
      <LdTextField
        v-model="form.period"
        :label="t('courses.period')"
        name="period"
        :placeholder="t('courses.periodPlaceholder')"
        :error="errors.period"
        required
      />
      <LdTextArea
        v-model="form.description"
        :label="t('courses.description')"
        name="description"
        :rows="3"
        :error="errors.description"
      />
      <div class="ld-form__actions">
        <LdButton type="submit" :loading="saving" data-test="course-save">
          {{ saving ? t('courses.saving') : course ? t('courses.save') : t('courses.create') }}
        </LdButton>
        <LdButton variant="ghost" :disabled="saving" @click="emit('close')">
          {{ t('common2.cancel') }}
        </LdButton>
      </div>
    </form>
  </LdDialog>
</template>
