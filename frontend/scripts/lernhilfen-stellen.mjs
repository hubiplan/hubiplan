// Schreibt src/learning/places.json: zu jeder Erklärung („Warum?“) die Seite, auf der sie
// steht, damit das Glossar „Zur Stelle“ anbieten kann (docs/lernhilfen.md).
//
// Liest die Routen aus den <Route>-Angaben der Oberfläche und sucht, in welcher Seite
// <Why k="…"> vorkommt. Nach neuen Erklärungen oder verschobenen Seiten ausführen und
// die Datei mit einchecken; src/test/Lernhilfen.test.tsx meldet, wenn sie veraltet ist:
//
//   node scripts/lernhilfen-stellen.mjs        (im Ordner frontend)
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const src = join(root, 'src')
const WRAPPERS = new Set(['RequireOrg', 'RequireModule', 'Navigate', 'Suspense', 'Route'])

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== 'test') walk(path, out)
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) out.push(path)
  }
  return out
}

const files = walk(src)
const text = new Map(files.map((f) => [f, readFileSync(f, 'utf-8')]))

function target(from, spec) {
  const base = resolve(dirname(from), spec)
  for (const cand of [base, `${base}.tsx`, `${base}.ts`, join(base, 'index.tsx')])
    if (text.has(cand)) return cand
  return existsSync(base) ? base : null
}

/** Je Datei: Name im Quelltext → Datei, aus der er kommt (auch lazy geladene Seiten). */
const imports = new Map()
const importers = new Map()
for (const [file, code] of text) {
  const names = new Map()
  const add = (name, spec) => {
    const to = target(file, spec)
    if (!to) return
    names.set(name, to)
    if (!importers.has(to)) importers.set(to, new Set())
    importers.get(to).add(file)
  }
  for (const m of code.matchAll(/import\s+(?!type\b)([^'";]+?)\s+from\s+'(\.[^']+)'/g)) {
    const [, what, spec] = m
    for (const part of what.replace(/[{}]/g, ',').split(',')) {
      const name = part
        .trim()
        .split(/\s+as\s+/)
        .pop()
      if (name && /^\w+$/.test(name)) add(name, spec)
    }
  }
  for (const m of code.matchAll(
    /const\s+(\w+)\s*=\s*lazy\w*\(\s*\(\)\s*=>\s*import\('(\.[^']+)'\)/g,
  ))
    add(m[1], m[2])
  imports.set(file, names)
}

/** <Route>-Angaben einer Datei mit Pfad (samt umschließender Routen) und Komponenten. */
function routesIn(code) {
  const out = []
  const stack = []
  const re = /<Route\b|<\/Route>/g
  let m
  while ((m = re.exec(code))) {
    if (m[0] === '</Route>') {
      stack.pop()
      continue
    }
    let i = m.index + 6
    let depth = 0
    for (; i < code.length; i++) {
      const c = code[i]
      if (c === '{') depth++
      else if (c === '}') depth--
      else if (c === '>' && depth === 0) break
    }
    const tag = code.slice(m.index, i + 1)
    const path = /\bpath="([^"]*)"/.exec(tag)?.[1] ?? ''
    const element = /element=\{([\s\S]*)\}/.exec(tag)?.[1] ?? ''
    const comps = [...element.matchAll(/<(\w+)/g)].map((x) => x[1]).filter((n) => !WRAPPERS.has(n))
    const full = [...stack, path].filter(Boolean).join('/')
    out.push({ path: full, comps, at: m.index })
    if (!tag.endsWith('/>')) stack.push(path)
    re.lastIndex = i + 1
  }
  return out
}

const clean = (p) =>
  `/${p}`
    .replace(/\/\*$/, '')
    .replace(/\/+/g, '/')
    .replace(/(.)\/$/, '$1')

/** Name der Komponente (Funktion auf oberster Ebene), in der eine Stelle der Datei liegt. */
const scopes = new Map()
function scopeAt(file, index) {
  if (!scopes.has(file))
    scopes.set(
      file,
      [...text.get(file).matchAll(/^(?:export\s+)?(?:default\s+)?function\s+(\w+)/gm)].map((m) => ({
        name: m[1],
        at: m.index,
      })),
    )
  let name = null
  for (const s of scopes.get(file)) if (s.at <= index) name = s.name
  return name
}

/** Datei oder „Datei#Komponente“ → Adressen, unter denen sie als Seite eingehängt ist */
const mounts = new Map([[join(src, 'App.tsx'), ['']]])
const mountsOf = (file, comp) => mounts.get(`${file}#${comp}`) ?? mounts.get(file)
function mount(key, full) {
  const found = mounts.get(key) ?? []
  if (!found.includes(full)) found.push(full)
  mounts.set(key, found)
}
for (let round = 0; round < 8; round++)
  for (const [file, code] of text) {
    if (!code.includes('<Route')) continue
    for (const route of routesIn(code)) {
      const bases = mountsOf(file, scopeAt(file, route.at))
      if (!bases) continue
      for (const comp of route.comps) {
        const imported = imports.get(file).get(comp)
        const local = !imported && new RegExp(`^(?:export\\s+)?function ${comp}\\b`, 'm').test(code)
        if (!imported && !local) continue
        for (const base of bases) {
          const full = clean(`${base}/${route.path}`)
          if (imported) {
            mount(imported, full)
            mount(`${imported}#${comp}`, full)
          } else mount(`${file}#${comp}`, full)
        }
      }
    }
  }

/** Adressen, die eine Seitenhilfe kennt: nur dorthin führt „Zur Stelle“. */
const known = new Set()
for (const name of readdirSync(join(src, 'help', 'de', 'seiten'))) {
  const head = readFileSync(join(src, 'help', 'de', 'seiten', name), 'utf-8').split('\n---')[0]
  const list = /^routen:\s*\[([^\]]*)\]/m.exec(head.replace(/\n[ \t]+/g, ' '))?.[1] ?? ''
  for (const route of list.split(',').map((s) => s.trim()))
    if (route && route !== '/' && !route.includes(':')) known.add(route)
}

/** Die Adresse selbst oder die nächste darüber, die eine Seitenhilfe hat. */
function knownAbove(path) {
  let p = path.replace(/\/:.*$/, '')
  while (p && !known.has(p)) p = p.slice(0, p.lastIndexOf('/'))
  return p || null
}

/** Arbeitsbereich einer Untereinheit: nur, wenn es keine andere Stelle gibt. */
const late = (p) => Number(p.startsWith('/abteilung'))

/** Beste Adresse: die genaueste mit Seitenhilfe. */
function best(paths) {
  const usable = [...new Set(paths.map(knownAbove).filter(Boolean))].sort(
    (a, b) => late(a) - late(b) || b.split('/').length - a.split('/').length || a.localeCompare(b),
  )
  return usable[0] ?? null
}

function routeOf(file, index) {
  const own = best(mounts.get(`${file}#${scopeAt(file, index)}`) ?? [])
  if (own) return own
  const seen = new Set([file])
  let level = [file]
  for (let depth = 0; depth < 5 && level.length; depth++) {
    const hits = level.flatMap((f) => mounts.get(f) ?? [])
    const found = best(hits)
    if (found) return found
    const next = []
    for (const f of level)
      for (const up of importers.get(f) ?? [])
        if (!seen.has(up)) {
          seen.add(up)
          next.push(up)
        }
    level = next
  }
  return null
}

const places = {}
for (const [file, code] of text)
  for (const m of code.matchAll(/<Why\s+k="(\w+)"|\bwhy="(\w+)"/g)) {
    const key = m[1] ?? m[2]
    const route = routeOf(file, m.index)
    if (!route || late(route)) continue
    const old = places[key]
    if (
      !old ||
      late(route) < late(old) ||
      (late(route) === late(old) && route.localeCompare(old) < 0)
    )
      places[key] = route
  }

const sorted = Object.fromEntries(Object.entries(places).sort(([a], [b]) => a.localeCompare(b)))
const out = join(src, 'learning', 'places.json')
writeFileSync(out, `${JSON.stringify(sorted, null, 2)}\n`)
console.log(`${Object.keys(sorted).length} Stellen nach ${relative(root, out)}`)
