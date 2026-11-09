import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it } from 'vitest'
import { ScoreFoldersPanel } from '../pages/music/ScoreFoldersPanel.tsx'
import { fakeApi } from './fakeApi.ts'

const base = '/api/orgs/1/music/'
const folder = {
  id: 3,
  name: 'Marschbuch',
  kind: 'marchbook',
  position: 0,
  departments: [7],
  note: '',
  active: true,
  items: [
    {
      id: 11,
      folder: 3,
      arrangement: 21,
      position: 1,
      number: '12',
      title: 'Florentiner Marsch',
      arrangement_name: 'Blasorchester',
    },
    {
      id: 12,
      folder: 3,
      arrangement: 22,
      position: 2,
      number: '27',
      title: 'Alte Kameraden',
      arrangement_name: 'Blasorchester',
    },
  ],
}

it('zeigt Mappen mit Nummern, ordnet um und fügt ein Stück hinzu', async () => {
  const calls = fakeApi({
    ['GET ' + base + 'score-folders/']: () => ({ status: 200, body: [folder] }),
    ['GET ' + base + 'score-folders/units/']: () => ({
      status: 200,
      body: [{ id: 7, name: 'Spielmannszug' }],
    }),
    ['POST ' + base + 'score-folders/3/reorder/']: () => ({ status: 200, body: folder }),
    ['POST ' + base + 'score-folder-items/']: () => ({ status: 201, body: {} }),
  })
  render(
    <ScoreFoldersPanel
      base={base}
      canEdit
      arrangements={[
        ['21', 'Florentiner Marsch · Blasorchester'],
        ['22', 'Alte Kameraden · Blasorchester'],
        ['23', 'Preußens Gloria · Blasorchester'],
      ]}
    />,
  )
  await screen.findByText('Marschbuch')
  expect(screen.getByText(/Spielmannszug/)).toBeInTheDocument()
  expect(screen.getByText(/2 Stücke/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Stücke zeigen' }))
  expect(screen.getByText('Nr. 27')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Alte Kameraden nach oben' }))
  const reorder = calls.find((c) => c.key === 'POST ' + base + 'score-folders/3/reorder/')
  expect(JSON.parse(String(reorder?.init?.body))).toEqual({ items: [12, 11] })
  // Schon enthaltene Arrangements stehen nicht mehr zur Auswahl
  const select = screen.getByRole('combobox', { name: 'Arrangement' })
  expect(select.querySelectorAll('option')).toHaveLength(2)
  await userEvent.selectOptions(select, '23')
  await userEvent.type(screen.getByRole('textbox', { name: 'Nummer (optional)' }), '5')
  await userEvent.click(screen.getByRole('button', { name: 'Stück hinzufügen' }))
  const added = calls.find((c) => c.key === 'POST ' + base + 'score-folder-items/')
  expect(JSON.parse(String(added?.init?.body))).toEqual({ folder: 3, arrangement: 23, number: '5' })
})
