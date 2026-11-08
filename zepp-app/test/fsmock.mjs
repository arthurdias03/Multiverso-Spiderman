export const files = new Map(); export const dirs = new Set([''])
export function readFileSync({ path }) { return files.has(path) ? files.get(path) : undefined }
export function writeFileSync({ path, data }) { files.set(path, data) }
export function statSync({ path }) { return files.has(path) ? { size: files.get(path).length } : undefined }
export function readdirSync({ path }) { if (!dirs.has(path)) return undefined; return [...files.keys()].filter(k => k.startsWith(path + '/')).map(k => k.slice(path.length + 1)) }
export function mkdirSync({ path }) { dirs.add(path); return 0 }
export function rmSync({ path }) { files.delete(path); return 0 }
export function renameSync({ oldPath, newPath }) { if (!files.has(oldPath)) return -1; files.set(newPath, files.get(oldPath)); files.delete(oldPath); return 0 }
