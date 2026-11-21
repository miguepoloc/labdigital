<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { coursesApi, type Course } from '@/api/courses'
import LdAlert from '@/components/LdAlert.vue'
import LdBadge from '@/components/LdBadge.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import LdTextField from '@/components/LdTextField.vue'
import { t } from '@/i18n'
import CourseFormDialog from './CourseFormDialog.vue'
import { courseErrorMessage } from './courseErrors'

const router = useRouter()
const courses = ref<Course[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

const code = ref('')
const joining = ref(false)
const joinError = ref<string | null>(null)
const joinStatus = ref<string | null>(null)
const creating = ref(false)

const teaching = computed(() => courses.value.filter((c) => c.my_role === 'docente'))
const studying = computed(() => courses.value.filter((c) => c.my_role === 'estudiante'))
const groups = computed(() => [
  {
    key: 'teacher',
    title: t('courses.asTeacher'),
    items: teaching.value,
    empty: t('courses.emptyTeacher'),
  },
  {
    key: 'student',
    title: t('courses.asStudent'),
    items: studying.value,
    empty: t('courses.emptyStudent'),
  },
])

async function load() {
  loading.value = true
  loadError.value = null
  try {
    courses.value = await coursesApi.list()
  } catch (e) {
    loadError.value = courseErrorMessage(e)
  } finally {
    loading.value = false
  }
}

async function join() {
  joinError.value = null
  joinStatus.value = null
  const value = code.value.trim()
  if (!value) {
    joinError.value = t('validation.required')
    return
  }
  joining.value = true
  try {
    const course = await coursesApi.join(value)
    code.value = ''
    joinStatus.value = t('courses.joined', { name: course.name })
    const i = courses.value.findIndex((c) => c.id === course.id)
    if (i >= 0) courses.value.splice(i, 1, course)
    else courses.value.push(course)
  } catch (e) {
    joinError.value = courseErrorMessage(e)
  } finally {
    joining.value = false
  }
}

function onCreated(course: Course) {
  creating.value = false
  void router.push({ name: 'course', params: { id: course.id }, query: { nuevo: '1' } })
}

function statusBadge(c: Course): { tone: 'warning' | 'danger' | 'neutral'; text: string } | null {
  if (c.my_status === 'pending') return { tone: 'warning', text: t('courses.pending') }
  if (c.my_status === 'rejected') return { tone: 'danger', text: t('courses.rejected') }
  if (c.my_status === 'removed') return { tone: 'neutral', text: t('courses.removed') }
  return null
}

onMounted(load)
</script>

<template>
  <div class="ld-stack">
    <header class="ld-courses__head">
      <div>
        <h1>{{ t('courses.title') }}</h1>
        <p class="ld-muted">{{ t('courses.subtitle') }}</p>
      </div>
      <LdButton variant="secondary" data-test="create-course" @click="creating = true">
        {{ t('courses.create') }}
      </LdButton>
    </header>

    <LdCard :title="t('courses.joinTitle')">
      <form class="ld-courses__join" novalidate data-test="join-form" @submit.prevent="join">
        <LdTextField
          v-model="code"
          :label="t('courses.joinCode')"
          name="join_code"
          autocomplete="off"
          :help="t('courses.joinHelp')"
          :error="joinError"
        />
        <LdButton type="submit" :loading="joining" data-test="join-submit">
          {{ joining ? t('courses.joining') : t('courses.joinSubmit') }}
        </LdButton>
      </form>
      <LdAlert v-if="joinStatus" variant="success" data-test="join-status">{{
        joinStatus
      }}</LdAlert>
    </LdCard>

    <LdSpinner v-if="loading" size="lg" :label="t('common2.loading')" />
    <LdAlert v-else-if="loadError" variant="danger">
      {{ loadError }}
      <template #actions>
        <LdButton size="sm" variant="secondary" @click="load">{{ t('common2.retry') }}</LdButton>
      </template>
    </LdAlert>
    <LdEmptyState
      v-else-if="courses.length === 0"
      :title="t('courses.emptyTitle')"
      :body="t('courses.emptyBody')"
      :heading-level="2"
      data-test="courses-empty"
    />
    <template v-else>
      <section
        v-for="group in groups"
        :key="group.key"
        class="ld-stack"
        :data-test="`courses-${group.key}`"
      >
        <h2 class="ld-courses__group">{{ group.title }}</h2>
        <p v-if="group.items.length === 0" class="ld-muted">{{ group.empty }}</p>
        <ul v-else class="ld-courses__grid">
          <li v-for="c in group.items" :key="c.id" data-test="course-item">
            <RouterLink :to="{ name: 'course', params: { id: c.id } }" class="ld-courses__card">
              <span class="ld-courses__name">{{ c.name }}</span>
              <span class="ld-muted ld-courses__meta">
                {{ c.period }} · {{ t('courses.by', { name: c.owner_name }) }}
              </span>
              <span class="ld-row ld-courses__badges">
                <LdBadge v-if="c.my_role === 'docente'" tone="info">{{
                  t('courses.teacherBadge')
                }}</LdBadge>
                <LdBadge v-if="statusBadge(c)" :tone="statusBadge(c)!.tone">{{
                  statusBadge(c)!.text
                }}</LdBadge>
                <LdBadge v-if="c.student_count != null">{{
                  t('courses.studentsCount', { n: c.student_count })
                }}</LdBadge>
                <LdBadge v-if="c.pending_count" tone="accent">{{
                  t('courses.pendingCount', { n: c.pending_count })
                }}</LdBadge>
              </span>
            </RouterLink>
          </li>
        </ul>
      </section>
    </template>

    <CourseFormDialog v-if="creating" @close="creating = false" @saved="onCreated" />
  </div>
</template>

<style scoped>
.ld-courses__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ld-space-3);
}

.ld-courses__join {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--ld-space-3);
}

.ld-courses__join > :first-child {
  flex: 1 1 16rem;
}

.ld-courses__join > :last-child {
  margin-top: 1.6rem;
}

.ld-courses__group {
  font-size: var(--ld-text-lg);
  margin: 0;
}

.ld-courses__grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--ld-space-3);
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));
}

.ld-courses__card {
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-2);
  height: 100%;
  padding: var(--ld-space-4) var(--ld-space-5);
  border: 1px solid var(--ld-color-border);
  border-radius: var(--ld-radius-lg);
  background: var(--ld-color-surface);
  color: inherit;
  text-decoration: none;
  box-shadow: var(--ld-shadow-sm);
  transition: box-shadow var(--ld-duration) var(--ld-ease);
}

.ld-courses__card:hover {
  box-shadow: var(--ld-shadow-md);
}

.ld-courses__card:focus-visible {
  outline: none;
  box-shadow: var(--ld-focus-ring);
}

.ld-courses__name {
  font-family: var(--ld-font-heading);
  font-weight: 700;
  font-size: var(--ld-text-lg);
  color: var(--ld-color-primary);
}

.ld-courses__meta {
  font-size: var(--ld-text-sm);
}

.ld-courses__badges {
  gap: var(--ld-space-2);
}
</style>
