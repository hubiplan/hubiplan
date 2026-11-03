import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TodoAttachments } from '../components/TodoAttachments.tsx'
import { fakeApi } from './fakeApi.ts'

describe('Aufgabenanhänge', () => {
  it('lädt mehrere Dateien mit fortgeschriebenen Versionen hoch', async () => {
    const versions: string[] = []
    fakeApi({
      'GET /api/orgs/7/todos/1/': () => ({ status: 200, body: { version: 3 } }),
      'POST /api/orgs/7/todos/1/attachments/': (init) => {
        const data = init?.body as FormData
        versions.push(String(data.get('version')))
        return { status: 201, body: { version: Number(data.get('version')) + 1 } }
      },
    })
    const saved = vi.fn()
    render(<TodoAttachments base="/api/orgs/7/todos/" id={1} writable onSaved={saved} />)
    await userEvent.click(screen.getByText('Anhänge'))
    await userEvent.upload(screen.getByLabelText('Dateien hochladen'), [
      new File(['%PDF-1.4'], 'eins.pdf', { type: 'application/pdf' }),
      new File(['%PDF-1.4'], 'zwei.pdf', { type: 'application/pdf' }),
    ])
    await waitFor(() => expect(saved).toHaveBeenCalledOnce())
    expect(versions).toEqual(['3', '4'])
  })

  it('zeigt ohne Dokumentrecht einen Platzhalter und für Leser keine Aktionen', async () => {
    fakeApi({
      'GET /api/orgs/7/todos/1/attachments/': () => ({
        status: 200,
        body: {
          items: [
            {
              id: 4,
              name: 'Dokument ohne Zugriff',
              available: false,
              size: null,
              deleted_at: null,
            },
          ],
          documents: [],
        },
      }),
    })
    render(<TodoAttachments base="/api/orgs/7/todos/" id={1} writable={false} onSaved={() => {}} />)
    await userEvent.click(screen.getByText('Anhänge'))
    expect(await screen.findByText('Dokument ohne Zugriff')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByText('Dateien hochladen')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Entfernen' })).not.toBeInTheDocument()
  })
})
