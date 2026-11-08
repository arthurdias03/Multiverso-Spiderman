/**
 * Serviço em segundo plano que toca a fila (continua após sair do app / tela apagada).
 * Restrições do App Service: sem timers, sem UI, e escrita em arquivo só com a tela apagada.
 */
import { create, id } from '@zos/media'
import * as appServiceMgr from '@zos/app-service'
import { readFileSync, writeFileSync } from '@zos/fs'
import { log } from '@zos/utils'

const logger = log.getLogger('trex-music-service')
const QUEUE_FILE = 'queue.json'
const NOW_FILE = 'now.json'

let player = null
let items = []
let index = 0
let failures = 0

function readJSON(path, fallback) {
  try {
    const s = readFileSync({ path, options: { encoding: 'utf8' } })
    return s ? JSON.parse(s) : fallback
  } catch (e) {
    return fallback
  }
}

function saveNow(playing) {
  try {
    // só funciona com a tela apagada (restrição do sistema); com a tela ligada a página já sabe o índice
    writeFileSync({ path: NOW_FILE, data: JSON.stringify({ index, playing }), options: { encoding: 'utf8' } })
  } catch (e) {}
}

function parseIndex(param) {
  const m = /index=(\d+)/.exec(String(param || ''))
  return m ? parseInt(m[1], 10) : 0
}

function playCurrent() {
  if (!items.length) return finish()
  const item = items[index]
  saveNow(true)
  try {
    player.stop()
  } catch (e) {}
  player.setSource(player.source.FILE, { file: 'data://' + item.f })
  player.prepare()
}

function next() {
  index = (index + 1) % items.length
  playCurrent()
}

function finish() {
  saveNow(false)
  try {
    player && player.stop()
  } catch (e) {}
  appServiceMgr.exit()
}

AppService({
  onInit(param) {
    const q = readJSON(QUEUE_FILE, { items: [] })
    items = q.items || []
    index = Math.min(parseIndex(param), Math.max(items.length - 1, 0))
    logger.log(`start: ${items.length} faixas, índice ${index}`)

    player = create(id.PLAYER)
    player.addEventListener(player.event.PREPARE, (ok) => {
      if (ok) {
        failures = 0
        player.start()
      } else {
        logger.log('falha ao preparar ' + (items[index] && items[index].f))
        failures++
        if (failures >= items.length) return finish() // nenhuma faixa tocável
        next()
      }
    })
    player.addEventListener(player.event.COMPLETE, () => next())
    playCurrent()
  },
  onEvent(e) {
    if (String(e).indexOf('action=exit') >= 0) finish()
  },
  onDestroy() {
    try {
      player && player.stop()
    } catch (e) {}
  },
})
