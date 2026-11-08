import { onKey, KEY_UP, KEY_DOWN, KEY_EVENT_CLICK } from '@zos/interaction'
import { COLOR } from '../lib/constants'
import { title, label, button, setText } from '../lib/ui'
import { currentState, jump, pause, resume } from '../lib/player-control'

Page({
  state: { w: {} },

  build() {
    const w = this.state.w
    w.title = title('Tocando')
    w.track = label('', 120, 110, { size: 32, color: COLOR.text, wrap: true })
    w.artist = label('', 232, 44, { size: 24 })
    w.pos = label('', 280, 36, { size: 20 })

    button('<<', 330, () => this.cmd(jump.bind(null, -1)), { x: 70, w: 100 })
    w.toggle = button('Pausar', 330, () => this.toggle(), {
      x: 180, w: 120, color: COLOR.accent, pressColor: COLOR.accentPressed, textColor: 0x000000,
    })
    button('>>', 330, () => this.cmd(jump.bind(null, 1)), { x: 310, w: 100 })

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

  cmd(fn) {
    fn(() => this.refresh())
    this.refresh()
  },

  toggle() {
    const { now } = currentState()
    if (now.playing) this.cmd(pause)
    else this.cmd(resume)
  },

  refresh() {
    const { queue, now } = currentState()
    const w = this.state.w
    const items = queue.items || []
    const item = items[now.index || 0]
    setText(w.title, queue.title || 'Tocando')
    setText(w.track, item ? item.t : 'Nada na fila')
    setText(w.artist, item ? item.a : '')
    setText(w.pos, items.length ? `${(now.index || 0) + 1} / ${items.length}` : '')
    setText(w.toggle, now.playing ? 'Pausar' : 'Tocar')
  },

  onResume() {
    this.refresh()
  },
})
