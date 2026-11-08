// Roda a lógica de lib/storage.js no Node com um @zos/fs simulado em memória.
import { mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const out = join(here, '.build')
mkdirSync(out, { recursive: true })
writeFileSync(join(out, 'storage.mjs'), readFileSync(join(here, '../lib/storage.js'), 'utf8')
  .replace("'@zos/fs'", "'../fsmock.mjs'").replace("'./constants'", "'./constants.mjs'").replace("'./validate'", "'./validate.js'"))
copyFileSync(join(here, '../lib/constants.js'), join(out, 'constants.mjs'))
copyFileSync(join(here, '../lib/validate.js'), join(out, 'validate.js'))
await import('./storage.test.mjs')
await import('./validate.test.mjs')
