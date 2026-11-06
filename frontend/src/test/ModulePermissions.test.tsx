import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { CatalogModule } from '../api/orgs.ts'
import { RoleForm, PermissionSummary } from '../components/RoleEditor.tsx'
import type { RoleValues } from '../components/roles.ts'

const members: CatalogModule = {
  id: 'members',
  kind: 'area',
  module: 'members',
  label: 'Mitglieder',
  levels: [
    { code: 'members.view', level: 'view', label: 'Mitglieder sehen' },
    { code: 'members.edit', level: 'edit', label: 'Mitglieder ändern' },
  ],
  permissions: [],
}
const music: CatalogModule = {
  id: 'music',
  kind: 'area',
  module: 'music',
  label: 'Musik',
  levels: [
    { code: 'music.view', level: 'view', label: 'Musiker lesen' },
    { code: 'music.edit', level: 'edit', label: 'Musiker bearbeiten' },
  ],
  permissions: [],
}

describe('Modulfreigaben in Rollen', () => {
  it('blendet ruhende Rechte aus und erhält sie bei alles entfernen und erneutem Freischalten', async () => {
    const saved: Partial<RoleValues>[] = []
    const props = {
      role: {
        id: 1,
        name: 'Leitung',
        holders: 1,
        permissions: ['members.view', 'music.edit', 'music.view'],
      },
      fields: [],
      hasWebsite: false,
      onSave: async (values: Partial<RoleValues>) => {
        saved.push(values)
      },
      onDone: () => undefined,
      onCancel: () => undefined,
    }
    const view = render(<RoleForm {...props} catalog={[members]} />)
    expect(screen.queryByText('Musik')).not.toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'alles entfernen' }))
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    expect(saved[0].permissions).toEqual(['music.edit', 'music.view'])
    view.rerender(<RoleForm {...props} catalog={[members, music]} />)
    expect(screen.getByRole('radio', { name: 'Musik: bearbeiten' })).toBeChecked()
    view.rerender(<RoleForm {...props} catalog={[members]} />)
    expect(screen.queryByRole('radio', { name: 'Musik: bearbeiten' })).not.toBeInTheDocument()
  })

  it('zählt verborgene Rechte nicht und zeigt keine leere Rechteübersicht', () => {
    const view = render(<PermissionSummary codes={['music.edit']} catalog={[members]} />)
    expect(screen.getByText('keine')).toBeInTheDocument()
    expect(screen.queryByText('Einzelne Rechte')).not.toBeInTheDocument()
    view.rerender(
      <RoleForm
        role={{ id: 1, name: 'Leitung', holders: 0, permissions: ['music.edit'] }}
        catalog={[members]}
        fields={[]}
        hasWebsite={false}
        permissionsOptional
        onSave={async () => undefined}
        onDone={() => undefined}
        onCancel={() => undefined}
      />,
    )
    expect(screen.queryByText(/gewählt/)).not.toBeInTheDocument()
    expect(screen.getByText('Rechte (optional)').closest('details')).not.toHaveAttribute('open')
  })
})
