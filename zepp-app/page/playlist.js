import { push } from '@zos/router'
import { showToast } from '@zos/interaction'
import { px } from '@zos/utils'
import { COLOR, IMG } from '../lib/constants'
import { align, coverFor, renderList, text } from '../lib/ui'
import { loadLibrary, isDownloaded } from '../lib/storage'
import { playQueue, currentState } from '../lib/player-control'

const MAX_ROWS = 1000 // a lista nativa recicla itens; 1000 linhas cabem com folga
const W = 432
const T = { HEAD: 1, ACTIONS: 2, OK: 3, PEND: 4, PLAYING: 5, MORE: 6, FOOT: 7 }
const L = align.LEFT
const C = align.CENTER_H
const tv = (x, y, w, h, key, color, size, a = L) => ({ x: px(x), y: px(y), w: px(w), h: px(h), key, color, text_size: px(size), align_h: a })
const iv = (x, y, s, key, action = false) => ({ x: px(x), y: px(y), w: px(s), h: px(s), key, action })
const cfg = (type_id, h, bg, radius, texts, images = []) => ({
  type_id, item_height: px(h), item_bg_color: bg, item_bg_radius: px(radius),
  text_view: texts, text_view_count: texts.length, image_view: images, image_view_count: images.length,
})
const track = (type, titleColor, artistColor) => cfg(type, 84, COLOR.card, 20, [
  tv(60, 10, 340, 36, 'title', titleColor, 22),
  tv(60, 46, 340, 28, 'artist', artistColor, 18),
], [iv(18, 28, 28, 'icon')])

const ITEM_CONFIG = [
  cfg(T.HEAD, 290, COLOR.bg, 0, [
    tv(10, 196, W - 20, 42, 'name', COLOR.text, 30, C),
    tv(20, 240, W - 40, 30, 'sub', COLOR.sub, 18, C),
  ], [iv((W - 140) / 2, 46, 140, 'cover')]),
  cfg(T.ACTIONS, 116, COLOR.bg, 0, [tv(0, 0, 10, 10, 'x', COLOR.bg, 10)], [
    iv(120, 22, 72, 'shuffle', true),
    iv(216, 10, 96, 'play', true),
  ]),
  track(T.OK, COLOR.text, COLOR.sub),
  track(T.PEND, COLOR.dim, COLOR.dim2),
  track(T.PLAYING, COLOR.accent, COLOR.sub),
  cfg(T.MORE, 70, COLOR.bg, 0, [tv(10, 0, W - 20, 70, 'label', COLOR.sub, 18, C)]),
  cfg(T.FOOT, 130, COLOR.bg, 0, [tv(0, 0, 10, 10, 'x', COLOR.bg, 10)]),
]

function shuffle(arr) {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

Page({
  state: { pl: null, lib: null, list: null, items: [] },

  onInit(params) {
    let id = ''
    try {
      id = JSON.parse(params || '{}').id
    } catch (e) {}
    this.state.lib = loadLibrary()
    this.state.pl = this.state.lib.playlists.find((p) => p.id === id) || null
  },

  play(ids, index, isShuffle) {
    const { lib, pl } = this.state
    const queue = ids
      .filter((id) => isDownloaded(lib, id))
      .map((id) => ({ f: lib.tracks[id].f, t: lib.tracks[id].t, a: lib.tracks[id].a }))
    if (!queue.length) return showToast({ content: 'Nenhuma música baixada ainda' })
    playQueue(queue, Math.max(0, index), { title: pl.name, playlistId: pl.id, shuffle: !!isShuffle }, (ok, msg) => {
      if (!ok) return showToast({ content: msg || 'Não foi possível tocar' })
      push({ url: 'page/player' })
    })
  },

  build() {
    const { pl } = this.state
    if (!pl) {
      text({ x: 40, y: 200, w: 400, h: 80, text: 'Playlist não encontrada', color: COLOR.sub })
      return
    }
    this.render()
  },

  onResume() {
    if (this.state.pl) this.render() // atualiza a faixa em destaque
  },

  render() {
    const { pl, lib } = this.state
    const downloaded = pl.tracks.filter((id) => isDownloaded(lib, id))
    const { queue, now } = currentState()
    const playingFile = queue.playlistId === pl.id && queue.items[now.index || 0] ? queue.items[now.index || 0].f : null

    const items = [
      {
        type: T.HEAD,
        data: {
          cover: coverFor(pl.id, 140),
          name: pl.name,
          sub: downloaded.length === pl.tracks.length
            ? `${pl.tracks.length} músicas no relógio`
            : `${downloaded.length} de ${pl.tracks.length} no relógio`,
        },
      },
      {
        type: T.ACTIONS,
        data: { x: '', shuffle: IMG.shuffle, play: IMG.play },
        onClick: (key) => {
          if (key === 'shuffle') this.play(shuffle(downloaded), 0, true)
          else if (key === 'play') this.play(pl.tracks, 0, false)
        },
      },
    ]
    pl.tracks.slice(0, MAX_ROWS).forEach((id) => {
      const t = lib.tracks[id] || { t: id, a: '' }
      const ok = isDownloaded(lib, id)
      const playing = ok && playingFile && t.f === playingFile
      items.push({
        type: playing ? T.PLAYING : ok ? T.OK : T.PEND,
        data: { title: t.t, artist: t.a || ' ', icon: playing ? IMG.eq : ok ? IMG.ok : IMG.wait },
        onClick: () => {
          if (!ok) return showToast({ content: 'Ainda baixando' })
          this.play(downloaded, downloaded.indexOf(id), false)
        },
      })
    })
    if (pl.tracks.length > MAX_ROWS) {
      items.push({ type: T.MORE, data: { label: `+${pl.tracks.length - MAX_ROWS} músicas (use Tocar)` } })
    }
    items.push({ type: T.FOOT, data: { x: '' } })
    this.state.items = items

    renderList(this.state, {
      x: px(24), y: 0, w: px(W), h: px(480), item_space: px(8),
      item_config: ITEM_CONFIG, item_config_count: ITEM_CONFIG.length,
    }, items, (index, key) => {
      const it = this.state.items[index]
      it && it.onClick && it.onClick(key)
    })
  },
})
