import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { buildTauriArgs } from './run-tauri.mjs'

function applyJsonMergePatch(target, patch) {
  if (patch === null || typeof patch !== 'object' || Array.isArray(patch)) {
    return structuredClone(patch)
  }

  const result =
    target !== null && typeof target === 'object' && !Array.isArray(target)
      ? structuredClone(target)
      : {}

  for (const [key, value] of Object.entries(patch)) {
    if (value === null) {
      delete result[key]
    } else {
      result[key] = applyJsonMergePatch(result[key], value)
    }
  }

  return result
}

async function readJson(relativePath) {
  return JSON.parse(await readFile(new URL(relativePath, import.meta.url), 'utf8'))
}

test('adds the development overlay to the dev subcommand', () => {
  assert.deepEqual(buildTauriArgs(['dev', '--no-watch']), [
    'dev',
    '--no-watch',
    '--config',
    'src-tauri/tauri.dev.conf.json',
  ])
})

test('preserves non-development Tauri commands', () => {
  assert.deepEqual(buildTauriArgs(['build', '--debug']), ['build', '--debug'])
})

test('development merge changes only the approved identity fields', async () => {
  const base = await readJson('../src-tauri/tauri.conf.json')
  const overlay = await readJson('../src-tauri/tauri.dev.conf.json')
  const expected = structuredClone(base)
  expected.productName = 'Personal Timesheet Dev'
  expected.identifier = 'com.personal.timesheet.dev'
  expected.app.windows[0].title = 'Personal Timesheet Dev'

  assert.deepEqual(applyJsonMergePatch(base, overlay), expected)
})
