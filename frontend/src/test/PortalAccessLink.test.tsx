import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { PortalPage } from '../pages/portal/PortalPage.tsx'

const scope = vi.hoisted(() => ({
  activePortal: { id: 9 },
  portal: [{ id: 9 }, { id: 12 }],
  select: vi.fn(),
}))
vi.mock('../org/OrgContext.tsx', () => ({ useOrg: () => scope }))
afterEach(() => scope.select.mockClear())
it('öffnet keinen nicht verfügbaren Zugang und bietet einen sicheren Rückweg', () => {
  render(
    <MemoryRouter initialEntries={['/mein-bereich/rundschreiben?zugang=18&schreiben=17']}>
      <PortalPage />
    </MemoryRouter>,
  )
  expect(screen.getByRole('alert')).toHaveTextContent(
    'Dieser Mitgliederzugang steht deinem Konto nicht zur Verfügung.',
  )
  expect(screen.getByRole('link', { name: 'Zu meinem Bereich' })).toHaveAttribute(
    'href',
    '/mein-bereich',
  )
  expect(scope.select).not.toHaveBeenCalled()
})
it('wählt den im Link genannten eigenen Zugang, bevor es einen Inhalt lädt', async () => {
  render(
    <MemoryRouter initialEntries={['/mein-bereich/rundschreiben?zugang=12&schreiben=17']}>
      <PortalPage />
    </MemoryRouter>,
  )
  expect(screen.getByRole('status')).toHaveTextContent('Mitgliederzugang wird geöffnet …')
  await waitFor(() => expect(scope.select).toHaveBeenCalledWith('p:12'))
  expect(screen.queryByRole('heading', { name: 'Mitteilungen' })).not.toBeInTheDocument()
})
