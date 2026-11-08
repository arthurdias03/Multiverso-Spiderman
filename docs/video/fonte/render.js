// Renderiza o vídeo quadro a quadro (determinístico) e envia os JPEGs direto para o ffmpeg
const { chromium } = require('playwright')
const { spawn } = require('child_process')
const FPS = Number(process.env.FPS || 30)
const LIMIT = Number(process.env.LIMIT || 0)
;(async () => {
  const b = await chromium.launch()
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } })
  await p.goto('file://' + __dirname + '/video.html')
  await p.waitForTimeout(800)
  const duration = await p.evaluate(() => window.DURATION)
  const total = LIMIT || Math.round(duration * FPS)
  const out = process.env.OUT || __dirname + '/spotifibr.mp4'
  const ff = spawn('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-shortest',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    '-c:a', 'aac', '-b:a', '64k', out], { stdio: ['pipe', 'inherit', 'inherit'] })
  const t0 = Date.now()
  for (let i = 0; i < total; i++) {
    await p.evaluate((t) => setTime(t), i / FPS)
    const buf = await p.screenshot({ type: 'jpeg', quality: 92 })
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r))
    if (i % 300 === 0) console.log(`quadro ${i}/${total} (${((Date.now() - t0) / 1000).toFixed(0)} s)`)
  }
  ff.stdin.end()
  await new Promise((r) => ff.on('close', r))
  await b.close()
  console.log(`ok: ${total} quadros em ${((Date.now() - t0) / 1000).toFixed(0)} s -> ${out}`)
})()
