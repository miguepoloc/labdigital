/** Configuración estática del frontend. Todo lo que dependa del despliegue debería vivir aquí. */
export const config = {
  /** Prefijo público de la plataforma (coincide con `base` de Vite). */
  basePath: '/labdigital/',
  /** Prefijo de la API v1 (contrato §1). */
  apiBase: '/labdigital/api/v1',
  /** Ruta privada por defecto tras iniciar sesión. */
  defaultAfterLogin: '/labdigital/app',
  /**
   * Manual de protección de datos personales de Unimagdalena (Acuerdo Superior N.º 17 de 2018,
   * Ley 1581 de 2012).
   */
  dataPolicyUrl: 'https://www.unimagdalena.edu.co/Content/Public/Docs/ManualProteccionDeDatos.pdf',
  /** Escudo oficial del CDN institucional. */
  escudo: {
    light: 'https://cdn.unimagdalena.edu.co/images/escudo/bg_light/128.png',
    dark: 'https://cdn.unimagdalena.edu.co/images/escudo/bg_dark/128.png',
  },
  /** Longitud mínima de contraseña (plan: mínimo 10 caracteres). */
  passwordMinLength: 10,
} as const
