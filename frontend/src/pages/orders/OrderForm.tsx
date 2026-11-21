// Bestellung eines Mitglieds: je Artikel die Menge, bei Größen oder Varianten je Auswahl.
// Gleich im Mitgliederbereich und beim Eintragen durch die Verwaltung.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { amount } from '../../api/orders.ts'
import type { LineInput, MemberOrder, OrderArticle } from '../../api/orders.ts'
import { t } from '../../i18n/index.ts'
import { formatEuro } from '../../i18n/format.ts'
import { limitText, priceText } from './format.ts'

const key = (article: number, variant: string) => `${article}|${variant}`

function initial(order: MemberOrder | null): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of order?.lines ?? [])
    out[key(line.article, line.variant)] = String(line.quantity)
  return out
}

export function OrderForm({
  articles,
  order,
  showPrices,
  submitLabel,
  onSave,
  onWithdraw,
  onCancel,
}: {
  articles: OrderArticle[]
  order: MemberOrder | null
  showPrices: boolean
  submitLabel: string
  onSave: (lines: LineInput[], note: string) => Promise<boolean>
  onWithdraw?: () => Promise<void>
  onCancel?: () => void
}) {
  const [values, setValues] = useState<Record<string, string>>(() => initial(order))
  const [note, setNote] = useState(order?.note ?? '')
  const [busy, setBusy] = useState(false)
  const set = (k: string, v: string) => setValues((cur) => ({ ...cur, [k]: v }))
  const lines: LineInput[] = []
  let total = 0
  for (const a of articles) {
    for (const variant of a.variants.length ? a.variants : ['']) {
      const quantity = Number(values[key(a.id!, variant)] || 0)
      if (quantity > 0) {
        lines.push({ article: a.id!, variant, quantity })
        total += (amount(a.price) ?? 0) * quantity
      }
    }
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await onSave(lines, note)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="stack order-form" onSubmit={submit}>
      {articles.map((a) => (
        <fieldset key={a.id} className="order-article">
          <legend>
            {a.name}
            {showPrices && priceText(a) && <span className="muted"> · {priceText(a)}</span>}
          </legend>
          {a.text && <p className="muted small">{a.text}</p>}
          {limitText(a) && <p className="muted small">{limitText(a)}</p>}
          <div className="order-variants">
            {(a.variants.length ? a.variants : ['']).map((variant) => (
              <label key={variant} className="field order-quantity">
                <span>{variant || t('Menge')}</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  max={99}
                  value={values[key(a.id!, variant)] ?? ''}
                  placeholder="0"
                  aria-label={
                    variant
                      ? t('{name}, {label} {value}: Menge', {
                          name: a.name,
                          label: a.variant_label || t('Auswahl'),
                          value: variant,
                        })
                      : t('{name}: Menge', { name: a.name })
                  }
                  onChange={(e) => set(key(a.id!, variant), e.target.value)}
                />
              </label>
            ))}
          </div>
          {a.variants.length > 0 && a.variant_label && (
            <p className="muted small">{t('Auswahl: {label}', { label: a.variant_label })}</p>
          )}
        </fieldset>
      ))}
      <label className="field">
        <span>{t('Bemerkung (optional)')}</span>
        <textarea
          rows={2}
          maxLength={500}
          value={note}
          placeholder={t('z. B. Name zum Besticken')}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {showPrices && total > 0 && (
        <p>
          <strong>{t('Summe: {x}', { x: formatEuro(total) })}</strong>
        </p>
      )}
      <div className="button-row">
        <button className="button button-primary" type="submit" disabled={busy || !lines.length}>
          {busy ? t('Wird gespeichert …') : submitLabel}
        </button>
        {onWithdraw && order && (
          <button
            className="button button-ghost"
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              try {
                await onWithdraw()
              } finally {
                setBusy(false)
              }
            }}
          >
            {t('Bestellung zurückziehen')}
          </button>
        )}
        {onCancel && (
          <button className="button button-ghost" type="button" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}

/** Bestellte Positionen als kurze Liste */
export function OrderLines({ order, showPrices }: { order: MemberOrder; showPrices: boolean }) {
  return (
    <ul className="order-lines">
      {order.lines.map((line) => (
        <li key={`${line.article}-${line.variant}`}>
          {line.quantity} × {line.name}
          {line.variant && ` (${line.variant})`}
          {showPrices && line.amount && (
            <span className="muted"> · {formatEuro(amount(line.amount) ?? 0)}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
