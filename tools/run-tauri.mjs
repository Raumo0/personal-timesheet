import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const DEVELOPMENT_CONFIG = 'src-tauri/tauri.dev.conf.json'

export function buildTauriArgs(args) {
  if (args[0] !== 'dev') {
    return args
  }

  return [...args, '--config', DEVELOPMENT_CONFIG]
}

function run() {
  const require = createRequire(import.meta.url)
  const tauriCli = require.resolve('@tauri-apps/cli/tauri.js')
  const result = spawnSync(
    process.execPath,
    [tauriCli, ...buildTauriArgs(process.argv.slice(2))],
    { stdio: 'inherit' },
  )

  if (result.error) {
    throw result.error
  }

  process.exitCode = result.status ?? 1
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  run()
}
