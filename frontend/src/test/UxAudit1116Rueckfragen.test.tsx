// UX-Audit 16.11.2026, VW-23: Jede rote Rückfrage sagt, ob sich die Handlung zurücknehmen
// lässt. `final: true` ergänzt den Satz im Dialog; was „Rückgängig“ zurückholt, fragt nicht.
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { confirmDialog } from '../components/dialog.ts'

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const path = join(dir, e.name)
    if (e.isDirectory()) return e.name === 'test' ? [] : sources(path)
    return /\.tsx?$/.test(e.name) ? [path] : []
  })
}

/** Die Optionen jeder Rückfrage, die direkt als Objekt übergeben wird. */
function confirmations(): { where: string; body: string }[] {
  const found: { where: string; body: string }[] = []
  for (const file of sources('src')) {
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(/confirmDialog\(\{/g)) {
      let depth = 1
      let i = m.index + m[0].length
      for (; depth > 0 && i < text.length; i++) {
        if (text[i] === '{') depth++
        else if (text[i] === '}') depth--
      }
      const line = text.slice(0, m.index).split('\n').length
      found.push({ where: `${file}:${line}`, body: text.slice(m.index, i) })
    }
  }
  return found
}

describe('VW-23 Rückfragen nennen die Folge', () => {
  it('ergänzt bei endgültigen Handlungen den Satz zur Folge', async () => {
    const user = userEvent.setup()
    const result = confirmDialog({
      title: 'Vorlage „Einladung“ löschen?',
      confirmLabel: 'Löschen',
      final: true,
    })
    const dialog = screen.getByRole('alertdialog')
    expect(dialog.textContent).toContain('Das lässt sich nicht rückgängig machen.')
    expect(dialog.getAttribute('aria-describedby')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Löschen' }))
    await expect(result).resolves.toBe(true)
  })

  it('wiederholt den Satz nicht, wenn der Text ihn schon enthält', async () => {
    const user = userEvent.setup()
    const result = confirmDialog({
      title: 'Würde löschen?',
      message: 'Alle Regentschaften werden gelöscht. Das lässt sich nicht rückgängig machen.',
      confirmLabel: 'Löschen',
      final: true,
    })
    expect(screen.queryByTestId('dialog-final')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await expect(result).resolves.toBe(false)
  })

  it('lässt den Satz weg, wenn es einen Rückweg gibt', async () => {
    const user = userEvent.setup()
    const result = confirmDialog({
      title: '„Satzung“ löschen?',
      message: 'Das Dokument kommt in den Papierkorb und bleibt dort 30 Tage.',
      confirmLabel: 'In den Papierkorb',
      final: false,
    })
    expect(screen.getByRole('alertdialog').textContent).not.toContain('rückgängig')
    await user.click(screen.getByRole('button', { name: 'Abbrechen' }))
    await expect(result).resolves.toBe(false)
  })

  it('kennzeichnet jede Rückfrage im Code als endgültig, mit Rückweg oder harmlos', () => {
    const all = confirmations()
    expect(all.length).toBeGreaterThan(150)
    const unmarked = all.filter((c) => !/\bfinal: /.test(c.body) && !/danger: false/.test(c.body))
    expect(unmarked.map((c) => c.where)).toEqual([])
  })

  it('fragt beim Löschen einer Terminkategorie nicht mehr, weil „Rückgängig“ sie zurückholt', () => {
    const page = readFileSync('src/pages/events/EventsPage.tsx', 'utf8')
    const at = page.indexOf('eventApi.removeCategory')
    expect(at).toBeGreaterThan(0)
    expect(page.slice(at - 400, at)).not.toContain('confirmDialog')
  })
})
