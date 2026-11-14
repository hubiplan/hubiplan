import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { EventDetail } from '../api/events.ts'
import { EventDocumentLink } from '../components/calendar/EventDocumentLink.tsx'
import { fakeApi } from './fakeApi.ts'

const base = '/api/orgs/7/'
const event = { id: 4, attachments: [] } as unknown as EventDetail

describe('Dokument aus der Ablage an einen Termin knüpfen', () => {
  it('lädt die Auswahl erst auf Wunsch, warnt bei engerem Ordner und verknüpft', async () => {
    const linked = { ...event, attachments: [{ id: 9, kind: 'document', name: 'Ablaufplan' }] }
    const calls = fakeApi({
      [`GET ${base}events/4/attachments/`]: () => ({
        status: 200,
        body: {
          documents: [
            {
              id: 3,
              title: 'Ablaufplan',
              folder: 'Planung',
              folder_visibility: 'nur Vorstand',
              narrower: true,
            },
            {
              id: 5,
              title: 'Formular',
              folder: 'Formulare',
              folder_visibility: 'alle Mitglieder',
              narrower: false,
            },
          ],
        },
      }),
      [`POST ${base}events/4/attachments/`]: () => ({ status: 201, body: linked }),
    })
    const onChanged = vi.fn()
    render(<EventDocumentLink base={base} event={event} disabled={false} onChanged={onChanged} />)
    expect(calls.some((c) => c.key.startsWith('GET'))).toBe(false)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Dokument aus der Ablage verknüpfen' }))
    const select = await screen.findByLabelText('Dokument aus der Ablage')
    expect(screen.getByRole('button', { name: 'Verknüpfen' })).toBeDisabled()
    await user.selectOptions(select, '5')
    expect(screen.queryByText(/enger sichtbar/)).not.toBeInTheDocument()
    await user.selectOptions(select, '3')
    expect(
      screen.getByText(/Der Ordner „Planung“ ist enger sichtbar \(nur Vorstand\)/),
    ).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Verknüpfen' }))
    const post = calls.find((c) => c.key.startsWith('POST'))
    expect(JSON.parse(String(post?.init?.body))).toEqual({ document: 3 })
    expect(onChanged).toHaveBeenCalledWith(linked)
    expect(
      await screen.findByRole('button', { name: 'Dokument aus der Ablage verknüpfen' }),
    ).toBeVisible()
  })

  it('sagt, wenn nichts zu verknüpfen ist', async () => {
    fakeApi({
      [`GET ${base}events/4/attachments/`]: () => ({ status: 200, body: { documents: [] } }),
    })
    render(<EventDocumentLink base={base} event={event} disabled={false} onChanged={vi.fn()} />)
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: 'Dokument aus der Ablage verknüpfen' }))
    expect(await screen.findByText(/kein weiteres Dokument/)).toBeVisible()
  })
})
