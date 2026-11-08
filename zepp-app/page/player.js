import { onKey, KEY_UP, KEY_DOWN, KEY_EVENT_CLICK } from '@zos/interaction'
import { COLOR, IMG } from '../lib/constants'
import { text, image, imageButton, setText, remove, coverFor } from '../lib/ui'
import { currentState, jump, pause, resume } from '../lib/player-control'

// Layout "tocando agora" (480x480 redondo): origem -> capa -> título/artista -> controles -> posição
Page({
  state: { w: {}, playing: null },

  build() {
    const w = this.state.w
    const { queue } = currentState()
    w.from = text({ x: 120, y: 30, w: 240, h: 22, text: 'TOCANDO DE', size: 15, color: COLOR.sub })
    w.list = text({ x: 90, y: 52, w: 300, h: 30, text: queue.title || 'Fila', size: 20 })
    w.cover = image(170, 92, coverFor(queue.playlistId || queue.title, 140))
    w.title = text({ x: 50, y: 244, w: 380, h: 42, size: 28 })
    w.artist = text({ x: 70, y: 286, w: 340, h: 30, size: 20, color: COLOR.sub })

    imageButton(108, 346, 64, IMG.prev, IMG.prevP, () => this.cmd(jump.bind(null, -1)))
    imageButton(308, 346, 64, IMG.next, IMG.nextP, () => this.cmd(jump.bind(null, 1)))
    w.pos = text({ x: 150, y: 436, w: 180, h: 24, size: 16, color: COLOR.sub })
    w.shuffleIcon = null

    // botões físicos: cima = anterior, baixo = próxima
    try {
      onKey({
        callback: (key, ev) => {
          if (ev !== KEY_EVENT_CLICK) return false
          if (key === KEY_UP) this.cmd(jump.bind(null, -1))
          else if (key === KEY_DOWN) this.cmd(jump.bind(null, 1))
          else return false
          return true
        },
      })
    } catch (e) {}

    this.refresh()
  },

  drawToggle(playing) {
    if (this.state.playing === playing) return
    this.state.playing = playing
    remove(this.state.w.toggle)
    this.state.w.toggle = playing
      ? imageButton(192, 330, 96, IMG.pause, IMG.pauseP, () => this.cmd(pause))
      : imageButton(192, 330, 96, IMG.play, IMG.playP, () => this.cmd(resume))
  },

  cmd(fn) {
    fn(() => this.refresh())
    this.refresh()
  },

  refresh() {
    const { queue, now } = currentState()
    const w = this.state.w
    const items = queue.items || []
    const item = items[now.index || 0]
    setText(w.title, item ? item.t : 'Nada tocando')
    setText(w.artist, item ? item.a : 'Escolha uma playlist')
    setText(w.pos, items.length ? `${queue.shuffle ? 'Aleatório · ' : ''}${(now.index || 0) + 1} de ${items.length}` : '')
    this.drawToggle(!!now.playing)
  },

  onResume() {
    this.refresh()
  },
})
