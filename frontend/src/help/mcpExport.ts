// Hilfe und Begriffe für die KI-Schnittstelle (MCP, Stufe 0; docs/mcp.md).
//
// Das Backend kennt die Markdown-Dateien der Hilfe und die Begriffe der Lernhilfen nicht
// (eigener Build-Kontext). Deshalb liegt eine Kopie in backend/mcpserver/hilfe.json.
// Erzeugen: node scripts/mcp-hilfe.mjs (im Ordner frontend). Der Test McpHilfe.test.ts
// meldet, wenn die Kopie nicht mehr zur Hilfe passt.
//
// Nur reine Funktionen und Daten ohne Browser, damit Node das Skript direkt ausführen kann.
import { DECISIONS, SECTIONS, TERMS } from '../learning/content.ts'

export interface GlossaryItem {
  key: string
  kind: 'term' | 'decision'
  name: string
  text: string
  example: string
  section: string
}

export interface McpExport {
  hinweis: string
  help: { de: Record<string, string>; en: Record<string, string> }
  glossary: { de: GlossaryItem[]; en: GlossaryItem[] }
}

export const MCP_EXPORT_NOTE =
  'Erzeugt aus frontend/src/help und frontend/src/learning mit „node scripts/mcp-hilfe.mjs“ ' +
  '(Ordner frontend). Nicht von Hand ändern.'

const sorted = (files: Record<string, string>) =>
  Object.fromEntries(
    Object.entries(files)
      .map(([name, raw]) => [name, raw.replace(/\r\n/g, '\n')] as const)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
  )

/** Begriffe und Entscheidungen; ``en`` ist der Katalog learning/en.json (deutsch → englisch). */
function glossary(en: Record<string, string> | null): GlossaryItem[] {
  const tx = (de: string) => (en ? en[de] || de : de)
  const sectionName = (k: string) => tx((SECTIONS as Record<string, { de: string }>)[k]?.de ?? '')
  const items: GlossaryItem[] = [
    ...Object.entries(TERMS).map(([key, t]) => ({
      key,
      kind: 'term' as const,
      name: (t.symbol ? `${t.symbol} – ` : '') + tx(t.name.de),
      text: tx(t.meaning.de),
      example: tx(t.example.de),
      section: sectionName(t.section),
    })),
    ...Object.entries(DECISIONS).map(([key, d]) => ({
      key,
      kind: 'decision' as const,
      name: tx(d.title.de),
      text: tx(d.text.de),
      example: '',
      section: tx(d.place.de),
    })),
  ]
  return items.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
}

/** Dateien je Sprache mit Namen relativ zum Sprachordner (z. B. „anleitungen/passwort.md“). */
export function buildMcpExport(
  files: { de: Record<string, string>; en: Record<string, string> },
  learningEn: Record<string, string>,
): McpExport {
  return {
    hinweis: MCP_EXPORT_NOTE,
    help: { de: sorted(files.de), en: sorted(files.en) },
    glossary: { de: glossary(null), en: glossary(learningEn) },
  }
}

/** Gleiche Ausgabe wie in der Datei (ein Leerzeichen Einrückung, Zeilenende am Schluss). */
export const mcpExportText = (data: McpExport) => JSON.stringify(data, null, 1) + '\n'
