import { readFileSync, writeFileSync, mkdirSync, readdirSync, rmSync, renameSync, statSync } from '@zos/fs'
import { LIB_FILE, MUSIC_DIR } from './constants'

export function readJSON(path, fallback) {
  try {
    const s = readFileSync({ path, options: { encoding: 'utf8' } })
    return s ? JSON.parse(s) : fallback
  } catch (e) {
    return fallback
  }
}

export function writeJSON(path, obj) {
  writeFileSync({ path, data: JSON.stringify(obj), options: { encoding: 'utf8' } })
}

export function fileSize(path) {
  const st = statSync({ path })
  return st ? st.size : -1
}

/** Converte "data://x/y" ou "/data/x/y" no caminho relativo usado pelo @zos/fs. */
export function relPath(p) {
  return String(p || '')
    .replace(/^data:\/\//, '')
    .replace(/^\/?data\//, '')
    .replace(/^\/+/, '')
}

export function ensureDir(path) {
  if (readdirSync({ path }) === undefined) mkdirSync({ path })
}

export function listDir(path) {
  return readdirSync({ path }) || []
}

export function remove(path) {
  try {
    rmSync({ path })
  } catch (e) {}
}

export function move(oldPath, newPath) {
  return renameSync({ oldPath, newPath }) === 0
}

/**
 * Biblioteca local:
 * { playlists: [{ id, name, tracks: [trackId] }], tracks: { id: { t, a, s, f } } }
 * f = caminho relativo do MP3 no /data (ausente => ainda não baixado)
 */
export function loadLibrary() {
  const lib = readJSON(LIB_FILE, null)
  return lib && lib.playlists && lib.tracks ? lib : { playlists: [], tracks: {} }
}

export function saveLibrary(lib) {
  writeJSON(LIB_FILE, lib)
}

export function trackPath(id) {
  return `${MUSIC_DIR}/${id}.mp3`
}

export function isDownloaded(lib, id) {
  const t = lib.tracks[id]
  return !!(t && t.f && fileSize(t.f) > 0)
}

/**
 * Aplica o manifesto do servidor: atualiza playlists/metadados, apaga o que saiu de todas
 * as playlists e devolve a lista do que falta baixar (na ordem das playlists).
 */
export function applyManifest(lib, manifest) {
  ensureDir(MUSIC_DIR)
  const nextTracks = {}
  const playlists = []
  const needed = []
  const seenNeeded = {}

  for (const pl of manifest.playlists || []) {
    const ids = []
    for (const tr of pl.tracks || []) {
      ids.push(tr.id)
      const old = lib.tracks[tr.id]
      nextTracks[tr.id] = { t: tr.t, a: tr.a, s: tr.s, f: old && old.f }
      if (!isDownloaded(lib, tr.id) && !seenNeeded[tr.id]) {
        seenNeeded[tr.id] = true
        nextTracks[tr.id].f = undefined
        needed.push({ id: tr.id, p: tr.p, s: tr.s })
      }
    }
    playlists.push({ id: pl.id, name: pl.name, tracks: ids })
  }

  // remove do relógio faixas que não estão mais em nenhuma playlist
  let removed = 0
  for (const id of Object.keys(lib.tracks)) {
    if (!nextTracks[id] && lib.tracks[id].f) {
      remove(lib.tracks[id].f)
      removed++
    }
  }

  lib.playlists = playlists
  lib.tracks = nextTracks
  saveLibrary(lib)
  return { needed, removed }
}

/** Move um arquivo recebido para music/<id>.mp3 e registra na biblioteca. */
export function adoptFile(lib, id, receivedPath) {
  ensureDir(MUSIC_DIR)
  const src = relPath(receivedPath)
  const dst = trackPath(id)
  let final = dst
  if (src !== dst) {
    remove(dst)
    if (!move(src, dst)) final = src // se não der para mover, toca de onde está
  }
  if (!lib.tracks[id]) lib.tracks[id] = { t: id, a: '' }
  lib.tracks[id].f = final
  saveLibrary(lib)
  return final
}

/** Reaproveita arquivos que chegaram enquanto o app estava fechado (tamanho confere com o manifesto). */
export function adoptLeftovers(lib, dir = 'download') {
  let n = 0
  for (const name of listDir(dir)) {
    const m = /^(.+)\.mp3$/.exec(name)
    if (!m) continue
    const id = m[1]
    const t = lib.tracks[id]
    const path = `${dir}/${name}`
    if (t && !isDownloaded(lib, id) && t.s && fileSize(path) === t.s) {
      adoptFile(lib, id, path)
      n++
    }
  }
  return n
}

export function playableTracks(lib, playlist) {
  return playlist.tracks.filter((id) => isDownloaded(lib, id))
}
