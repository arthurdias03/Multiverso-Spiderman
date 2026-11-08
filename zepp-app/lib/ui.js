import { createWidget, deleteWidget, widget, align, prop, text_style } from '@zos/ui'
import { px } from '@zos/utils'
import { COLOR } from './constants'

export { align, prop }

const COVER_COUNT = 6

/** Capa com gradiente escolhida de forma estável pelo id da playlist. */
export function coverFor(id, size) {
  let h = 0
  for (const ch of String(id || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return `covers/c${h % COVER_COUNT}_${size}.png`
}

/** Converte a lista de tipos por item em data_type_config (intervalos fechados [start, end]). */
export function typeRanges(types) {
  const out = []
  types.forEach((t, i) => {
    const last = out[out.length - 1]
    if (last && last.type_id === t && last.end === i - 1) last.end = i
    else out.push({ start: i, end: i, type_id: t })
  })
  return out
}

/** Cria/atualiza um SCROLL_LIST a partir de [{ type, data, onClick }]. */
export function renderList(state, base, items, onClick) {
  const payload = {
    data_array: items.map((i) => i.data),
    data_count: items.length,
    data_type_config: typeRanges(items.map((i) => i.type)),
    data_type_config_count: 0,
  }
  payload.data_type_config_count = payload.data_type_config.length
  if (!state.list) {
    state.list = createWidget(widget.SCROLL_LIST, {
      ...base,
      ...payload,
      item_click_func: (list, index, key) => onClick(index, key),
    })
  } else {
    state.list.setProperty(prop.UPDATE_DATA, { ...payload, on_page: 1 })
  }
}

export function text(o) {
  return createWidget(widget.TEXT, {
    x: px(o.x), y: px(o.y), w: px(o.w), h: px(o.h),
    text: o.text || '', text_size: px(o.size || 24), color: o.color == null ? COLOR.text : o.color,
    align_h: o.align === 'left' ? align.LEFT : align.CENTER_H, align_v: align.CENTER_V,
    text_style: o.wrap ? text_style.WRAP : text_style.ELLIPSIS,
  })
}

export function image(x, y, src) {
  return createWidget(widget.IMG, { x: px(x), y: px(y), src })
}

export function imageButton(x, y, size, src, pressSrc, onClick) {
  return createWidget(widget.BUTTON, {
    x: px(x), y: px(y), w: px(size), h: px(size), normal_src: src, press_src: pressSrc, click_func: onClick,
  })
}

export function setText(w, value) {
  try {
    w && w.setProperty(prop.TEXT, value)
  } catch (e) {}
}

export function remove(w) {
  try {
    w && deleteWidget(w)
  } catch (e) {}
}
