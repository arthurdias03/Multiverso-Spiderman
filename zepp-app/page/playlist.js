import { push } from '@zos/router'
import { showToast } from '@zos/interaction'
import { COLOR } from '../lib/constants'
import { title, label, button } from '../lib/ui'
import { loadLibrary, isDownloaded } from '../lib/storage'
import { playQueue } from '../lib/player-control'

const MAX_ROWS = 150 // limite de widgets por página (memória do relógio)

function shuffle(arr) {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

Page({
  state: { pl: null, lib: null },

  onInit(params) {
    let id = ''
    try {
      id = JSON.parse(params || '{}').id
    } catch (e) {}
    this.state.lib = loadLibrary()
    this.state.pl = this.state.lib.playlists.find((p) => p.id === id) || null
  },

  queueFrom(ids) {
    const { lib } = this.state
    return ids
      .filter((id) => isDownloaded(lib, id))
      .map((id) => ({ f: lib.tracks[id].f, t: lib.tracks[id].t, a: lib.tracks[id].a }))
  },

  play(ids, index) {
    const queue = this.queueFrom(ids)
    if (!queue.length) return showToast({ content: 'Nenhuma música baixada ainda' })
    playQueue(queue, index, this.state.pl.name, (ok, msg) => {
      if (!ok) return showToast({ content: msg || 'Não foi possível tocar' })
      push({ url: 'page/player' })
    })
  },

  build() {
    const { pl, lib } = this.state
    if (!pl) {
      title('Playlist')
      label('Playlist não encontrada', 200)
      return
    }
    title(pl.name)
    const downloaded = pl.tracks.filter((id) => isDownloaded(lib, id))
    label(`${downloaded.length} de ${pl.tracks.length} no relógio`, 84, 40, { size: 22 })

    button('Tocar', 136, () => this.play(pl.tracks, 0), {
      x: 70, w: 165, color: COLOR.accent, pressColor: COLOR.accentPressed, textColor: 0x000000,
    })
    button('Aleatório', 136, () => this.play(shuffle(downloaded), 0), { x: 245, w: 165 })

    let y = 224
    const rows = pl.tracks.slice(0, MAX_ROWS)
    rows.forEach((id) => {
      const t = lib.tracks[id] || { t: id, a: '' }
      const ok = isDownloaded(lib, id)
      const text = `${t.t}${t.a ? ' · ' + t.a : ''}`
      button(text, y, () => {
        if (!ok) return showToast({ content: 'Ainda não baixada' })
        const playable = downloaded
        this.play(playable, playable.indexOf(id))
      }, { size: 22, h: 64, textColor: ok ? COLOR.text : COLOR.muted, radius: 16 })
      y += 72
    })
    if (pl.tracks.length > MAX_ROWS) {
      label(`+${pl.tracks.length - MAX_ROWS} músicas (use Tocar/Aleatório)`, y, 50, { size: 20 })
      y += 50
    }
    label('', y + 20, 60)
  },
})
