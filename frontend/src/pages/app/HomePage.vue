<script setup lang="ts">
/**
 * Inicio (LD-16): resumen de proyectos recientes, cursos y próximas entregas.
 * Cada tarjeta carga y falla por separado: un error en una no vacía las demás.
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { coursesApi, labsApi, type Course, type Lab } from '@/api/courses'
import { projectsApi, type ProjectSummary } from '@/api/projects'
import LdAlert from '@/components/LdAlert.vue'
import LdBadge from '@/components/LdBadge.vue'
import LdButton from '@/components/LdButton.vue'
import LdCard from '@/components/LdCard.vue'
import LdEmptyState from '@/components/LdEmptyState.vue'
import LdSpinner from '@/components/LdSpinner.vue'
import { t, type MessageKey } from '@/i18n'
import { formatBogotaShort } from '@/lib/bogota'
import { errorMessage } from '@/lib/errors'
import { formatDateTime } from '@/lib/format'
import CourseFormDialog from './courses/CourseFormDialog.vue'
import { courseErrorMessage } from './courses/courseErrors'
import { deadlineState } from './labs/labRules'
import SubmissionStatusBadge from './submissions/SubmissionStatusBadge.vue'
import { useSessionStore } from '@/stores/session'

const MAX_PROJECTS = 4
/** Tope de cursos para los que se piden labs (una petición por curso). */
const MAX_LAB_COURSES = 6
const MAX_UPCOMING = 5

const session = useSessionStore()
const router = useRouter()
const firstName = computed(() => session.me?.full_name.split(/\s+/)[0] ?? '')

function plural(n: number, one: MessageKey, many: MessageKey): string {
  return n === 1 ? t(one) : t(many, { n })
}

// ---- Proyectos ----
const projects = ref<ProjectSummary[]>([])
const projectsLoading = ref(true)
const projectsError = ref<string | null>(null)

async function loadProjects() {
  projectsLoading.value = true
  projectsError.value = null
  try {
    const list = await projectsApi.list()
    projects.value = [...list]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .slice(0, MAX_PROJECTS)
  } catch (e) {
    projectsError.value = errorMessage(e)
  } finally {
    projectsLoading.value = false
  }
}

// ---- Cursos y labs ----
const courses = ref<Course[]>([])
const coursesLoading = ref(true)
const coursesError = ref<string | null>(null)
const labsByCourse = ref<Record<string, Lab[]>>({})
const labsLoading = ref(true)
const labsError = ref(false)
const creating = ref(false)

/** Activos primero, luego solicitudes pendientes; rechazados/retirados no se muestran. */
const visibleCourses = computed(() => [
  ...courses.value.filter((c) => c.my_status === 'active'),
  ...courses.value.filter((c) => c.my_status === 'pending'),
])

async function loadLabs(active: Course[]) {
  labsLoading.value = true
  labsError.value = false
  const results = await Promise.allSettled(
    active.slice(0, MAX_LAB_COURSES).map(async (c) => [c.id, await labsApi.list(c.id)] as const),
  )
  const map: Record<string, Lab[]> = {}
  for (const r of results) {
    if (r.status === 'fulfilled') map[r.value[0]] = r.value[1]
    else labsError.value = true
  }
  labsByCourse.value = map
  labsLoading.value = false
}

async function loadCourses() {
  coursesLoading.value = true
  coursesError.value = null
  try {
    courses.value = await coursesApi.list()
  } catch (e) {
    coursesError.value = courseErrorMessage(e)
    labsLoading.value = false
    return
  } finally {
    coursesLoading.value = false
  }
  await loadLabs(courses.value.filter((c) => c.my_status === 'active'))
}

interface Upcoming {
  lab: Lab
  course: Course
  /** Sólo para estudiantes sin entrega en un lab vencido que admite tardías. */
  late: boolean
}

const upcoming = computed<Upcoming[]>(() => {
  const now = Date.now()
  const items: Upcoming[] = []
  for (const course of courses.value) {
    for (const lab of labsByCourse.value[course.id] ?? []) {
      if (!lab.published_at) continue
      const future = !!lab.due_at && Date.parse(lab.due_at) >= now
      const state = deadlineState(lab, now)
      if (course.my_role === 'docente') {
        if (future) items.push({ lab, course, late: false })
      } else if (future || (!lab.my_submission && state !== 'closed')) {
        items.push({ lab, course, late: !lab.my_submission && state === 'late' })
      }
    }
  }
  const due = (x: Upcoming) => (x.lab.due_at ? Date.parse(x.lab.due_at) : Infinity)
  return items.sort((a, b) => due(a) - due(b)).slice(0, MAX_UPCOMING)
})

function onCreated(course: Course) {
  creating.value = false
  void router.push({ name: 'course', params: { id: course.id }, query: { nuevo: '1' } })
}

onMounted(() => {
  void loadProjects()
  void loadCourses()
})
</script>

<template>
  <div class="ld-stack">
    <header>
      <h1>{{ t('home.title', { name: firstName }) }}</h1>
      <p class="ld-muted">{{ t('home.subtitle') }}</p>
    </header>
    <LdAlert v-if="session.me && !session.me.email_verified" variant="warning">
      {{ t('home.emailUnverified') }}
    </LdAlert>
    <div class="ld-home__grid">
      <!-- Proyectos -->
      <LdCard :title="t('home.projectsTitle')" data-test="home-projects">
        <LdSpinner v-if="projectsLoading" :label="t('home.loading')" />
        <LdAlert v-else-if="projectsError" variant="danger" data-test="home-projects-error">
          {{ projectsError }}
          <template #actions>
            <LdButton size="sm" variant="secondary" @click="loadProjects">{{
              t('home.retry')
            }}</LdButton>
          </template>
        </LdAlert>
        <LdEmptyState
          v-else-if="projects.length === 0"
          :title="t('home.projectsEmpty')"
          :body="t('home.projectsEmptyBody')"
          data-test="home-projects-empty"
        >
          <LdButton :to="{ name: 'projects' }">{{ t('home.projectsCreate') }}</LdButton>
        </LdEmptyState>
        <ul v-else class="ld-home__list">
          <li v-for="p in projects" :key="p.id" class="ld-home__item" data-test="home-project">
            <div class="ld-home__info">
              <RouterLink :to="{ name: 'project', params: { id: p.id } }" class="ld-home__name">{{
                p.name
              }}</RouterLink>
              <span class="ld-muted ld-home__meta">
                {{ t(`projects.modules.${p.module}`) }} ·
                {{ t('home.projectEdited', { date: formatDateTime(p.updated_at) }) }}
              </span>
            </div>
            <LdButton
              size="sm"
              variant="secondary"
              :to="{ name: 'fpga', params: { projectId: p.id } }"
              :aria-label="t('home.projectOpenLabel', { name: p.name })"
              data-test="home-project-open"
              >{{ t('home.projectOpen') }}</LdButton
            >
          </li>
        </ul>
        <template v-if="!projectsLoading && !projectsError && projects.length" #footer>
          <div class="ld-row ld-home__actions">
            <LdButton size="sm" :to="{ name: 'projects' }">{{ t('home.projectsNew') }}</LdButton>
            <LdButton size="sm" variant="ghost" :to="{ name: 'projects' }">{{
              t('home.projectsAll')
            }}</LdButton>
          </div>
        </template>
      </LdCard>

      <!-- Cursos -->
      <LdCard :title="t('home.coursesTitle')" data-test="home-courses">
        <LdSpinner v-if="coursesLoading" :label="t('home.loading')" />
        <LdAlert v-else-if="coursesError" variant="danger" data-test="home-courses-error">
          {{ coursesError }}
          <template #actions>
            <LdButton size="sm" variant="secondary" @click="loadCourses">{{
              t('home.retry')
            }}</LdButton>
          </template>
        </LdAlert>
        <LdEmptyState
          v-else-if="visibleCourses.length === 0"
          :title="t('home.coursesEmpty')"
          :body="t('home.coursesEmptyBody')"
          data-test="home-courses-empty"
        >
          <LdButton :to="{ name: 'courses' }">{{ t('home.coursesJoin') }}</LdButton>
          <LdButton variant="ghost" @click="creating = true">{{
            t('home.coursesCreate')
          }}</LdButton>
        </LdEmptyState>
        <ul v-else class="ld-home__list">
          <li v-for="c in visibleCourses" :key="c.id" class="ld-home__item" data-test="home-course">
            <div class="ld-home__info">
              <RouterLink :to="{ name: 'course', params: { id: c.id } }" class="ld-home__name">{{
                c.name
              }}</RouterLink>
              <span class="ld-muted ld-home__meta">{{ c.period }}</span>
              <span class="ld-row ld-home__badges">
                <LdBadge :tone="c.my_role === 'docente' ? 'info' : 'neutral'">{{
                  c.my_role === 'docente' ? t('home.roleDocente') : t('home.roleEstudiante')
                }}</LdBadge>
                <LdBadge v-if="c.my_status === 'pending'" tone="warning" data-test="home-pending">{{
                  t('home.pending')
                }}</LdBadge>
                <template v-if="c.my_role === 'docente'">
                  <LdBadge v-if="c.student_count != null">{{
                    plural(c.student_count, 'home.studentsOne', 'home.studentsMany')
                  }}</LdBadge>
                  <LdBadge v-if="c.pending_count" tone="accent" data-test="home-requests">{{
                    plural(c.pending_count, 'home.requestsOne', 'home.requestsMany')
                  }}</LdBadge>
                  <LdBadge v-if="labsByCourse[c.id]">{{
                    plural(labsByCourse[c.id]!.length, 'home.labsOne', 'home.labsMany')
                  }}</LdBadge>
                </template>
              </span>
            </div>
          </li>
        </ul>
        <template v-if="!coursesLoading && !coursesError && visibleCourses.length" #footer>
          <div class="ld-row ld-home__actions">
            <LdButton size="sm" :to="{ name: 'courses' }">{{ t('home.coursesJoin') }}</LdButton>
            <LdButton size="sm" variant="secondary" @click="creating = true">{{
              t('home.coursesCreate')
            }}</LdButton>
            <LdButton size="sm" variant="ghost" :to="{ name: 'courses' }">{{
              t('home.coursesAll')
            }}</LdButton>
          </div>
        </template>
      </LdCard>

      <!-- Próximas entregas (sólo si hay cursos activos) -->
      <LdCard
        v-if="!coursesLoading && !coursesError && courses.some((c) => c.my_status === 'active')"
        :title="t('home.upcomingTitle')"
        class="ld-home__wide"
        data-test="home-upcoming"
      >
        <LdSpinner v-if="labsLoading" :label="t('home.loading')" />
        <template v-else>
          <LdAlert v-if="labsError" variant="warning" data-test="home-upcoming-error">
            {{ t('home.upcomingError') }}
            <template #actions>
              <LdButton size="sm" variant="secondary" @click="loadCourses">{{
                t('home.retry')
              }}</LdButton>
            </template>
          </LdAlert>
          <LdEmptyState
            v-if="upcoming.length === 0 && !labsError"
            :title="t('home.upcomingEmpty')"
            :body="t('home.upcomingEmptyBody')"
            data-test="home-upcoming-empty"
          />
          <ul v-else-if="upcoming.length" class="ld-home__list">
            <li
              v-for="u in upcoming"
              :key="u.lab.id"
              class="ld-home__item"
              data-test="home-upcoming-item"
            >
              <div class="ld-home__info">
                <RouterLink :to="{ name: 'lab', params: { id: u.lab.id } }" class="ld-home__name">{{
                  u.lab.title
                }}</RouterLink>
                <span class="ld-muted ld-home__meta">
                  {{ u.course.name }} ·
                  {{
                    u.lab.due_at
                      ? t('home.upcomingDue', { date: formatBogotaShort(u.lab.due_at) })
                      : t('home.upcomingNoDue')
                  }}
                </span>
              </div>
              <template v-if="u.course.my_role === 'estudiante'">
                <SubmissionStatusBadge
                  v-if="u.lab.my_submission"
                  :submission="u.lab.my_submission"
                />
                <LdBadge v-else :tone="u.late ? 'warning' : 'neutral'">{{
                  u.late ? t('home.upcomingLate') : t('home.upcomingNotSubmitted')
                }}</LdBadge>
              </template>
            </li>
          </ul>
        </template>
      </LdCard>
    </div>

    <CourseFormDialog v-if="creating" @close="creating = false" @saved="onCreated" />
  </div>
</template>

<style scoped>
.ld-home__grid {
  display: grid;
  gap: var(--ld-space-4);
  align-items: start;
}

@media (min-width: 900px) {
  .ld-home__grid {
    grid-template-columns: 1fr 1fr;
  }

  .ld-home__wide {
    grid-column: 1 / -1;
  }
}

.ld-home__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
}

.ld-home__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ld-space-2) var(--ld-space-3);
  padding: var(--ld-space-3) 0;
  border-top: 1px solid var(--ld-color-border);
}

.ld-home__item:first-child {
  border-top: 0;
  padding-top: 0;
}

.ld-home__info {
  display: flex;
  flex-direction: column;
  gap: var(--ld-space-1);
  min-width: 0;
}

.ld-home__name {
  font-family: var(--ld-font-heading);
  font-weight: 700;
  color: var(--ld-color-primary);
  overflow-wrap: anywhere;
}

.ld-home__meta {
  font-size: var(--ld-text-sm);
}

.ld-home__badges,
.ld-home__actions {
  gap: var(--ld-space-2);
  flex-wrap: wrap;
}
</style>
