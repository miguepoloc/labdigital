/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" activa los mocks de MSW en el navegador (desarrollo). */
  readonly VITE_API_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
