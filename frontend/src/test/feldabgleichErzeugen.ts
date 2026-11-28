// Feldabgleich mit dem Server: macht aus den Antworten in backend/config/feldabgleich/<bereich>.json
// die Konstanten mit Typangabe unter src/test/feldabgleich. Benutzt von scripts/feldabgleich.mjs
// (schreibt die Dateien) und von Feldabgleich.test.ts (prüft, dass sie aktuell sind).
export type Antworten = Record<string, { typ: string; quelle: string; antworten: unknown[] }>

export function alsTypescript(daten: Antworten): string {
  const eintraege = Object.entries(daten).sort(([a], [b]) => (a < b ? -1 : 1))
  const quelle = eintraege[0][1].quelle
  const typen = [
    ...new Set(
      eintraege.flatMap(([, e]) => e.typ.replaceAll('[]', '').replace(/[<>]/g, ' ').split(/\s+/)),
    ),
  ]
    .filter(Boolean)
    .sort()
  const zeilen = [
    '// Erzeugt von scripts/feldabgleich.mjs aus backend/config/feldabgleich, nicht von Hand ändern.',
    '// Echte Antworten des Servers (Demoverein, erfundene Daten). Meldet die Typprüfung',
    '// hier einen Fehler, passen Server und Typ nicht zusammen: den Typ in',
    `// ${quelle.replace('../../', 'src/')} anpassen (oder den Server).`,
    `import type { ${typen.join(', ')} } from '${quelle}'`,
    '',
  ]
  for (const [name, e] of eintraege) {
    zeilen.push(`export const ${name}: (${e.typ})[] = ${JSON.stringify(e.antworten, null, 1)}`)
    zeilen.push('')
  }
  return zeilen.join('\n')
}
