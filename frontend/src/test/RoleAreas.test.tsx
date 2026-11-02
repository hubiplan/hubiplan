import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { RoleForm, RoleTable } from '../components/RoleEditor.tsx'
import { levelOf, permissionAreas, withLevel } from '../components/roles.ts'
import type { RoleValues } from '../components/roles.ts'

const catalog = [
  {
    id: 'members',
    label: 'Mitglieder',
    permissions: [
      { code: 'members.view', label: 'Mitglieder lesen' },
      { code: 'members.edit', label: 'Mitglieder bearbeiten' },
    ],
  },
  {
    id: 'events',
    label: 'Termine',
    permissions: [{ code: 'events.manage', label: 'Termine verwalten' }],
  },
  { id: 'finance', label: 'Kasse', permissions: [{ code: 'finance.view', label: 'Kasse lesen' }] },
]

describe('Rechte in der Rollenliste', () => {
  it('fasst Rechte nach Bereichen zusammen', () => {
    expect(permissionAreas(['members.view', 'events.manage'], catalog)).toEqual([
      { label: 'Mitglieder', full: false, permissions: ['Mitglieder lesen'] },
      { label: 'Termine', full: true, permissions: ['Termine verwalten'] },
    ])
  })

  it('zeigt Bereiche als Kennzeichen, Einzelrechte aufklappbar', () => {
    render(
      <RoleTable
        roles={[
          {
            id: 1,
            name: 'Schriftführer',
            permissions: ['members.view', 'events.manage'],
            holders: 1,
          },
        ]}
        catalog={catalog}
      />,
    )
    const areas = screen.getByRole('list', { name: 'Bereiche' })
    expect(
      within(areas)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['Mitglieder (teilweise)', 'Termine'])
    expect(screen.getByText('Einzelne Rechte')).toBeInTheDocument()
    expect(screen.queryByText('Kasse')).not.toBeInTheDocument()
  })
})

// Bereiche mit Stufen (konzepte/berechtigungen.md)
const staged = [
  {
    id: 'members',
    kind: 'area' as const,
    label: 'Mitglieder',
    levels: [
      { code: 'members.view', level: 'view' as const, label: 'Mitglieder sehen' },
      { code: 'members.edit', level: 'edit' as const, label: 'Mitglieder ändern' },
    ],
    permissions: [],
  },
  {
    id: 'audit',
    kind: 'area' as const,
    label: 'Änderungsprotokoll',
    levels: [{ code: 'audit.view', level: 'view' as const, label: 'Protokoll sehen' }],
    permissions: [],
  },
  {
    id: 'extras',
    kind: 'extras' as const,
    label: 'Zusatzrechte',
    permissions: [
      { code: 'export.lists', label: 'Mitgliederlisten exportieren', needs: 'members.view' },
    ],
  },
]

describe('Rechte je Bereich: kein Zugriff, lesen, bearbeiten', () => {
  it('liest und setzt Stufen; Bearbeiten schließt Lesen ein', () => {
    const members = staged[0]
    expect(levelOf(['members.view'], members)).toBe('view')
    expect(levelOf(['members.view', 'members.edit'], members)).toBe('edit')
    expect(withLevel([], members, 'edit', staged).sort()).toEqual(['members.edit', 'members.view'])
    // Ohne Lesen fällt das abhängige Zusatzrecht weg
    expect(withLevel(['members.view', 'export.lists'], members, 'none', staged)).toEqual([])
  })

  it('zeigt die Stufe im Kennzeichen der Rollenliste', () => {
    expect(permissionAreas(['members.view', 'audit.view'], staged)).toEqual([
      { label: 'Mitglieder', full: false, permissions: ['lesen'] },
      { label: 'Änderungsprotokoll', full: true, permissions: ['lesen'] },
    ])
  })

  it('Maske: je Bereich drei Stufen, Zusatzrecht erst mit Lesen', async () => {
    const saved: Partial<RoleValues>[] = []
    render(
      <RoleForm
        role={null}
        catalog={staged}
        fields={[]}
        hasWebsite={false}
        onSave={async (v) => {
          saved.push(v)
        }}
        onDone={() => undefined}
        onCancel={() => undefined}
      />,
    )
    const user = userEvent.setup()
    expect(screen.getByRole('radio', { name: 'Mitglieder: kein Zugriff' })).toBeChecked()
    // Protokoll kennt nur Lesen
    expect(screen.queryByRole('radio', { name: 'Änderungsprotokoll: bearbeiten' })).toBeNull()
    expect(screen.getByRole('checkbox', { name: /Mitgliederlisten exportieren/ })).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: 'Mitglieder: bearbeiten' }))
    await user.click(screen.getByRole('checkbox', { name: /Mitgliederlisten exportieren/ }))
    await user.type(screen.getByLabelText(/Name/), 'Schriftführer')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(saved[0].permissions?.sort()).toEqual(['export.lists', 'members.edit', 'members.view'])
  })
})
