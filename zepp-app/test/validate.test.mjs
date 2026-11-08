import assert from 'node:assert'
import { isValidId, isSafeRelPath, sanitizeManifest, checkServerUrl, checkToken, LIMITS } from '../lib/validate.js'

assert.ok(isValidId('4uLU6hMCjMI75M1A2tKUQC'))
for (const bad of ['../x', 'a/b', '', 'a'.repeat(65), 'ção', null, 'x.mp3']) assert.ok(!isValidId(bad), bad)

assert.ok(isSafeRelPath('Rock/Queen - Bohemian Rhapsody.mp3'))
for (const bad of ['../etc/passwd', '/abs', 'a/../b', 'a//b', 'a\\b', 'a/\u0000', '.', 'x/..']) assert.ok(!isSafeRelPath(bad), bad)

const dirty = {
  generated: 1,
  playlists: [
    { id: 'p1', name: 'Rock\u0007', tracks: [
      { id: 'ok1', t: 'A', a: 'B', p: 'Rock/a.mp3', s: 10 },
      { id: '../evil', t: 'x', a: 'y', p: 'Rock/b.mp3', s: 10 },
      { id: 'ok2', t: 'x', a: 'y', p: '../../b.mp3', s: 10 },
      { id: 'ok3', t: 'x', a: 'y', p: 'Rock/c.mp3', s: LIMITS.fileBytes + 1 },
      { id: 'ok1', t: 'dup', a: 'y', p: 'Rock/a.mp3', s: 10 },
      { id: 'ok4', t: 'z'.repeat(500), a: 'y', p: 'Rock/d.mp3', s: 5 },
    ] },
    { id: 'bad/id', name: 'x', tracks: [] },
  ],
}
const clean = sanitizeManifest(dirty)
assert.strictEqual(clean.playlists.length, 1)
assert.deepStrictEqual(clean.playlists[0].tracks.map((t) => t.id), ['ok1', 'ok4'])
assert.strictEqual(clean.playlists[0].tracks[1].t.length, LIMITS.text)
assert.strictEqual(clean.playlists[0].name, 'Rock ')
assert.deepStrictEqual(sanitizeManifest(null).playlists, [])

for (const ok of ['http://192.168.0.10:8765', 'http://10.0.0.2:8765/', 'http://100.101.1.2:8765', 'https://music.exemplo.com', 'http://meupc.local:8765'])
  assert.ok(checkServerUrl(ok).ok, ok)
for (const bad of ['http://meuservidor.com:8765', 'http://8.8.8.8', 'ftp://192.168.0.1', 'http://user:pw@192.168.0.1',
  'http://192.168.0.1.evil.com', 'http://192.168.0.1:8765?x=1', 'javascript:alert(1)', '', 'http://999.168.0.1'])
  assert.ok(!checkServerUrl(bad).ok, bad)
assert.ok(checkServerUrl('https://x.com').secure)

assert.ok(checkToken('a'.repeat(43)).ok)
assert.ok(!checkToken('curto').ok)
assert.ok(!checkToken('a'.repeat(20) + ' ' + 'b'.repeat(20)).ok)
console.log('validate OK')
