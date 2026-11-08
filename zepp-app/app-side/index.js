/**
 * Side Service (roda dentro do app Zepp no celular).
 * Busca o manifesto no servidor do trex-sync, baixa os MP3 e transfere ao relógio, um por vez.
 */
import { BaseSideService, settingsLib } from '@zeppos/zml/base-side'

const state = {
  queue: [],
  busy: false,
  current: null, // { download, file }
  total: 0,
  done: 0,
}

function config() {
  const url = String(settingsLib.getItem('serverUrl') || '').trim().replace(/\/+$/, '')
  const token = String(settingsLib.getItem('token') || '').trim()
  return { url, token }
}

function withToken(url, token) {
  return token ? `${url}${url.indexOf('?') >= 0 ? '&' : '?'}k=${encodeURIComponent(token)}` : url
}

function encodePath(p) {
  return String(p).split('/').map(encodeURIComponent).join('/')
}

AppSideService(
  BaseSideService({
    onInit() {},
    onRun() {},
    onDestroy() {
      this.cancelAll()
    },

    onRequest(req, res) {
      switch (req.method) {
        case 'manifest':
          return this.getManifest().then(
            (m) => res(null, m),
            (e) => res({ message: String((e && e.message) || e) }),
          )
        case 'download':
          return res(null, this.enqueue((req.params && req.params.items) || []))
        case 'cancel':
          this.cancelAll()
          return res(null, { ok: true })
        default:
          return res({ message: 'método desconhecido: ' + req.method })
      }
    },

    async getManifest() {
      const { url, token } = config()
      if (!url) throw new Error('Configure o endereço do servidor no app Zepp')
      const r = await this.fetch({ url: withToken(`${url}/manifest.json`, token), method: 'GET', timeout: 15000 })
      if (r.status === 401) throw new Error('Token inválido')
      if (r.status !== 200) throw new Error(`Servidor respondeu ${r.status}`)
      const m = typeof r.body === 'string' ? JSON.parse(r.body) : r.body
      return {
        generated: m.generated,
        playlists: (m.playlists || []).map((pl) => ({
          id: pl.id,
          name: pl.name,
          tracks: (pl.tracks || []).map((t) => ({ id: t.id, t: t.t, a: t.a, p: t.p, s: t.s })),
        })),
      }
    },

    enqueue(items) {
      const known = {}
      state.queue.forEach((i) => (known[i.id] = true))
      if (state.current) known[state.current.id] = true
      const fresh = items.filter((i) => !known[i.id])
      state.queue = state.queue.concat(fresh)
      state.total += fresh.length
      if (!state.busy) this.processNext()
      return { queued: state.queue.length, total: state.total }
    },

    cancelAll() {
      state.queue = []
      if (state.current) {
        try {
          state.current.download && state.current.download.cancel()
        } catch (e) {}
        try {
          state.current.file && state.current.file.cancel()
        } catch (e) {}
      }
      state.current = null
      state.busy = false
      state.total = 0
      state.done = 0
    },

    notify(params) {
      try {
        this.call({ method: 'sync.progress', params: { ...params, done: state.done, total: state.total } })
      } catch (e) {}
    },

    processNext() {
      const item = state.queue.shift()
      if (!item) {
        state.busy = false
        state.current = null
        this.notify({ finished: true })
        state.total = 0
        state.done = 0
        return
      }
      state.busy = true
      const { url, token } = config()
      const cur = { id: item.id }
      state.current = cur
      const fail = (msg) => {
        state.done++
        this.notify({ id: item.id, error: msg })
        this.processNext()
      }

      const task = this.download(withToken(`${url}/${encodePath(item.p)}`, token), {
        timeout: 180000,
        filePath: `${item.id}.mp3`,
      })
      cur.download = task
      let lastPct = -1
      task.onProgress = (ev) => {
        const pct = Math.floor((ev.progress || 0) / 25) * 25
        if (pct !== lastPct) {
          lastPct = pct
          this.notify({ id: item.id, stage: 'baixando', pct: ev.progress })
        }
      }
      task.onFail = (ev) => fail(`download falhou (${ev && ev.code})`)
      task.onSuccess = (ev) => {
        if (ev.statusCode && ev.statusCode !== 200) return fail(`HTTP ${ev.statusCode}`)
        const path = ev.filePath || ev.tempFilePath || `data://download/${item.id}.mp3`
        let file
        try {
          file = this.sendFile(path, { id: item.id, s: String(item.s || '') })
        } catch (e) {
          return fail('transferência indisponível')
        }
        cur.file = file
        let lastT = -1
        file.on('progress', (e) => {
          const d = e.data || {}
          const pct = d.fileSize ? Math.floor((d.loadedSize / d.fileSize) * 100) : 0
          const step = Math.floor(pct / 10)
          if (step !== lastT) {
            lastT = step
            this.notify({ id: item.id, stage: 'enviando', pct })
          }
        })
        file.on('change', (e) => {
          const st = e.data && e.data.readyState
          if (st === 'transferred') {
            state.done++
            this.notify({ id: item.id, stage: 'ok' })
            this.processNext()
          } else if (st === 'error' || st === 'canceled') {
            if (state.current === cur) fail(`envio ${st}`)
          }
        })
      }
    },
  }),
)
