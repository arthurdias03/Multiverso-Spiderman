// spotifiBR Desktop: interface do painel local
const TOKEN = new URLSearchParams(location.search).get('t') || ''
history.replaceState(null, '', '/') // tira o token da barra de endereço
const $ = (id) => document.getElementById(id)
const COVERS = [['#7b2ff7', '#2f80ed'], ['#ff512f', '#f09819'], ['#11998e', '#38ef7d'], ['#fc466b', '#3f5efb'], ['#f7971e', '#ffd200'], ['#00c6ff', '#0072ff']]
let lastLog = 0
let state = null

async function api(path, { method = 'GET', body, raw } = {}) {
  const res = await fetch(path, {
    method,
    headers: { 'X-Panel-Token': TOKEN, ...(raw ? {} : { 'Content-Type': 'application/json' }) },
    body: raw || (body ? JSON.stringify(body) : undefined),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || (res.status === 409 ? 'Aguarde a tarefa atual terminar' : `Erro ${res.status}`))
  return data
}

function toast(msg, err) {
  const t = $('toast')
  t.textContent = msg
  t.className = 'toast show' + (err ? ' err' : '')
  clearTimeout(t._h)
  t._h = setTimeout(() => (t.className = 'toast'), 3200)
}

const act = (fn, okMsg) => async () => {
  try {
    await fn()
    if (okMsg) toast(okMsg)
    refresh()
  } catch (e) {
    toast(e.message, true)
  }
}

function cover(id) {
  let h = 0
  for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  const [a, b] = COVERS[h % COVERS.length]
  return `linear-gradient(135deg, ${a}, ${b})`
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag)
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'style') e.style.cssText = v
    else if (k === 'class') e.className = v
    else e.setAttribute(k, v)
  }
  for (const k of kids) e.append(k)
  return e
}

function render(s) {
  state = s
  if (s.error) return toast(s.error, true)
  const sp = s.spotify
  $('chip-spotify').className = 'chip ' + (sp.connected ? 'on' : 'warn')
  $('chip-spotify').textContent = sp.connected ? 'Spotify conectado' : 'Spotify desconectado'
  $('chip-server').className = 'chip ' + (s.server.running ? 'on' : '')
  $('chip-server').textContent = s.server.running ? 'Servidor ligado' : 'Servidor desligado'
  $('chip-auto').className = 'chip ' + (s.auto.enabled ? 'on' : '')
  $('chip-auto').textContent = s.auto.enabled ? `Automático · ${s.auto.minutes} min` : 'Automático desligado'
  $('spotify-text').textContent = !sp.client_id
    ? 'Primeiro cole o Client ID em Configurações (abaixo, à direita).'
    : sp.connected ? 'Conectado com permissão somente de leitura.' : 'Clique para autorizar no navegador.'
  $('btn-login').textContent = sp.connected ? 'Reconectar' : 'Conectar Spotify'
  $('btn-login').disabled = !sp.client_id

  $('server-box').classList.toggle('hidden', !s.server.running)
  $('server-text').textContent = s.server.running
    ? 'Ligado. Cole endereço e token em: app Zepp → T-Rex 3 → Apps → spotifiBR → Configurações.'
    : 'Desligado. Ligue para o relógio baixar as músicas pelo app Zepp.'
  if (s.server.running) {
    $('srv-url').textContent = s.server.url
    $('srv-token').textContent = s.server.token
  }
  $('btn-server').textContent = s.server.running ? 'Desligar servidor' : 'Ligar servidor'
  if (document.activeElement !== $('auto-min')) $('auto-min').value = s.auto.minutes
  $('auto').checked = s.auto.enabled
  $('busy').textContent = s.busy ? `⏳ ${s.busy}...` : ''
  $('btn-sync').disabled = !!s.busy

  const pls = s.summary.playlists || []
  $('last-sync').textContent = s.summary.time ? 'Último sync: ' + new Date(s.summary.time * 1000).toLocaleString('pt-BR') : 'Ainda não sincronizado'
  $('playlists').replaceChildren(...(pls.length ? pls.map((p) => {
    const pct = p.total ? Math.round((p.ready / p.total) * 100) : 0
    return el('div', { class: 'pl' },
      el('div', { class: 'cover', style: `background:${cover(p.id)}` }, '♪'),
      el('div', {}, el('b', {}, p.name), el('div', { class: 'bar' }, el('i', { style: `width:${pct}%` }))),
      el('span', { class: 'n' }, `${p.ready} de ${p.total}`))
  }) : [el('p', { class: 'muted' }, 'Configure as playlists e clique em Sincronizar agora.')]))

  const missing = pls.flatMap((p) => p.missing.map((m) => ({ ...m, pl: p.name })))
  $('missing-count').textContent = missing.length ? `${missing.length} música(s)` : ''
  const q = (m) => encodeURIComponent(`${m.artist} ${m.title}`)
  $('missing').replaceChildren(...(missing.length ? missing.slice(0, 300).map((m) =>
    el('div', { class: 'mi' },
      el('span', {}, `${m.artist} – ${m.title} `, el('small', {}, `· ${m.pl}`)),
      el('div', {},
        el('a', { href: `https://bandcamp.com/search?q=${q(m)}`, target: '_blank', rel: 'noopener noreferrer' }, 'Bandcamp'),
        el('a', { href: `https://music.apple.com/br/search?term=${q(m)}`, target: '_blank', rel: 'noopener noreferrer' }, 'iTunes'),
        el('a', { href: m.url, target: '_blank', rel: 'noopener noreferrer' }, 'Spotify'))))
    : [el('p', { class: 'muted' }, 'Nada faltando. 🎉')]))

  const cfg = s.settings
  if (!$('cfg-client').dataset.loaded) {
    $('cfg-client').value = cfg.spotify_client_id || ''
    $('cfg-playlists').value = (cfg.playlists || []).join('\n')
    $('cfg-dirs').value = (cfg.library_dirs || []).join('\n')
    $('cfg-bitrate').value = cfg.mp3_bitrate || '128k'
    $('cfg-client').dataset.loaded = '1'
  }
}

async function refresh() {
  try {
    render(await api('/api/status'))
  } catch (e) {
    toast(e.message, true)
  }
}

async function pollLog() {
  try {
    const rows = await api(`/api/log?since=${lastLog}`)
    if (rows.length) {
      const pre = $('log')
      for (const r of rows) {
        pre.textContent += `${new Date(r.t * 1000).toLocaleTimeString('pt-BR')}  ${r.msg}\n`
        lastLog = r.id
      }
      pre.scrollTop = pre.scrollHeight
      refresh()
    }
  } catch (e) {}
}

async function upload(files) {
  for (const f of files) {
    try {
      const r = await api(`/api/upload?name=${encodeURIComponent(f.name)}`, { method: 'PUT', raw: f })
      toast(`Adicionada: ${r.name}`)
    } catch (e) {
      toast(`${f.name}: ${e.message}`, true)
    }
  }
  refresh()
}

$('btn-login').onclick = act(() => api('/api/login', { method: 'POST' }), 'Autorize no navegador que abriu')
$('btn-sync').onclick = act(() => api('/api/sync', { method: 'POST' }), 'Sincronização iniciada')
$('btn-open').onclick = act(() => api('/api/open-library', { method: 'POST' }))
$('btn-server').onclick = act(() => api(state && state.server.running ? '/api/server/stop' : '/api/server/start', { method: 'POST' }))
$('btn-token').onclick = act(() => api('/api/token/new', { method: 'POST' }), 'Novo token gerado')
const saveAuto = act(() => api('/api/auto', { method: 'POST', body: { enabled: $('auto').checked, minutes: Number($('auto-min').value) || 10 } }))
$('auto').onchange = saveAuto
$('auto-min').onchange = saveAuto
$('btn-save').onclick = act(() => api('/api/settings', {
  method: 'POST',
  body: {
    spotify_client_id: $('cfg-client').value,
    playlists: $('cfg-playlists').value.split('\n'),
    library_dirs: $('cfg-dirs').value.split('\n'),
    mp3_bitrate: $('cfg-bitrate').value,
  },
}), 'Configurações salvas')
document.querySelectorAll('[data-copy]').forEach((b) => (b.onclick = () => {
  navigator.clipboard.writeText($(b.dataset.copy).textContent).then(() => toast('Copiado'))
}))
const drop = $('drop')
drop.onclick = () => $('file').click()
$('file').onchange = (e) => upload(e.target.files)
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over') }
drop.ondragleave = () => drop.classList.remove('over')
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); upload(e.dataTransfer.files) }

refresh()
pollLog()
setInterval(pollLog, 1500)
setInterval(refresh, 5000)
