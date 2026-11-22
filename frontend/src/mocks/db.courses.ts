/**
 * Datos simulados de cursos, labs, equipos, entregas, archivos y (lectura mínima de) proyectos (LD-8b).
 * Las fechas se siembran relativas a "ahora" para que los estados (abierto, tardía, cerrado) sean estables.
 * Usuarios extra (docente demo y compañeros) se añaden a `db.users` de `db.ts` con `ensureCourseUsers()`.
 */
import type {
  CourseRole,
  DeadlinePolicy,
  GradeScale,
  MembershipStatus,
  SubmissionStatus,
  TeamMode,
} from '@/api/courses'
import type { FileKind } from '@/api/submissions'
import { DEMO_PASSWORD, db, findUserByEmail, type MockUser } from './db'

export interface MCourse {
  id: string
  name: string
  period: string
  description: string
  owner_id: string
  join_code: string
  created_at: string
  archived_at: string | null
}

export interface MMembership {
  course_id: string
  user_id: string
  role: CourseRole
  status: MembershipStatus
  requested_at: string
}

export interface MLab {
  id: string
  course_id: string
  title: string
  statement_md: string
  module: string
  published_at: string | null
  opens_at: string | null
  due_at: string | null
  deadline_policy: DeadlinePolicy
  team_mode: TeamMode
  max_team_size: number | null
  grade_scale: GradeScale
  allow_resubmission: boolean
  created_at: string
}

export interface MTeam {
  id: string
  lab_id: string
  name: string
  join_code: string
  locked: boolean
  member_ids: string[]
}

export interface MSubmission {
  id: string
  lab_id: string
  attempt: number
  student_id: string | null
  team_id: string | null
  submitted_by: string
  project_id: string
  version_id: string
  submitted_at: string
  is_late: boolean
  status: SubmissionStatus
  file_ids: string[]
}

export interface MReview {
  id: string
  submission_id: string
  reviewer_id: string
  grade: number | null
  comment: string
  return_for_resubmission: boolean
  created_at: string
}

export interface MFile {
  id: string
  owner_id: string
  name: string
  size: number
  mime: string
  sha256: string
  kind: FileKind
}

export interface MVersion {
  id: string
  n: number
  label: string | null
  kind: 'autosave' | 'manual' | 'submitted'
  size: number
  created_at: string
}

export interface MProject {
  id: string
  owner_id: string
  name: string
  module: string
  updated_at: string
  versions: MVersion[]
}

interface CoursesState {
  courses: MCourse[]
  memberships: MMembership[]
  labs: MLab[]
  teams: MTeam[]
  submissions: MSubmission[]
  reviews: MReview[]
  files: MFile[]
  projects: MProject[]
}

/** Correos de los usuarios demo de este módulo (todos con la contraseña `DEMO_PASSWORD`). */
export const DOCENTE_EMAIL = 'docente@unimagdalena.edu.co'
export const STUDENT_EMAIL = 'estudiante@unimagdalena.edu.co'

const EXTRA_USERS: Omit<MockUser, 'created_at'>[] = [
  {
    id: '0190d0c0-0000-7000-8000-000000000101',
    email: DOCENTE_EMAIL,
    full_name: 'Carlos Andrés Docente',
    password: DEMO_PASSWORD,
    role: 'user',
    email_verified: true,
    active: true,
  },
  {
    id: '0190d0c0-0000-7000-8000-000000000102',
    email: 'luis.perez@unimagdalena.edu.co',
    full_name: 'Luis Fernando Pérez',
    password: DEMO_PASSWORD,
    role: 'user',
    email_verified: true,
    active: true,
  },
  {
    id: '0190d0c0-0000-7000-8000-000000000103',
    email: 'sofia.rodriguez@unimagdalena.edu.co',
    full_name: 'Sofía Rodríguez',
    password: DEMO_PASSWORD,
    role: 'user',
    email_verified: true,
    active: true,
  },
  {
    id: '0190d0c0-0000-7000-8000-000000000104',
    email: 'juan.rojas@unimagdalena.edu.co',
    full_name: 'Juan Camilo Rojas',
    password: DEMO_PASSWORD,
    role: 'user',
    email_verified: true,
    active: true,
  },
  {
    id: '0190d0c0-0000-7000-8000-000000000105',
    email: 'marta.docente@unimagdalena.edu.co',
    full_name: 'Marta Lucía Docente',
    password: DEMO_PASSWORD,
    role: 'user',
    email_verified: true,
    active: true,
  },
]

/** Añade (si faltan) los usuarios demo de cursos al estado de `db.ts`. Idempotente. */
export function ensureCourseUsers(): void {
  for (const u of EXTRA_USERS) {
    if (!findUserByEmail(u.email)) db.users.push({ ...u, created_at: '2026-11-01T14:00:00.000Z' })
  }
}

export function userById(id: string): MockUser | undefined {
  return db.users.find((u) => u.id === id)
}

export function uid(email: string): string {
  ensureCourseUsers()
  const u = findUserByEmail(email)
  if (!u) throw new Error(`usuario mock inexistente: ${email}`)
  return u.id
}

let seq = 0
export function newId(prefix = 'f2'): string {
  seq++
  return `0190${prefix}00-0000-7000-8000-${String(seq).padStart(12, '0')}`
}

const DAY = 86_400_000
const iso = (ms: number) => new Date(ms).toISOString()

/** IDs estables del curso y labs de ejemplo (útiles en tests y para navegar en dev). */
export const IDS = {
  course: '0190c0c0-0000-7000-8000-000000000001',
  courseCircuitos: '0190c0c0-0000-7000-8000-000000000002',
  courseMicro: '0190c0c0-0000-7000-8000-000000000003',
  lab1: '0190c1c1-0000-7000-8000-000000000001',
  lab2: '0190c1c1-0000-7000-8000-000000000002',
  lab3: '0190c1c1-0000-7000-8000-000000000003',
  lab4: '0190c1c1-0000-7000-8000-000000000004',
  projSumador: '0190c2c2-0000-7000-8000-000000000001',
  projContador: '0190c2c2-0000-7000-8000-000000000002',
  projLuis: '0190c2c2-0000-7000-8000-000000000003',
  subAna1: '0190c3c3-0000-7000-8000-000000000001',
  subAna2: '0190c3c3-0000-7000-8000-000000000002',
  subLuis1: '0190c3c3-0000-7000-8000-000000000003',
  subSofia3: '0190c3c3-0000-7000-8000-000000000004',
  teamFF: '0190c4c4-0000-7000-8000-000000000001',
  teamCMP: '0190c4c4-0000-7000-8000-000000000002',
}

const STATEMENT_LAB1 = `# Objetivo

Diseñar y simular un **sumador completo de 1 bit** en VHDL y extenderlo a 4 bits.

## Procedimiento

1. Escribe la entidad \`full_adder\` con entradas \`a\`, \`b\`, \`cin\` y salidas \`s\`, \`cout\`.
2. Instancia cuatro sumadores para formar \`adder4\`.
3. Simula todas las combinaciones con un *testbench* y revisa las formas de onda.

## Entregables

- Proyecto con el diseño y el testbench.
- Informe en PDF con capturas de la simulación.
- Archivo \`.bit\` generado para la Basys 3.

> Consulta la [guía de VHDL](https://ghdl.github.io/ghdl/) si tienes dudas.
`

const STATEMENT_LAB2 = `# Contador BCD

Implementa un contador BCD de 0 a 9 que muestre el valor en el display de 7 segmentos de la Basys 3.

- Usa el reloj de 100 MHz con un divisor a 1 Hz.
- El botón central reinicia la cuenta.

\`\`\`vhdl
process (clk) begin
  if rising_edge(clk) then
    -- tu código aquí
  end if;
end process;
\`\`\`
`

function seedState(): CoursesState {
  seq = 0
  ensureCourseUsers()
  const now = Date.now()
  const ana = uid(STUDENT_EMAIL)
  const carlos = uid(DOCENTE_EMAIL)
  const luis = uid('luis.perez@unimagdalena.edu.co')
  const sofia = uid('sofia.rodriguez@unimagdalena.edu.co')
  const juan = uid('juan.rojas@unimagdalena.edu.co')
  const marta = uid('marta.docente@unimagdalena.edu.co')
  const created = iso(now - 30 * DAY)
  const numeric05: GradeScale = { type: 'numeric', min: 0, max: 5, decimals: 1, pass_mark: 3 }

  const courses: MCourse[] = [
    {
      id: IDS.course,
      name: 'Diseño de Sistemas Digitales 2027-1',
      period: '2027-1',
      description: 'Quinto semestre de Ingeniería Electrónica. Laboratorios con FPGA Basys 3.',
      owner_id: carlos,
      join_code: 'DSD27A',
      created_at: created,
      archived_at: null,
    },
    {
      id: IDS.courseCircuitos,
      name: 'Circuitos Digitales 2027-1',
      period: '2027-1',
      description: 'Cuarto semestre.',
      owner_id: marta,
      join_code: 'CIRC27',
      created_at: created,
      archived_at: null,
    },
    {
      id: IDS.courseMicro,
      name: 'Microprocesamiento I 2027-1',
      period: '2027-1',
      description: 'Sexto semestre.',
      owner_id: marta,
      join_code: 'MICRO1',
      created_at: created,
      archived_at: null,
    },
  ]

  const m = (course_id: string, user_id: string, status: MembershipStatus, daysAgo: number) => ({
    course_id,
    user_id,
    role: 'estudiante' as const,
    status,
    requested_at: iso(now - daysAgo * DAY),
  })
  const memberships: MMembership[] = [
    m(IDS.course, ana, 'active', 25),
    m(IDS.course, luis, 'active', 25),
    m(IDS.course, sofia, 'active', 24),
    m(IDS.course, juan, 'pending', 1),
    m(IDS.courseCircuitos, ana, 'pending', 2),
  ]

  const lab = (over: Partial<MLab> & Pick<MLab, 'id' | 'title'>): MLab => ({
    course_id: IDS.course,
    statement_md: '',
    module: 'fpga',
    published_at: iso(now - 20 * DAY),
    opens_at: null,
    due_at: null,
    deadline_policy: 'late_marked',
    team_mode: 'individual',
    max_team_size: null,
    grade_scale: numeric05,
    allow_resubmission: false,
    created_at: iso(now - 21 * DAY),
    ...over,
  })
  const lab1Due = now - 10 * DAY
  const labs: MLab[] = [
    lab({
      id: IDS.lab1,
      title: 'Lab 1 — Sumador completo en VHDL',
      statement_md: STATEMENT_LAB1,
      due_at: iso(lab1Due),
      deadline_policy: 'late_marked',
    }),
    lab({
      id: IDS.lab2,
      title: 'Lab 2 — Contador BCD con display de 7 segmentos',
      statement_md: STATEMENT_LAB2,
      due_at: iso(now + 14 * DAY),
      deadline_policy: 'strict',
      team_mode: 'team',
      max_team_size: 3,
      allow_resubmission: true,
    }),
    lab({
      id: IDS.lab3,
      title: 'Lab 3 — Máquina de estados (semáforo)',
      statement_md: 'Diseñe una máquina de Moore para un semáforo de dos vías.',
      due_at: iso(now - 3 * DAY),
      deadline_policy: 'strict',
    }),
    lab({
      id: IDS.lab4,
      title: 'Lab 4 — Transmisor UART',
      statement_md: 'Borrador: transmisor UART a 9600 baudios.',
      published_at: null,
      deadline_policy: 'none',
      grade_scale: { type: 'pass_fail' },
    }),
  ]

  const teams: MTeam[] = [
    {
      id: IDS.teamFF,
      lab_id: IDS.lab2,
      name: 'Los Flip-Flops',
      join_code: 'FF1234',
      locked: false,
      member_ids: [ana, luis],
    },
    {
      id: IDS.teamCMP,
      lab_id: IDS.lab2,
      name: 'Compuertas',
      join_code: 'CMP777',
      locked: false,
      member_ids: [sofia],
    },
  ]

  const v = (n: number, daysAgo: number, label: string | null = null): MVersion => ({
    id: newId('v0'),
    n,
    label,
    kind: label ? 'manual' : 'autosave',
    size: 4_096 + n * 512,
    created_at: iso(now - daysAgo * DAY),
  })
  const projects: MProject[] = [
    {
      id: IDS.projSumador,
      owner_id: ana,
      name: 'Sumador completo',
      module: 'fpga',
      updated_at: iso(now - 9 * DAY),
      versions: [v(1, 15), v(2, 12, 'Primera entrega'), v(3, 9, 'Con testbench')],
    },
    {
      id: IDS.projContador,
      owner_id: ana,
      name: 'Contador BCD',
      module: 'fpga',
      updated_at: iso(now - 1 * DAY),
      versions: [v(1, 4), v(2, 1)],
    },
    {
      id: IDS.projLuis,
      owner_id: luis,
      name: 'Sumador 4 bits',
      module: 'fpga',
      updated_at: iso(now - 11 * DAY),
      versions: [v(1, 11, 'Final')],
    },
  ]

  const file = (owner_id: string, name: string, kind: FileKind, size: number): MFile => ({
    id: newId('fi'),
    owner_id,
    name,
    kind,
    size,
    mime: name.endsWith('.pdf') ? 'application/pdf' : 'application/octet-stream',
    sha256: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  })
  const f1 = file(ana, 'informe-lab1.pdf', 'report', 482_113)
  const f2 = file(ana, 'adder4.bit', 'bitstream', 2_192_012)
  const f3 = file(ana, 'informe-lab1-v2.pdf', 'report', 512_400)
  const f4 = file(luis, 'informe-luis.pdf', 'report', 390_000)
  const f5 = file(sofia, 'semaforo.pdf', 'report', 401_000)

  const sumVersions = projects[0]!.versions
  const submissions: MSubmission[] = [
    {
      id: IDS.subAna1,
      lab_id: IDS.lab1,
      attempt: 1,
      student_id: ana,
      team_id: null,
      submitted_by: ana,
      project_id: IDS.projSumador,
      version_id: sumVersions[1]!.id,
      submitted_at: iso(lab1Due - 2 * DAY),
      is_late: false,
      status: 'returned',
      file_ids: [f1.id, f2.id],
    },
    {
      id: IDS.subAna2,
      lab_id: IDS.lab1,
      attempt: 2,
      student_id: ana,
      team_id: null,
      submitted_by: ana,
      project_id: IDS.projSumador,
      version_id: sumVersions[2]!.id,
      submitted_at: iso(lab1Due + 1 * DAY),
      is_late: true,
      status: 'submitted',
      file_ids: [f3.id, f2.id],
    },
    {
      id: IDS.subLuis1,
      lab_id: IDS.lab1,
      attempt: 1,
      student_id: luis,
      team_id: null,
      submitted_by: luis,
      project_id: IDS.projLuis,
      version_id: projects[2]!.versions[0]!.id,
      submitted_at: iso(lab1Due - 1 * DAY),
      is_late: false,
      status: 'graded',
      file_ids: [f4.id],
    },
    {
      id: IDS.subSofia3,
      lab_id: IDS.lab3,
      attempt: 1,
      student_id: sofia,
      team_id: null,
      submitted_by: sofia,
      project_id: IDS.projLuis,
      version_id: projects[2]!.versions[0]!.id,
      submitted_at: iso(now - 4 * DAY),
      is_late: false,
      status: 'graded',
      file_ids: [f5.id],
    },
  ]

  const reviews: MReview[] = [
    {
      id: newId('rv'),
      submission_id: IDS.subAna1,
      reviewer_id: carlos,
      grade: null,
      comment:
        'Falta el testbench que pruebe las 8 combinaciones. Agrégalo y vuelve a entregar, por favor.',
      return_for_resubmission: true,
      created_at: iso(lab1Due - 1 * DAY),
    },
    {
      id: newId('rv'),
      submission_id: IDS.subLuis1,
      reviewer_id: carlos,
      grade: 4.5,
      comment: 'Muy buen trabajo. El informe podría explicar mejor el acarreo.',
      return_for_resubmission: false,
      created_at: iso(lab1Due + 2 * DAY),
    },
    {
      id: newId('rv'),
      submission_id: IDS.subSofia3,
      reviewer_id: carlos,
      grade: 3.8,
      comment: 'Funciona. Revisa los estados no alcanzables.',
      return_for_resubmission: false,
      created_at: iso(now - 2 * DAY),
    },
  ]

  return {
    courses,
    memberships,
    labs,
    teams,
    submissions,
    reviews,
    files: [f1, f2, f3, f4, f5],
    projects,
  }
}

export let cdb: CoursesState = seedState()

/** Reinicia los datos de cursos (los tests lo llaman antes de cada caso, tras `resetDb`). */
export function resetCoursesDb(): void {
  cdb = seedState()
}
