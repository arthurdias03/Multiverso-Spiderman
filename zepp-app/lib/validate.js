/**
 * Validação de tudo que vem de fora (servidor, celular, transferências).
 * Sem dependências do Zepp OS: usado no relógio, no side service e nos testes em Node.
 */

export const LIMITS = {
  playlists: 100,
  tracksPerPlaylist: 3000,
  tracksTotal: 10000,
  text: 120,
  fileBytes: 50 * 1024 * 1024,
  pathLen: 400,
}

const ID_RE = /^[A-Za-z0-9]{1,64}$/

export function isValidId(id) {
  return typeof id === 'string' && ID_RE.test(id)
}

/** Caminho relativo seguro: sem "..", sem "/" inicial, sem controle, sem barra invertida. */
export function isSafeRelPath(p) {
  if (typeof p !== 'string' || !p || p.length > LIMITS.pathLen) return false
  if (p[0] === '/' || p.indexOf('\\') >= 0 || /[\x00-\x1f\x7f]/.test(p)) return false
  return p.split('/').every((seg) => seg && seg !== '.' && seg !== '..')
}

export function cleanText(s, max = LIMITS.text) {
  return String(s == null ? '' : s).replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, max)
}

/** Devolve um manifesto limpo (descarta entradas inválidas e corta excessos). */
export function sanitizeManifest(m) {
  const out = { generated: Number(m && m.generated) || 0, playlists: [] }
  const playlists = m && Array.isArray(m.playlists) ? m.playlists : []
  let total = 0
  for (const pl of playlists.slice(0, LIMITS.playlists)) {
    if (!pl || !isValidId(pl.id)) continue
    const tracks = []
    const seen = {}
    for (const t of (Array.isArray(pl.tracks) ? pl.tracks : []).slice(0, LIMITS.tracksPerPlaylist)) {
      if (total >= LIMITS.tracksTotal) break
      if (!t || !isValidId(t.id) || seen[t.id] || !isSafeRelPath(t.p)) continue
      const size = Number(t.s)
      if (!(size > 0 && size <= LIMITS.fileBytes)) continue
      seen[t.id] = true
      tracks.push({ id: t.id, t: cleanText(t.t), a: cleanText(t.a), p: t.p, s: size })
      total++
    }
    out.playlists.push({ id: pl.id, name: cleanText(pl.name, 60) || 'Playlist', tracks })
  }
  return out
}

function isPrivateHost(host) {
  const h = String(host || '').toLowerCase().replace(/^\[|\]$/g, '')
  if (h === 'localhost' || h.endsWith('.local')) return true
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h)
  if (!m) return h === '::1' || /^f[cd][0-9a-f]{2}:/.test(h) || /^fe80:/.test(h)
  const [a, b] = [Number(m[1]), Number(m[2])]
  if ([m[1], m[2], m[3], m[4]].some((x) => Number(x) > 255)) return false
  return a === 10 || a === 127 || (a === 192 && b === 168) || (a === 172 && b >= 16 && b <= 31) ||
    (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254)
}

/**
 * Regras do endereço do servidor:
 * - https: qualquer host (tráfego cifrado)
 * - http: só IP/host de rede privada (o token não pode atravessar a internet em texto puro)
 * - sem usuário/senha embutidos, sem query/fragmento
 */
export function checkServerUrl(raw) {
  const url = String(raw || '').trim().replace(/\/+$/, '')
  const m = /^(https?):\/\/([^/?#@\s]+)(\/[^?#\s]*)?$/i.exec(url)
  if (!m) return { ok: false, error: 'Endereço inválido (use http://IP:porta ou https://...)' }
  const scheme = m[1].toLowerCase()
  const hostPort = m[2]
  const host = hostPort.replace(/:\d+$/, '')
  if (scheme === 'http' && !isPrivateHost(host)) {
    return { ok: false, error: 'http só é aceito na rede local. Para fora de casa use https' }
  }
  return { ok: true, url, secure: scheme === 'https' }
}

export function checkToken(token) {
  const t = String(token || '').trim()
  if (t.length < 32 || /[\s\x00-\x1f]/.test(t)) return { ok: false, error: 'Token ausente ou inválido' }
  return { ok: true, token: t }
}

export function encodePath(p) {
  return String(p).split('/').map(encodeURIComponent).join('/')
}
