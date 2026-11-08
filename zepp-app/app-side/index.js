/**
 * Side Service (roda dentro do app Zepp no celular).
 * Busca o manifesto no servidor do trex-sync, baixa os MP3 e transfere ao relógio, um por vez.
 */
import { BaseSideService, settingsLib } from '@zeppos/zml/base-side'
import { checkServerUrl, checkToken, sanitizeManifest, isValidId, isSafeRelPath, encodePath } from '../lib/validate'

const TOKEN_HEADER = 'X-Trex-Token'
const MAX_ATTEMPTS = 3
const RETRY_DELAY_MS = 5000

const state = {
  cancelled: false,
  queue: [],
  busy: false,
  current: null, // { download, file }
  total: 0,
  done: 0,
}

/** Lê e valida a configuração. O token vai SÓ no cabeçalho (nunca na URL, que pode parar em logs). */
function config() {
  const u = checkServerUrl(settingsLib.getItem('serverUrl'))
  if (!u.ok) throw new Error(u.error)
  const t = checkToken(settingsLib.getItem('token'))
  if (!t.ok) throw new Error(t.error)
  return { url: u.url, headers: { [TOKEN_HEADER]: t.token } }
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
      const { url, headers } = config()
      const r = await this.fetch({ url: `${url}/manifest.json`, method: 'GET', headers, timeout: 15000 })
      if (r.status === 401) throw new Error('Token inválido')
      if (r.status === 429) throw new Error('Bloqueado por tentativas erradas; aguarde 15 min')
      if (r.status !== 200) throw new Error(`Servidor respondeu ${r.status}`)
      let m
      try {
        m = typeof r.body === 'string' ? JSON.parse(r.body) : r.body
      } catch (e) {
        throw new Error('Resposta inválida do servidor')
      }
      return sanitizeManifest(m) // descarta IDs/caminhos inválidos e limita tamanhos
    },

    enqueue(items) {
      items = (Array.isArray(items) ? items : []).filter((i) => i && isValidId(i.id) && isSafeRelPath(i.p))
      const known = {}
      state.queue.forEach((i) => (known[i.id] = true))
      if (state.current) known[state.current.id] = true
      const fresh = items.filter((i) => !known[i.id])
      state.cancelled = false
      state.queue = state.queue.concat(fresh)
      state.total += fresh.length
      if (!state.busy) this.processNext()
      return { queued: state.queue.length, total: state.total }
    },

    cancelAll() {
      state.cancelled = true
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
      let cfg
      try {
        cfg = config()
      } catch (e) {
        state.queue = []
        state.busy = false
        state.current = null
        return this.notify({ finished: true, error: e.message })
      }
      const cur = { id: item.id }
      state.current = cur
      // Falha transitória (rede/Bluetooth) => até MAX_ATTEMPTS tentativas com espera crescente.
      // Erro definitivo (401/403/404) => desiste na hora. Nada se perde: o que faltar volta na próxima sincronização.
      const fail = (msg, permanent) => {
        if (state.current !== cur) return
        state.current = null
        item.attempts = (item.attempts || 1) + 1
        if (!permanent && item.attempts <= MAX_ATTEMPTS && !state.cancelled) {
          this.notify({ id: item.id, stage: `nova tentativa ${item.attempts}/${MAX_ATTEMPTS}` })
          state.queue.unshift(item)
          return setTimeout(() => this.processNext(), RETRY_DELAY_MS * (item.attempts - 1))
        }
        state.done++
        this.notify({ id: item.id, error: msg })
        this.processNext()
      }

      const task = this.download(`${cfg.url}/${encodePath(item.p)}`, {
        headers: cfg.headers,
        timeout: 180000,
        filePath: `${item.id}.mp3`, // id validado: [A-Za-z0-9]{1,64}
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
        if (ev.statusCode && ev.statusCode !== 200) {
          return fail(`HTTP ${ev.statusCode}`, [401, 403, 404].indexOf(ev.statusCode) >= 0)
        }
        const path = ev.filePath || ev.tempFilePath || `data://download/${item.id}.mp3`
        let file
        try {
          file = this.sendFile(path, { id: item.id, s: String(item.s || '') }) // nada de token aqui
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
            if (state.current !== cur) return
            state.current = null
            state.done++
            this.notify({ id: item.id, stage: 'ok' })
            this.processNext()
          } else if (st === 'error' || st === 'canceled') {
            fail(`envio ${st}`, st === 'canceled')
          }
        })
      }
    },
  }),
)
