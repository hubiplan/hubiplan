import type { ReactNode } from 'react'
import type { HomeSectionData } from '../../api/website.ts'
import { Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

/** Tabelle: Spaltenköpfe und Zeilen mit fester Spaltenzahl (1–6) */
export function TableField({
  value,
  setData,
  titleField,
}: {
  value: HomeSectionData
  setData: (patch: Partial<HomeSectionData>) => void
  titleField: ReactNode
}) {
  const head = value.head?.length ? value.head : ['']
  const rows = value.rows ?? []
  const width = head.length
  const fit = (r: string[]) => Array.from({ length: width }, (_, c) => r[c] ?? '')
  const setWidth = (n: number) =>
    setData({
      head: Array.from({ length: n }, (_, c) => head[c] ?? ''),
      rows: rows.map((r) => Array.from({ length: n }, (_, c) => r[c] ?? '')),
    })
  return (
    <>
      {titleField}
      <SelectField
        label={t('Spalten')}
        value={width}
        onChange={(e) => setWidth(Number(e.target.value))}
      >
        {[1, 2, 3, 4, 5, 6].map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </SelectField>
      <fieldset className="home-item">
        <legend>{t('Kopfzeile')}</legend>
        {head.map((h, c) => (
          <Field
            key={c}
            label={t('Spalte {n}', { n: c + 1 })}
            value={h}
            maxLength={60}
            onChange={(e) => setData({ head: head.map((x, j) => (j === c ? e.target.value : x)) })}
          />
        ))}
      </fieldset>
      {rows.map((r, i) => (
        <fieldset key={i} className="home-item">
          <legend>{t('Zeile {n}', { n: i + 1 })}</legend>
          {fit(r).map((cell, c) => (
            <Field
              key={c}
              label={head[c] || t('Spalte {n}', { n: c + 1 })}
              value={cell}
              maxLength={120}
              onChange={(e) =>
                setData({
                  rows: rows.map((x, j) =>
                    j === i ? fit(x).map((y, k) => (k === c ? e.target.value : y)) : x,
                  ),
                })
              }
            />
          ))}
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setData({ rows: rows.filter((_, j) => j !== i) })}
          >
            {t('Zeile entfernen')}
          </button>
        </fieldset>
      ))}
      {rows.length < 40 && (
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setData({ rows: [...rows, fit([])] })}
          >
            {t('Zeile hinzufügen')}
          </button>
        </div>
      )}
      <Field
        label={t('Text darunter (optional)')}
        value={value.text ?? ''}
        maxLength={500}
        onChange={(e) => setData({ text: e.target.value })}
      />
    </>
  )
}
