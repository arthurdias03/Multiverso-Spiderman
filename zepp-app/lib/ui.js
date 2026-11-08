import { createWidget, deleteWidget, widget, align, prop, text_style } from '@zos/ui'
import { px } from '@zos/utils'
import { COLOR } from './constants'

// Tela redonda 480x480: conteúdo numa coluna central de 360px
export const W = 480
export const COL_X = px(60)
export const COL_W = px(360)

export function title(text, y = 28) {
  return createWidget(widget.TEXT, {
    x: px(40), y: px(y), w: px(400), h: px(50),
    text, text_size: px(34), color: COLOR.accent,
    align_h: align.CENTER_H, align_v: align.CENTER_V, text_style: text_style.ELLIPSIS,
  })
}

export function label(text, y, h = 40, opts = {}) {
  return createWidget(widget.TEXT, {
    x: opts.x != null ? px(opts.x) : COL_X, y: px(y), w: opts.w != null ? px(opts.w) : COL_W, h: px(h),
    text, text_size: px(opts.size || 24), color: opts.color || COLOR.muted,
    align_h: align.CENTER_H, align_v: align.CENTER_V,
    text_style: opts.wrap ? text_style.WRAP : text_style.ELLIPSIS,
  })
}

export function button(text, y, onClick, opts = {}) {
  return createWidget(widget.BUTTON, {
    x: opts.x != null ? px(opts.x) : COL_X, y: px(y), w: opts.w != null ? px(opts.w) : COL_W, h: px(opts.h || 68),
    radius: px(opts.radius || 34),
    normal_color: opts.color || COLOR.item,
    press_color: opts.pressColor || COLOR.itemPressed,
    color: opts.textColor || COLOR.text,
    text_size: px(opts.size || 26),
    text,
    click_func: onClick,
  })
}

export function setText(w, text) {
  try {
    w && w.setProperty(prop.TEXT, text)
  } catch (e) {}
}

export function remove(widgets) {
  for (const w of widgets) {
    try {
      deleteWidget(w)
    } catch (e) {}
  }
  widgets.length = 0
}
