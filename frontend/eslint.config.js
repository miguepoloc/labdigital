import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue,js}'],
  },
  globalIgnores([
    '**/dist/**',
    '**/coverage/**',
    'public/mockServiceWorker.js',
    'src/api/schema.gen.ts',
  ]),
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  {
    name: 'app/rules',
    rules: {
      // Con props tipadas en TS, `undefined` ya es el valor por defecto de las opcionales.
      'vue/require-default-prop': 'off',
    },
  },
  skipFormatting,
)
