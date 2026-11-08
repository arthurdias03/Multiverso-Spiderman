/**
 * Controle do serviço de reprodução em segundo plano.
 * O Zepp OS não oferece canal de mensagens página -> serviço; por isso cada comando
 * (tocar / próxima / anterior) reinicia o serviço com a fila e o índice desejados.
 * Pausar = parar o serviço guardando a posição (a faixa recomeça do início ao retomar;
 * o T-Rex 3 está no API_LEVEL 4.0 e o seek só existe a partir do 4.2).
 */
import * as appService from '@zos/app-service'
import { queryPermission, requestPermission } from '@zos/app'
import { QUEUE_FILE, NOW_FILE, SERVICE_FILE } from './constants'
import { readJSON, writeJSON } from './storage'

const PERM = ['device:os.bg_service']

export function isRunning() {
  try {
    return (appService.getAllAppServices() || []).indexOf(SERVICE_FILE) >= 0
  } catch (e) {
    return false
  }
}

function withPermission(cb) {
  const [status] = queryPermission({ permissions: PERM })
  if (status === 2) return cb(true)
  requestPermission({
    permissions: PERM,
    callback([result]) {
      cb(result === 2)
    },
  })
}

function startService(index, done) {
  appService.start({
    url: SERVICE_FILE,
    file: SERVICE_FILE,
    param: `index=${index}`,
    reload: false,
    complete_func: (info) => done && done(!!(info && info.result)),
  })
}

function stopService(done) {
  if (!isRunning()) return done && done()
  appService.stop({
    url: SERVICE_FILE,
    file: SERVICE_FILE,
    complete_func: () => done && done(),
  })
}

/** queue: [{ f, t, a }] ; index: posição inicial */
export function playQueue(queue, index, title, done) {
  writeJSON(QUEUE_FILE, { title, items: queue })
  writeJSON(NOW_FILE, { index, playing: true })
  withPermission((ok) => {
    if (!ok) return done && done(false, 'Permissão de serviço negada')
    stopService(() => startService(index, (res) => done && done(res)))
  })
}

export function currentState() {
  const q = readJSON(QUEUE_FILE, { title: '', items: [] })
  const now = readJSON(NOW_FILE, { index: 0, playing: false })
  now.playing = now.playing && isRunning()
  return { queue: q, now }
}

export function jump(delta, done) {
  const { queue, now } = currentState()
  const n = queue.items.length
  if (!n) return done && done(false)
  const index = (((now.index || 0) + delta) % n + n) % n
  writeJSON(NOW_FILE, { index, playing: true })
  stopService(() => startService(index, (res) => done && done(res)))
}

export function pause(done) {
  const { now } = currentState()
  writeJSON(NOW_FILE, { index: now.index || 0, playing: false })
  stopService(done)
}

export function resume(done) {
  jump(0, done)
}
