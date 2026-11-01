import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

for (const status of [0, 17]) {
  test(`Electron installer uses project temporary storage and cleans up on exit ${status}`, () => {
    const root = mkdtempSync(join(tmpdir(), 'modly-electron-test-'))
    try {
      mkdirSync(join(root, 'scripts'))
      const electron = join(root, 'node_modules', 'electron')
      mkdirSync(electron, { recursive: true })
      copyFileSync(new URL('./ensure-electron.mjs', import.meta.url), join(root, 'scripts', 'ensure-electron.mjs'))
      writeFileSync(join(electron, 'install.js'), `
        const assert = require('node:assert/strict');
        const fs = require('node:fs');
        const os = require('node:os');
        const path = require('node:path');
        const temporaryDirectory = os.tmpdir();
        assert.equal(path.dirname(temporaryDirectory), __dirname);
        assert.equal(process.env.TMP, temporaryDirectory);
        assert.equal(process.env.TEMP, temporaryDirectory);
        fs.writeFileSync(path.join(temporaryDirectory, 'partial-download'), 'test');
        fs.writeFileSync(path.join(__dirname, '../../observed-temp'), temporaryDirectory);
        process.exit(${status});
      `)
      const result = spawnSync(process.execPath, [join(root, 'scripts', 'ensure-electron.mjs')], {
        encoding: 'utf8',
        env: { ...process.env, TMPDIR: join(root, 'unusable-system-temp') }
      })
      assert.equal(result.status, status, result.stderr)
      const temporaryDirectory = readFileSync(join(root, 'observed-temp'), 'utf8')
      assert.equal(existsSync(temporaryDirectory), false, 'partial downloads must be removed')
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })
}
