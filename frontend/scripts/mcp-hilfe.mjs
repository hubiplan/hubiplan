// Schreibt die Hilfe für die KI-Schnittstelle nach backend/mcpserver/hilfe.json
// (src/help/mcpExport.ts, docs/mcp.md). Nach jeder Änderung an der Hilfe oder den
// Lernhilfen ausführen und die Datei mit einchecken:
//
//   node scripts/mcp-hilfe.mjs        (im Ordner frontend, Node ab 22.18)
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildMcpExport, mcpExportText } from '../src/help/mcpExport.ts'

const root = fileURLToPath(new URL('..', import.meta.url))

function markdown(dir) {
  const out = {}
  const walk = (d) => {
    for (const entry of readdirSync(d, { withFileTypes: true })) {
      const path = join(d, entry.name)
      if (entry.isDirectory()) walk(path)
      else if (entry.name.endsWith('.md'))
        out[relative(dir, path).split('\\').join('/')] = readFileSync(path, 'utf-8')
    }
  }
  walk(dir)
  return out
}

const help = join(root, 'src', 'help')
const files = { de: markdown(join(help, 'de')), en: markdown(join(help, 'en')) }
const learningEn = JSON.parse(readFileSync(join(root, 'src', 'learning', 'en.json'), 'utf-8'))
const target = join(root, '..', 'backend', 'mcpserver', 'hilfe.json')
writeFileSync(target, mcpExportText(buildMcpExport(files, learningEn)))
console.log(`geschrieben: ${relative(process.cwd(), target)}`)
