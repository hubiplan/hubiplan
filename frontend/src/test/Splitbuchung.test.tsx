import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Booking, Category } from '../api/finance.ts'
import { SplitEditor } from '../pages/finance/SplitEditor.tsx'
import { fakeApi } from './fakeApi.ts'

const cat = (id: number, name: string, tax_area: string): Category =>
  ({
    id,
    name,
    kind: 'both',
    kind_label: 'Einnahmen und Ausgaben',
    tax_area,
    tax_area_label: '',
    donations: false,
  }) as Category

const categories = [cat(1, 'Getränke', 'business'), cat(2, 'Eintritt', 'purpose')]
const booking = {
  id: 5,
  display_number: '2026-0005',
  amount: '1000.00',
  category: 1,
  project: null,
  kind: 'income',
} as unknown as Booking

describe('Splitbuchung', () => {
  it('teilt erst auf, wenn die Teile den Betrag ergeben', async () => {
    const calls = fakeApi({
      'POST /api/orgs/7/finance/bookings/5/split/': () => ({
        status: 201,
        body: [{ ...booking, amount: '700.00' }],
      }),
    })
    const done = vi.fn()
    render(
      <SplitEditor
        orgId={7}
        booking={booking}
        categories={categories}
        projects={[]}
        onDone={done}
        onCancel={() => {}}
      />,
    )
    const user = userEvent.setup()
    const submit = screen.getByRole('button', { name: 'Aufteilen' })
    // Erster Teil hat den ganzen Betrag, der zweite ist leer
    await user.clear(screen.getByLabelText('Betrag von Teil 1'))
    await user.type(screen.getByLabelText('Betrag von Teil 1'), '700')
    expect(screen.getByTestId('split-rest')).toHaveTextContent('300,00')
    expect(submit).toBeDisabled()
    await user.selectOptions(screen.getByLabelText('Kategorie von Teil 2'), '2')
    await user.type(screen.getByLabelText('Betrag von Teil 2'), '300')
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(done).toHaveBeenCalled()
    const post = calls.find((c) => c.key.startsWith('POST'))
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      parts: [
        { category: 1, amount: '700', project: null, text: '' },
        { category: 2, amount: '300', project: null, text: '' },
      ],
    })
  })
})
