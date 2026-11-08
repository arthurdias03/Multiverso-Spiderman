import assert from 'node:assert'
import { files, dirs } from './fsmock.mjs'
import * as S from './.build/storage.mjs'
const m1 = { playlists: [{ id: 'p', name: 'Rock', tracks: [{ id: 'a', t: 'A', a: 'X', p: 'Rock/a.mp3', s: 3 }, { id: 'b', t: 'B', a: 'Y', p: 'Rock/b.mp3', s: 4 }] }] }
let lib = S.loadLibrary()
let r = S.applyManifest(lib, m1)
assert.deepStrictEqual(r.needed.map(i => i.id), ['a', 'b'])
// arquivo "a" chega pela transferência
files.set('download/a.mp3', 'abc'); S.adoptFile(lib, 'a', 'data://download/a.mp3')
assert.ok(files.has('music/a.mp3') && !files.has('download/a.mp3'))
// "b" chegou com o app fechado -> recuperado se tamanho bate
dirs.add('download'); files.set('download/b.mp3', 'abcd')
lib = S.loadLibrary(); assert.strictEqual(S.adoptLeftovers(lib), 1)
assert.strictEqual(S.playableTracks(lib, lib.playlists[0]).length, 2)
// playlist muda: sai "a", entra "c"
const m2 = { playlists: [{ id: 'p', name: 'Rock', tracks: [{ id: 'b', t: 'B', a: 'Y', p: 'Rock/b.mp3', s: 4 }, { id: 'c', t: 'C', a: 'Z', p: 'Rock/c.mp3', s: 5 }] }] }
r = S.applyManifest(lib, m2)
assert.deepStrictEqual(r.needed.map(i => i.id), ['c']); assert.strictEqual(r.removed, 1)
assert.ok(!files.has('music/a.mp3') && files.has('music/b.mp3'))
assert.strictEqual(S.relPath('/data/download/x.mp3'), 'download/x.mp3')
console.log('JS OK')
