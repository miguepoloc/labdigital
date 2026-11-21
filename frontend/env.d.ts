/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" activa los mocks de MSW en el navegador (desarrollo). */
  readonly VITE_API_MOCK?: string
  /** Sólo desarrollo: URL del módulo FPGA en el iframe (p. ej. `/labdigital/dev-fpga-stub.html`). */
  readonly VITE_FPGA_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
