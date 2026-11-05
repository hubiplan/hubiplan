import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { CatalogueImportPanel } from '../pages/music/CatalogueImportPanel.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({ useActiveOrg: () => ({ id: 7 }) }))

it('requires a successful preview before sending a protected catalogue import', async () => {
  const url = '/api/orgs/7/music/catalogue-import/'
  const calls = fakeApi({
    [`POST ${url}`]: () => ({
      status: 200,
      body: {
        valid: true,
        errors: [],
        counts: { pieces: 1, arrangements: 1, parts: 1 },
        skipped: 0,
        digest: 'sample-digest',
        preview: 'signed-sample',
      },
    }),
  })
  const saved = vi.fn(async () => {})
  render(<CatalogueImportPanel onSaved={saved} />)
  expect(
    screen.queryByRole('button', { name: 'Geprüften Notenkatalog importieren' }),
  ).not.toBeInTheDocument()
  await userEvent.upload(
    screen.getByLabelText('CSV-Datei für den Notenkatalog'),
    new File(['title;arrangement\nMuster;Fassung'], 'noten.csv', { type: 'text/csv' }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Importvorschau erstellen' }))
  await userEvent.click(
    await screen.findByRole('button', { name: 'Geprüften Notenkatalog importieren' }),
  )
  await screen.findByText('Notenkatalog wurde importiert.')
  const request = calls.filter((x) => x.key.startsWith('POST'))[1]
  const data = request.init?.body as FormData
  expect(data.get('digest')).toBe('sample-digest')
  expect(data.get('preview')).toBe('signed-sample')
  expect(new Headers(request.init?.headers).get('Idempotency-Key')).toBeTruthy()
  expect(saved).toHaveBeenCalledOnce()
})

it('shows preview errors and does not offer to import invalid rows', async () => {
  fakeApi({
    'POST /api/orgs/7/music/catalogue-import/': () => ({
      status: 200,
      body: { valid: false, errors: ['Musterfehler in Zeile 2'], counts: {}, skipped: 0 },
    }),
  })
  render(<CatalogueImportPanel onSaved={async () => {}} />)
  await userEvent.upload(
    screen.getByLabelText('CSV-Datei für den Notenkatalog'),
    new File(['ungueltig'], 'noten.csv', { type: 'text/csv' }),
  )
  await userEvent.click(screen.getByRole('button', { name: 'Importvorschau erstellen' }))
  await screen.findByText('Musterfehler in Zeile 2')
  expect(
    screen.queryByRole('button', { name: 'Geprüften Notenkatalog importieren' }),
  ).not.toBeInTheDocument()
})
