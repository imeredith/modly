// Keep Electron's large download off the system temporary filesystem, which
// may have a small per-user quota even when the project disk has free space.
import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'

const require = createRequire(import.meta.url)
let temporaryDirectory

try {
  const installer = require.resolve('electron/install.js')
  temporaryDirectory = mkdtempSync(join(dirname(installer), '.download-'))
  const result = spawnSync(process.execPath, [installer], {
    stdio: 'inherit',
    env: {
      ...process.env,
      TMPDIR: temporaryDirectory,
      TMP: temporaryDirectory,
      TEMP: temporaryDirectory
    }
  })
  if (result.error) throw result.error
  process.exitCode = result.status ?? 1
} catch (error) {
  console.error('[Electron] Runtime installation failed:', error.message)
  process.exitCode = 1
} finally {
  if (temporaryDirectory) rmSync(temporaryDirectory, { recursive: true, force: true })
}
