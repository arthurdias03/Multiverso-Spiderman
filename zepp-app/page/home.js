import { BasePage } from '@zeppos/zml/base-page'
import { push } from '@zos/router'
import { setPageBrightTime, resetPageBrightTime, pauseDropWristScreenOff, resetDropWristScreenOff } from '@zos/display'
import { showToast } from '@zos/interaction'
import { getDiskInfo } from '@zos/device'
import { px } from '@zos/utils'
import { COLOR, IMG } from '../lib/constants'
import { align, coverFor, renderList } from '../lib/ui'
import {
  loadLibrary, applyManifest, adoptFile, adoptLeftovers, playableTracks,
} from '../lib/storage'
import { currentState } from '../lib/player-control'
import { isValidId } from '../lib/validate'

// ---- layout da biblioteca (lista nativa, tela redonda 480x480) ----
const W = 432
const T = { HEAD: 1, SYNC: 2, NOW: 3, SECTION: 4, PL: 5, EMPTY: 6, FOOT: 7 }
const L = align.LEFT
const C = align.CENTER_H
const tv = (x, y, w, h, key, color, size, a = L) => ({ x: px(x), y: px(y), w: px(w), h: px(h), key, color, text_size: px(size), align_h: a })
const iv = (x, y, s, key) => ({ x: px(x), y: px(y), w: px(s), h: px(s), key })
const cfg = (type_id, h, bg, radius, texts, images = []) => ({
  type_id, item_height: px(h), item_bg_color: bg, item_bg_radius: px(radius),
  text_view: texts, text_view_count: texts.length, image_view: images, image_view_count: images.length,
})
const ITEM_CONFIG = [
  cfg(T.HEAD, 150, COLOR.bg, 0, [
    tv(0, 60, W, 46, 'title', COLOR.accent, 34, C),
    tv(30, 108, W - 60, 30, 'status', COLOR.sub, 20, C),
  ]),
  cfg(T.SYNC, 80, COLOR.card2, 40, [tv(84, 0, 320, 80, 'label', COLOR.text, 24)], [iv(12, 12, 56, 'icon')]),
  cfg(T.NOW, 96, COLOR.card2, 24, [
    tv(96, 14, 280, 26, 'label', COLOR.accent, 16),
    tv(96, 40, 280, 38, 'title', COLOR.text, 22),
  ], [iv(16, 16, 64, 'cover'), iv(386, 34, 28, 'eq')]),
  cfg(T.SECTION, 56, COLOR.bg, 0, [tv(28, 10, 380, 40, 'label', COLOR.text, 24)]),
  cfg(T.PL, 96, COLOR.card, 24, [
    tv(96, 16, 280, 36, 'name', COLOR.text, 24),
    tv(96, 52, 280, 28, 'sub', COLOR.sub, 18),
  ], [iv(16, 16, 64, 'cover'), iv(386, 34, 28, 'state')]),
  cfg(T.EMPTY, 100, COLOR.bg, 0, [tv(20, 0, W - 40, 100, 'label', COLOR.sub, 20, C)]),
  cfg(T.FOOT, 130, COLOR.bg, 0, [tv(0, 0, 10, 10, 'x', COLOR.bg, 10)]),
]
const LIST_BASE = {
  x: px(24), y: 0, w: px(W), h: px(480), item_space: px(10),
  item_config: ITEM_CONFIG, item_config_count: ITEM_CONFIG.length,
}

function mb(bytes) {
  return (bytes / 1048576).toFixed(0) + ' MB'
}

function fileId(file) {
  let params = file.params
  if (typeof params === 'string') {
    try {
      params = JSON.parse(params)
    } catch (e) {
      params = {}
    }
  }
  const id = params && params.id ? String(params.id) : String(file.fileName || '').replace(/\.mp3$/, '')
  return isValidId(id) ? id : null
}

Page(
  BasePage({
    state: {
      lib: null,
      list: null,
      items: [],
      status: 'Abra o app Zepp no celular',
      syncLabel: 'Sincronizar agora',
      syncing: false,
    },

    onInit() {
      this.state.lib = loadLibrary()
      const adopted = adoptLeftovers(this.state.lib)
      if (adopted) showToast({ content: `${adopted} música(s) recuperadas` })
    },

    build() {
      this.render()
      this.sync()
    },

    onResume() {
      this.render() // volta do player/playlist: atualiza "Tocando agora"
    },

    // ---------- interface ----------
    render() {
      const { lib } = this.state
      const items = [
        { type: T.HEAD, data: { title: 'spotifiBR', status: this.state.status } },
        { type: T.SYNC, data: { icon: IMG.sync, label: this.state.syncLabel }, onClick: () => this.sync() },
      ]
      const { queue, now } = currentState()
      const current = queue.items && queue.items[now.index || 0]
      if (current) {
        items.push({
          type: T.NOW,
          data: {
            cover: coverFor(queue.playlistId || queue.title, 64),
            label: now.playing ? 'TOCANDO AGORA' : 'PAUSADO',
            title: current.t,
            eq: now.playing ? IMG.eq : IMG.blank,
          },
          onClick: () => push({ url: 'page/player' }),
        })
      }
      items.push({ type: T.SECTION, data: { label: 'Suas playlists' } })
      if (!lib.playlists.length) {
        items.push({ type: T.EMPTY, data: { label: 'Nenhuma playlist ainda' } })
      }
      for (const pl of lib.playlists) {
        const have = playableTracks(lib, pl).length
        const total = pl.tracks.length
        items.push({
          type: T.PL,
          data: {
            cover: coverFor(pl.id, 64),
            name: pl.name,
            sub: have === total ? `${total} músicas` : `${have} de ${total} no relógio`,
            state: have === total ? IMG.ok : IMG.wait,
          },
          onClick: () => push({ url: 'page/playlist', params: JSON.stringify({ id: pl.id }) }),
        })
      }
      items.push({ type: T.FOOT, data: { x: '' } })
      this.state.items = items
      renderList(this.state, LIST_BASE, items, (index) => {
        const it = this.state.items[index]
        it && it.onClick && it.onClick()
      })
    },

    setStatus(status, syncLabel) {
      this.state.status = status
      if (syncLabel) this.state.syncLabel = syncLabel
      this.render()
    },

    keepAwake(on) {
      try {
        if (on) {
          setPageBrightTime({ brightTime: 30 * 60 * 1000 })
          pauseDropWristScreenOff({ duration: 0 })
        } else {
          resetPageBrightTime()
          resetDropWristScreenOff()
        }
      } catch (e) {}
    },

    // ---------- sincronização ----------
    sync() {
      if (this.state.syncing) return
      this.state.syncing = true
      this.setStatus('Conectando ao celular...', 'Sincronizando...')
      this.request({ method: 'manifest' }, { timeout: 30000 })
        .then((manifest) => {
          const { needed, removed } = applyManifest(this.state.lib, manifest)
          if (!needed.length) {
            this.state.syncing = false
            return this.setStatus(removed ? `Tudo em dia · ${removed} removida(s)` : 'Tudo em dia', 'Sincronizar agora')
          }
          const bytes = needed.reduce((s, i) => s + (i.s || 0), 0)
          let free = -1
          try {
            free = getDiskInfo().free
          } catch (e) {}
          if (free >= 0 && bytes > free - 50 * 1048576) {
            this.state.syncing = false
            return this.setStatus(`Sem espaço: precisa ${mb(bytes)}`, 'Sincronizar agora')
          }
          this.keepAwake(true)
          this.setStatus(`${needed.length} novas · ${mb(bytes)}`, 'Baixando...')
          return this.request({ method: 'download', params: { items: needed } }, { timeout: 30000 })
        })
        .catch((e) => {
          this.state.syncing = false
          this.keepAwake(false)
          const msg = (e && (e.message || e.code)) || 'sem conexão com o app Zepp'
          this.setStatus(`Falha: ${msg}`, 'Tentar de novo')
        })
    },

    onCall(req) {
      if (!req || req.method !== 'sync.progress') return
      const p = req.params || {}
      if (p.finished) {
        this.state.syncing = false
        this.keepAwake(false)
        return this.setStatus(p.error ? `Falha: ${p.error}` : 'Sincronização concluída', 'Sincronizar agora')
      }
      const n = `${Math.min(p.done + 1, p.total)} de ${p.total}`
      if (p.error) return this.setStatus(`${n} · erro: ${p.error}`)
      const stage = p.stage === 'ok' ? 'ok' : `${p.stage || ''}${p.pct != null ? ' ' + p.pct + '%' : ''}`
      this.setStatus(`${n} · ${stage}`, 'Baixando...')
    },

    onReceivedFile(file) {
      const id = fileId(file)
      file.on('change', (event) => {
        const st = event && event.data && event.data.readyState
        if (st === 'transferred') {
          // arquivo inesperado (id inválido, fora do manifesto ou tamanho errado) é descartado
          const ok = id && adoptFile(this.state.lib, id, file.filePath || `download/${file.fileName}`)
          if (!ok) showToast({ content: 'Arquivo inesperado descartado' })
          this.render()
        }
      })
    },

    onDestroy() {
      this.keepAwake(false)
    },
  }),
)
