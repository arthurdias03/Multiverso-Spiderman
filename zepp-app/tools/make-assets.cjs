// Gera ícones, botões e capas (PNG transparentes) a partir de SVG, usando o Chromium do Playwright.
// Uso: node tools/make-assets.cjs   (saída em assets/common.r/)
// Ícones: Material Icons (Apache License 2.0).
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const OUT = path.join(__dirname, '..', 'assets', 'common.r')
const GREEN = '#1ed760', GREEN_P = '#17b04e'
const P = {
  play: 'M8 5v14l11-7z',
  pause: 'M6 19h4V5H6v14zm8-14v14h4V5h-4z',
  next: 'M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z',
  prev: 'M6 6h2v12H6zm3.5 6l8.5 6V6z',
  shuffle: 'M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z',
  sync: 'M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z',
  check: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  down: 'M12 4c4.41 0 8 3.59 8 8s-3.59 8-8 8-8-3.59-8-8 3.59-8 8-8m0-2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 10V8h-2v4H8l4 4 4-4h-3z',
  eq: 'M10 20h4V4h-4v16zm-6 0h4v-8H4v8zM16 9v11h4V9h-4z',
  note: 'M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z',
}
const COVERS = [['#7b2ff7', '#2f80ed'], ['#ff512f', '#f09819'], ['#11998e', '#38ef7d'],
  ['#fc466b', '#3f5efb'], ['#f7971e', '#ffd200'], ['#00c6ff', '#0072ff']]

// ícone (path 24x24) centralizado num quadro size x size, ocupando 'scale' do quadro
const glyph = (d, size, color, scale = 0.5, opacity = 1) => {
  const s = (size * scale) / 24, off = (size - 24 * s) / 2
  return `<path d="${d}" fill="${color}" fill-opacity="${opacity}" transform="translate(${off} ${off}) scale(${s})"/>`
}
const svg = (size, body) => `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${body}</svg>`
const circle = (size, fill) => `<circle cx="${size / 2}" cy="${size / 2}" r="${size / 2}" fill="${fill}"/>`

const assets = {}
// botões do player / playlist
for (const [name, d] of [['play', P.play], ['pause', P.pause]]) {
  assets[`btn/${name}_96.png`] = svg(96, circle(96, GREEN) + glyph(d, 96, '#000', 0.5))
  assets[`btn/${name}_96_p.png`] = svg(96, circle(96, GREEN_P) + glyph(d, 96, '#000', 0.46))
}
for (const [name, d] of [['prev', P.prev], ['next', P.next]]) {
  assets[`btn/${name}_64.png`] = svg(64, glyph(d, 64, '#fff', 0.62))
  assets[`btn/${name}_64_p.png`] = svg(64, circle(64, 'rgba(255,255,255,0.14)') + glyph(d, 64, '#b3b3b3', 0.58))
}
assets['btn/shuffle_72.png'] = svg(72, circle(72, '#2a2a2a') + glyph(P.shuffle, 72, '#fff', 0.46))
assets['btn/shuffle_72_p.png'] = svg(72, circle(72, '#3d3d3d') + glyph(P.shuffle, 72, GREEN, 0.44))
// ícones de linha
assets['icons/sync_56.png'] = svg(56, circle(56, GREEN) + glyph(P.sync, 56, '#000', 0.55))
assets['icons/ok_28.png'] = svg(28, glyph(P.check, 28, GREEN, 1))
assets['icons/wait_28.png'] = svg(28, glyph(P.down, 28, '#6a6a6a', 1))
assets['icons/eq_28.png'] = svg(28, glyph(P.eq, 28, GREEN, 0.9))
assets['icons/shuffle_24.png'] = svg(24, glyph(P.shuffle, 24, GREEN, 1))
assets['icons/blank_28.png'] = svg(28, '')
// capas (gradiente + nota)
COVERS.forEach(([a, b], i) => {
  for (const size of [64, 140]) {
    const r = Math.round(size * 0.14)
    assets[`covers/c${i}_${size}.png`] = svg(size,
      `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs>` +
      `<rect width="${size}" height="${size}" rx="${r}" fill="url(#g)"/>` + glyph(P.note, size, '#fff', 0.52, 0.85))
  }
})
// ícone do app
assets['icon.png'] = svg(248,
  `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${GREEN}"/><stop offset="1" stop-color="#0f9b8e"/></linearGradient></defs>` +
  `<circle cx="124" cy="124" r="124" fill="url(#g)"/>` + glyph(P.note, 248, '#fff', 0.56))

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ deviceScaleFactor: 1 })
  for (const [file, markup] of Object.entries(assets)) {
    const size = Number(/width="(\d+)"/.exec(markup)[1])
    await page.setViewportSize({ width: size, height: size })
    await page.setContent(`<html><body style="margin:0;background:transparent">${markup}</body></html>`)
    const dest = path.join(OUT, file)
    fs.mkdirSync(path.dirname(dest), { recursive: true })
    await page.screenshot({ path: dest, omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } })
  }
  await browser.close()
  console.log(`${Object.keys(assets).length} imagens em ${OUT}`)
})()
