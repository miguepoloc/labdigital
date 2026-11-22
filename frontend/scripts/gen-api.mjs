// Genera src/api/schema.gen.ts a partir del OpenAPI del backend.
// Uso: OPENAPI_URL=https://…/labdigital/api/openapi.json npm run gen:api
// Cuando exista, los tipos escritos a mano de src/api/types.ts deberán derivarse de este archivo.
import { spawnSync } from 'node:child_process'

const url = process.env.OPENAPI_URL ?? 'http://127.0.0.1:8088/labdigital/api/openapi.json'
const out = 'src/api/schema.gen.ts'
console.log(`gen:api: ${url} -> ${out}`)
const res = spawnSync('npx', ['openapi-typescript', url, '-o', out], {
  stdio: 'inherit',
  shell: process.platform === 'win32',
})
process.exit(res.status ?? 1)
