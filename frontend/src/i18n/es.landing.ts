/**
 * Textos de la landing pública (LD-12). Diseño aprobado: /labdigital/preview/ (artifact "Design").
 * Parten de los textos del diseño, adaptados al trato de tú del resto de la plataforma.
 */
export const landing = {
  meta: {
    description:
      'Laboratorios de la línea digital de Ingeniería Electrónica de la Universidad del Magdalena: simula, sintetiza y entrega tus prácticas desde el navegador.',
  },
  top: {
    tagline: 'GIDEAM · Ingeniería Electrónica',
    escudoAlt: 'Universidad del Magdalena',
    nav: {
      modules: 'Módulos',
      teachers: 'Docentes',
      agent: 'Agente',
      team: 'Equipo',
    },
    login: 'Entrar',
    app: 'Ir a mis laboratorios',
  },
  hero: {
    eyebrow: 'Laboratorios de la línea digital',
    titleBefore: 'Del primer ',
    titleEm: 'AND',
    titleAfter: ' al bitstream, en el navegador.',
    subBefore: 'Escribe VHDL o dibuja el circuito, simúlalo sobre una Basys 3 virtual, genera el ',
    subCode: '.bit',
    subAfter: ' y entrega la práctica a tu docente. Sin instalar Vivado.',
    ctaRegister: 'Crear cuenta gratis',
    ctaMore: 'Ver qué incluye',
    noteBefore: 'Basys 3 · Artix-7 ',
    noteCode: 'XC7A35T',
    noteAfter: ' · reloj de 100 MHz · 16 switches, 16 LEDs, 4 displays de 7 segmentos',
  },
  modules: {
    eyebrow: 'Una sola cuenta para toda la línea',
    title: 'Acompaña la ruta digital del programa',
    lead: 'Los mismos proyectos y la misma cuenta desde las compuertas hasta los microcontroladores, siguiendo el plan de estudios de Ingeniería Electrónica.',
    steps: [
      {
        sem: '4.º semestre',
        title: 'Circuitos Digitales',
        body: 'Compuertas, tablas de verdad y mapas de Karnaugh en un editor de circuitos al estilo de Logisim, conectado a la placa simulada.',
        tag: 'Disponible en el módulo FPGA',
        live: true,
        current: false,
      },
      {
        sem: '5.º semestre',
        title: 'Diseño de Sistemas Digitales',
        body: 'VHDL con GHDL, testbench, formas de onda y síntesis open source (Yosys, nextpnr, Project X-Ray) hasta el bitstream de la Basys 3.',
        tag: 'Disponible · JG FPGA',
        live: true,
        current: true,
      },
      {
        sem: '6.º semestre',
        title: 'Microprocesamiento I',
        body: 'Programación de microcontroladores Arduino y ESP32 con el mismo flujo de proyectos, cursos y entregas.',
        tag: 'Próximamente',
        live: false,
        current: false,
      },
    ],
  },
  features: {
    eyebrow: 'Módulo FPGA',
    title: 'Todo el laboratorio en una pestaña',
    items: [
      {
        icon: 'code',
        title: 'Editor VHDL',
        body: 'Resaltado, errores de GHDL en la línea exacta y proyectos con varios archivos y constraints XDC.',
      },
      {
        icon: 'board',
        title: 'Placa simulada',
        body: 'Switches, botones, LEDs y displays de la Basys 3 responden a tu diseño en tiempo real.',
      },
      {
        icon: 'wave',
        title: 'Formas de onda',
        body: 'Visor de señales del testbench con cursores y búsqueda de flancos, en fs, ps y ns.',
      },
      {
        icon: 'chip',
        title: 'Síntesis al bitstream',
        body: 'Genera el .bit en el servidor con herramientas libres y grábalo en la placa real.',
      },
      {
        icon: 'bulb',
        title: 'Asistente con IA',
        body: 'Explica errores y propone cambios con tu propia clave gratuita de Gemini, que se queda en tu navegador.',
      },
      {
        icon: 'doc',
        title: 'Informe de laboratorio',
        body: 'Arma el informe con capturas de la placa y las ondas, en formato APA 7 o IEEE, listo en PDF o Word.',
      },
    ],
  },
  teachers: {
    eyebrow: 'Para docentes',
    title: 'Crea el curso, publica el laboratorio y revisa desde el simulador',
    lead: 'Cualquier persona con cuenta puede abrir un curso. Tú decides quién entra, cómo se califica y qué pasa con las entregas tardías.',
    flow: [
      {
        title: 'Abre un curso',
        body: 'Comparte el código con tus estudiantes y aprueba cada solicitud de ingreso.',
      },
      {
        title: 'Publica laboratorios',
        body: 'Enunciado, fecha límite (cierre, tardía marcada o sin fecha), trabajo individual o en equipo y su propia escala de nota.',
      },
      {
        title: 'Revisa cada entrega',
        body: 'Abre el proyecto congelado en el simulador, lee el informe, descarga el .bit, comenta y califica.',
      },
      {
        title: 'Permite correcciones',
        body: 'Devuelve la entrega con comentarios; el estudiante reentrega y queda el historial de intentos.',
      },
    ],
    grades: {
      label: 'Ejemplo de tabla de entregas',
      title: 'Lab 3 · Contador BCD con display',
      scale: 'Escala 0,0–5,0 · tardía marcada',
      cols: {
        who: 'Estudiante / equipo',
        when: 'Entrega',
        status: 'Estado',
        grade: 'Nota',
      },
      rows: [
        {
          who: 'Equipo 1 (2)',
          when: '12 feb., 9:14 p. m.',
          status: 'ok',
          label: 'Calificado',
          grade: '4,6',
        },
        {
          who: 'Equipo 2 (2)',
          when: '13 feb., 7:02 a. m.',
          status: 'late',
          label: 'Tardía',
          grade: '3,9',
        },
        {
          who: 'Equipo 3 (3)',
          when: '12 feb., 6:40 p. m.',
          status: 'ret',
          label: 'Devuelto',
          grade: '—',
        },
      ],
      example: 'Datos de ejemplo.',
    },
  },
  agent: {
    eyebrow: 'Placa real',
    title: 'Programa tu Basys 3 con un clic',
    lead: 'La web no puede usar el USB de tu computador. El agente JG FPGA se ejecuta en tu PC, se empareja con la web mediante un código y graba el bitstream en la placa.',
    windows: 'Agente para Windows',
    mac: 'Agente para macOS',
    notes: {
      versionBefore:
        'Versión 1.1.0. En Windows incluye Digilent Adept; en macOS usa openFPGALoader.',
      localBefore: 'Escucha solo en tu propio equipo (',
      localCode: '127.0.0.1',
      localAfter: ') y atiende únicamente a la web emparejada.',
      noAgentBefore: '¿Sin agente? Descarga el ',
      noAgentCode: '.bit',
      noAgentAfter: ' y grábalo con Adept, Vivado u openFPGALoader.',
    },
  },
  team: {
    eyebrow: 'Equipo',
    title: 'Un proyecto del grupo de investigación GIDEAM',
    lead: 'Grupo de Investigación en Desarrollo Electrónico y Aplicaciones Móviles, adscrito al programa de Ingeniería Electrónica de la Facultad de Ingeniería de la Universidad del Magdalena, en Santa Marta.',
    body: 'LabDigital y el módulo JG FPGA se desarrollan con docentes, estudiantes y semilleros del grupo.',
    link: 'Conoce GIDEAM',
    creditsTitle: 'Créditos',
    credits: [
      {
        name: 'José Granados',
        role: 'Autor de JG FPGA, el simulador y la síntesis VHDL para la Basys 3.',
      },
      {
        name: 'Miguel Polo',
        role: 'Autor de LabDigital, la plataforma de cursos, laboratorios y entregas.',
      },
    ],
    creditsAffiliation: 'GIDEAM · Ingeniería Electrónica, Universidad del Magdalena.',
    facts: [
      { value: '2007', label: 'Adscrito a Ingeniería Electrónica' },
      { value: '5+', label: 'Líneas de investigación' },
      { value: 'Minciencias', label: 'Grupo categorizado' },
      { value: 'Caribe', label: 'Impacto regional aplicado' },
    ],
  },
  final: {
    title: 'Tu próximo laboratorio empieza con una cuenta.',
    register: 'Crear cuenta',
    login: 'Ya tengo cuenta',
  },
  footer: {
    line1:
      'LabDigital GIDEAM · Ingeniería Electrónica, Universidad del Magdalena · Santa Marta, Colombia.',
    line2Before: 'Al crear una cuenta aceptas la ',
    line2Link: 'política de protección de datos personales',
    line2After: ' de la Universidad del Magdalena (Ley 1581 de 2012).',
    designSystem: 'Design system',
  },
  /** Usado también por AuthLayout. */
  footerPolicy: 'Política de protección de datos',
}
