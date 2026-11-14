// Legt neben jede Text-Datei des fertigen Frontends (dist/) eine Brotli- und eine
// gzip-Fassung (.br, .gz) auf höchster Stufe. Caddy liefert sie mit „precompressed“ aus
// (deploy/caddy/site.caddy), statt beim Abruf selbst zu komprimieren: kleinere Bündel beim
// ersten Aufruf, keine Rechenzeit beim Ausliefern (Ladezeiten 14.11.2026).
// Aufruf: node scripts/vorkomprimieren.mjs [Ordner, Standard dist]
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { brotliCompressSync, constants, gzipSync } from 'node:zlib'

const ENDUNGEN = /\.(js|mjs|css|html|svg|json|webmanifest|txt|xml|md)$/i
// Kleine Dateien lohnen den Umweg nicht (Kopfzeilen sind größer als die Ersparnis)
const MINDESTGROESSE = 1024

function dateien(ordner) {
  return readdirSync(ordner).flatMap((name) => {
    const pfad = join(ordner, name)
    return statSync(pfad).isDirectory() ? dateien(pfad) : [pfad]
  })
}

const ordner = process.argv[2] ?? 'dist'
let anzahl = 0
let vorher = 0
let nachher = 0
for (const pfad of dateien(ordner)) {
  if (!ENDUNGEN.test(pfad)) continue
  const inhalt = readFileSync(pfad)
  if (inhalt.length < MINDESTGROESSE) continue
  const br = brotliCompressSync(inhalt, {
    params: {
      [constants.BROTLI_PARAM_QUALITY]: constants.BROTLI_MAX_QUALITY,
      [constants.BROTLI_PARAM_SIZE_HINT]: inhalt.length,
    },
  })
  const gz = gzipSync(inhalt, { level: 9 })
  // Nur ablegen, was wirklich kleiner ist
  if (br.length < inhalt.length) writeFileSync(`${pfad}.br`, br)
  if (gz.length < inhalt.length) writeFileSync(`${pfad}.gz`, gz)
  anzahl += 1
  vorher += inhalt.length
  nachher += Math.min(br.length, inhalt.length)
}
console.log(
  `vorkomprimiert: ${anzahl} Dateien, ${Math.round(vorher / 1024)} KB → ${Math.round(nachher / 1024)} KB (Brotli)`,
)
