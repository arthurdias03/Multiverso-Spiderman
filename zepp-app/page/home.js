import { BasePage } from '@zeppos/zml/base-page'
import { push } from '@zos/router'
import { setPageBrightTime, resetPageBrightTime, pauseDropWristScreenOff, resetDropWristScreenOff } from '@zos/display'
import { showToast } from '@zos/interaction'
import { getDiskInfo } from '@zos/device'
import { COLOR } from '../lib/constants'
import { title, label, button, setText, remove } from '../lib/ui'
import {
  loadLibrary, applyManifest, adoptFile, adoptLeftovers, playableTracks,
} from '../lib/storage'
import { currentState } from '../lib/player-control'

const LIST_Y = 250

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
  if (params && params.id) return params.id
  return String(file.fileName || '').replace(/\.mp3$/, '')
}

Page(
  BasePage({
    state: {
      lib: null,
      items: [],
      status: null,
      syncing: false,
      pending: 0,
    },

    onInit() {
      this.state.lib = loadLibrary()
      const adopted = adoptLeftovers(this.state.lib)
      if (adopted) showToast({ content: `${adopted} música(s) recuperadas` })
    },

    build() {
      title('T-Rex Music')
      this.state.status = label('', 84, 70, { wrap: true, size: 22 })
      button('Sincronizar', 160, () => this.sync(), {
        color: COLOR.accent, pressColor: COLOR.accentPressed, textColor: 0x000000,
      })
      this.renderPlaylists()
      this.sync()
    },

    renderPlaylists() {
      remove(this.state.items)
      const { lib } = this.state
      let y = LIST_Y
      const { queue } = currentState()
      if (queue.items && queue.items.length) {
        this.state.items.push(button('Tocando agora', y, () => push({ url: 'page/player' }), { size: 24 }))
        y += 84
      }
      if (!lib.playlists.length) {
        this.state.items.push(label('Nenhuma playlist ainda.\nToque em Sincronizar.', y, 80, { wrap: true }))
        return
      }
      for (const pl of lib.playlists) {
        const have = playableTracks(lib, pl).length
        const text = `${pl.name}  ${have}/${pl.tracks.length}`
        const w = button(text, y, () => push({ url: 'page/playlist', params: JSON.stringify({ id: pl.id }) }))
        w._plId = pl.id
        this.state.items.push(w)
        y += 80
      }
      this.state.items.push(label('', y + 20, 60)) // respiro no fim da rolagem
    },

    refreshCounts() {
      const { lib } = this.state
      for (const w of this.state.items) {
        if (!w._plId) continue
        const pl = lib.playlists.find((p) => p.id === w._plId)
        if (pl) setText(w, `${pl.name}  ${playableTracks(lib, pl).length}/${pl.tracks.length}`)
      }
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

    sync() {
      if (this.state.syncing) return
      this.state.syncing = true
      setText(this.state.status, 'Conectando ao celular...')
      this.request({ method: 'manifest' }, { timeout: 30000 })
        .then((manifest) => {
          const before = this.state.lib.playlists.map((p) => p.id).join(',')
          const { needed, removed } = applyManifest(this.state.lib, manifest)
          const after = this.state.lib.playlists.map((p) => p.id).join(',')
          if (before !== after) this.renderPlaylists()
          else this.refreshCounts()

          if (!needed.length) {
            this.state.syncing = false
            setText(this.state.status, removed ? `Tudo em dia. ${removed} removida(s).` : 'Tudo em dia.')
            return
          }
          const bytes = needed.reduce((s, i) => s + (i.s || 0), 0)
          let free = -1
          try {
            free = getDiskInfo().free
          } catch (e) {}
          if (free >= 0 && bytes > free - 50 * 1048576) {
            this.state.syncing = false
            setText(this.state.status, `Sem espaço: precisa ${mb(bytes)}, livre ${mb(free)}`)
            return
          }
          this.state.pending = needed.length
          this.keepAwake(true)
          setText(this.state.status, `Baixando ${needed.length} música(s) (${mb(bytes)})\nMantenha o app aberto`)
          return this.request({ method: 'download', params: { items: needed } }, { timeout: 30000 })
        })
        .catch((e) => {
          this.state.syncing = false
          this.keepAwake(false)
          const msg = (e && (e.message || e.code)) || 'sem conexão com o app Zepp'
          setText(this.state.status, `Falha: ${msg}`)
        })
    },

    onCall(req) {
      if (!req || req.method !== 'sync.progress') return
      const p = req.params || {}
      if (p.finished) {
        this.state.syncing = false
        this.keepAwake(false)
        this.refreshCounts()
        setText(this.state.status, 'Sincronização concluída.')
        return
      }
      if (p.error) {
        setText(this.state.status, `${p.done}/${p.total}  erro: ${p.error}`)
        return
      }
      const t = this.state.lib.tracks[p.id]
      const name = t ? t.t : ''
      const stage = p.stage === 'ok' ? 'ok' : `${p.stage || ''} ${p.pct != null ? p.pct + '%' : ''}`
      setText(this.state.status, `${Math.min(p.done + 1, p.total)}/${p.total} ${name}\n${stage}`)
    },

    onReceivedFile(file) {
      const id = fileId(file)
      file.on('change', (event) => {
        const st = event && event.data && event.data.readyState
        if (st === 'transferred') {
          adoptFile(this.state.lib, id, file.filePath || `download/${file.fileName}`)
          this.refreshCounts()
        }
      })
    },

    onDestroy() {
      this.keepAwake(false)
    },
  }),
)
