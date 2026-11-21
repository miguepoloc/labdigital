<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { coursesApi, labsApi, type Course, type Lab } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTabs, { type TabItem } from '@/components/LdTabs.vue'
import { t } from '@/i18n'
import LabList from '../labs/LabList.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import CourseFormDialog from './CourseFormDialog.vue'
import CourseMembersPanel from './CourseMembersPanel.vue'
import { courseErrorMessage } from './courseErrors'

const route = useRoute()
const courseId = computed(() => String(route.params.id))

const course = ref<Course | null>(null)
const labs = ref<Lab[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const labsError = ref<string | null>(null)
const tab = ref('labs')
const editing = ref(false)
const status = ref<{ kind: 'success' | 'danger'; text: string } | null>(null)
const confirmRotate = ref(false)
const rotating = ref(false)

const isTeacher = computed(() => course.value?.my_role === 'docente')
const isActive = computed(() => isTeacher.value || course.value?.my_status === 'active')
const tabs = computed<TabItem[]>(() => [
  { id: 'labs', label: t('courses.tabs.labs') },
  { id: 'requests', label: t('courses.tabs.requests'), count: course.value?.pending_count },
  { id: 'members', label: t('courses.tabs.members') },
  { id: 'settings', label: t('courses.tabs.settings') },
])

async function loadLabs() {
  labsError.value = null
  try {
    labs.value = await labsApi.list(courseId.value)
  } catch (e) {
    labsError.value = courseErrorMessage(e)
  }
}

async function load() {
  if (route.name !== 'course') return // saliendo de la página
  loading.value = true
  loadError.value = null
  course.value = null
  labs.value = []
  try {
    course.value = await coursesApi.get(courseId.value)
    if (isActive.value) await loadLabs()
    if (route.query.nuevo === '1' && isTeacher.value) {
      status.value = { kind: 'success', text: t('courses.created') }
      tab.value = 'settings'
    }
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function refreshCourse() {
  try {
    course.value = await coursesApi.get(courseId.value)
  } catch {
    /* el contador es informativo */
  }
}

function onSaved(c: Course) {
  course.value = c
  editing.value = false
  status.value = { kind: 'success', text: t('courses.saved') }
}

async function rotate() {
  if (!course.value) return
  rotating.value = true
  status.value = null
  try {
    const { join_code } = await coursesApi.rotateCode(course.value.id)
    course.value = { ...course.value, join_code }
    status.value = { kind: 'success', text: t('courses.code.rotated', { code: join_code }) }
  } catch (e) {
    status.value = { kind: 'danger', text: courseErrorMessage(e) }
  } finally {
    rotating.value = false
    confirmRotate.value = false
  }
}

async function copyCode() {
  if (!course.value?.join_code) return
  try {
    await navigator.clipboard.writeText(course.value.join_code)
    status.value = { kind: 'success', text: t('courses.code.copied') }
  } catch {
    /* sin portapapeles: el código sigue visible */
  }
}

watch(courseId, load, { immediate: true })
</script>

<template>
  <div class="ld-stack">
    <RouterLink :to="{ name: 'courses' }" class="ld-course__back">
      ← {{ t('courses.backToCourses') }}
    </RouterLink>

    <LdSpinner v-if="loading" size="lg" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger" data-test="course-error">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{ t('common2.retry') }}</LdButton>
      </template>
    </LdAlert>

    <template v-else-if="course">
      <header>
        <h1>{{ course.name }}</h1>
        <p class="ld-muted">
          {{ course.period }} · {{ t('courses.by', { name: course.owner_name }) }}
        </p>
        <p v-if="course.description">{{ course.description }}</p>
      </header>

      <LdAlert v-if="status" :variant="status.kind" data-test="course-status">
        {{ status.text }}
      </LdAlert>

      <!-- Estudiante sin membresía activa -->
      <LdAlert
        v-if="!isActive"
        :variant="course.my_status === 'pending' ? 'info' : 'warning'"
        :title="t(`courses.${course.my_status === 'active' ? 'pending' : course.my_status}`)"
        data-test="membership-notice"
      >
        {{
          course.my_status === 'pending'
            ? t('courses.pendingBody')
            : course.my_status === 'rejected'
              ? t('courses.rejectedBody')
              : t('courses.removedBody')
        }}
      </LdAlert>

      <!-- Estudiante activo -->
      <section v-else-if="!isTeacher" class="ld-stack" data-test="student-view">
        <h2>{{ t('labs.listTitle') }}</h2>
        <LdAlert v-if="labsError" variant="danger">{{ labsError }}</LdAlert>
        <LdEmptyState
          v-else-if="labs.length === 0"
          :title="t('labs.emptyTitle')"
          :body="t('labs.emptyBody')"
        />
        <LabList v-else :labs="labs" :teacher="false" />
      </section>

      <!-- Docente -->
      <LdTabs
        v-else
        v-model="tab"
        :tabs="tabs"
        :label="t('courses.tabs.label')"
        data-test="teacher-view"
      >
        <template #default="{ active }">
          <section v-if="active === 'labs'" class="ld-stack">
            <div class="ld-course__toolbar">
              <LdButton :to="{ name: 'lab-new', params: { id: course.id } }" data-test="new-lab">
                {{ t('labs.create') }}
              </LdButton>
              <LdButton
                variant="secondary"
                :href="coursesApi.gradesCsvUrl(course.id)"
                download="notas.csv"
                data-test="export-grades"
                :title="t('courses.grades.help')"
              >
                {{ t('courses.grades.export') }}
              </LdButton>
            </div>
            <LdAlert v-if="labsError" variant="danger">{{ labsError }}</LdAlert>
            <LdEmptyState
              v-else-if="labs.length === 0"
              :title="t('labs.emptyTeacherTitle')"
              :body="t('labs.emptyTeacherBody')"
            />
            <LabList v-else :labs="labs" :teacher="true" />
          </section>

          <CourseMembersPanel
            v-else-if="active === 'requests'"
            :course-id="course.id"
            mode="pending"
            @changed="refreshCourse"
          />
          <CourseMembersPanel
            v-else-if="active === 'members'"
            :course-id="course.id"
            mode="active"
            @changed="refreshCourse"
          />

          <section v-else class="ld-course__settings">
            <LdCard :title="t('courses.code.title')">
              <p class="ld-course__code" data-test="join-code">{{ course.join_code }}</p>
              <p class="ld-muted">{{ t('courses.code.help') }}</p>
              <template #footer>
                <LdButton size="sm" variant="secondary" @click="copyCode">
                  {{ t('courses.code.copy') }}
                </LdButton>
                <LdButton
                  size="sm"
                  variant="ghost"
                  data-test="rotate-code"
                  @click="confirmRotate = true"
                >
                  {{ t('courses.code.rotate') }}
                </LdButton>
              </template>
            </LdCard>
            <LdCard :title="t('courses.editTitle')">
              <dl class="ld-course__dl">
                <dt>{{ t('courses.name') }}</dt>
                <dd>{{ course.name }}</dd>
                <dt>{{ t('courses.period') }}</dt>
                <dd>{{ course.period }}</dd>
                <dt>{{ t('courses.description') }}</dt>
                <dd>{{ course.description || '—' }}</dd>
              </dl>
              <template #footer>
                <LdButton
                  size="sm"
                  variant="secondary"
                  data-test="edit-course"
                  @click="editing = true"
                >
                  {{ t('labs.edit') }}
                </LdButton>
              </template>
            </LdCard>
          </section>
        </template>
      </LdTabs>

      <CourseFormDialog v-if="editing" :course="course" @close="editing = false" @saved="onSaved" />
      <ConfirmDialog
        v-if="confirmRotate"
        :title="t('courses.code.rotate')"
        :message="t('courses.code.rotateConfirm')"
        :confirm-label="t('courses.code.rotate')"
        :busy="rotating"
        @cancel="confirmRotate = false"
        @confirm="rotate"
      />
    </template>
  </div>
</template>

<style scoped>
.ld-course__back {
  align-self: flex-start;
  font-size: var(--ld-text-sm);
}

.ld-course__toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ld-space-2);
}

.ld-course__settings {
  display: grid;
  gap: var(--ld-space-4);
}

@media (min-width: 900px) {
  .ld-course__settings {
    grid-template-columns: 1fr 1fr;
  }
}

.ld-course__code {
  margin: 0;
  font-family: var(--ld-font-mono);
  font-size: var(--ld-text-2xl);
  font-weight: 700;
  letter-spacing: 0.15em;
  color: var(--ld-color-primary);
}

.ld-course__dl {
  margin: 0;
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--ld-space-2) var(--ld-space-4);
}

.ld-course__dl dt {
  font-weight: 600;
}

.ld-course__dl dd {
  margin: 0;
}
</style>
