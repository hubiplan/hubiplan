import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { amount, ordersApi } from '../../api/orders.ts'
import type { CampaignDetail, CampaignList, PickMember } from '../../api/orders.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Loading, StatusMessage } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { formatDay, formatEuro } from '../../i18n/format.ts'
import { OrderForm, OrderLines } from './OrderForm.tsx'
import { limitText, priceText, stateLabel } from './format.ts'
import './orders.css'
import { CampaignEditor } from './CampaignEditor.tsx'

export function Campaign({
  base,
  orgId,
  id,
  list,
  onClose,
}: {
  base: string
  orgId: number
  id: number
  list: CampaignList
  onClose: () => Promise<void>
}) {
  const loaded = useLoad(() => ordersApi.get(base, id), [base, id])
  const [data, setData] = useState<CampaignDetail | null>(null)
  const [editing, setEditing] = useState(false)
  const [entering, setEntering] = useState(false)
  const [member, setMember] = useState<PickMember | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const c = data && data.id === id ? data : loaded.data
  if (loaded.error) return <p role="alert">{loaded.error}</p>
  if (!c) return <Loading />
  const prices = !c.club_pays
  const run = async (action: () => Promise<CampaignDetail | void>, done?: string) => {
    setBusy(true)
    setError('')
    setMessage(null)
    try {
      const next = await action()
      if (next) setData(next)
      if (done) setMessage(done)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (editing) {
    return (
      <CampaignEditor
        base={base}
        list={list}
        campaign={c}
        onDone={async (saved) => {
          setEditing(false)
          if (saved) setData(saved)
        }}
      />
    )
  }
  const withoutInvoice = c.orders.filter((o) => !o.invoice && (amount(o.total) ?? 0) > 0).length
  const editingOrder = member ? (c.orders.find((o) => o.membership === member.id) ?? null) : null
  return (
    <div className="orders stack">
      <PageHeader
        title={c.title}
        status={<span className="badge">{stateLabel(c.state)}</span>}
        onBack={onClose}
      />
      <p className="muted">
        {t('Bestellen bis {date}', { date: formatDay(c.deadline) })}
        {' · '}
        {c.unit ? t('nur {name}', { name: c.unit }) : t('alle Mitglieder')}
        {' · '}
        {tn(
          '{n} Bestellung von {m} möglichen',
          '{n} Bestellungen von {m} möglichen',
          c.orders.length,
          {
            m: c.audience,
          },
        )}
        {c.club_pays && ` · ${t('Der Verein bezahlt')}`}
      </p>
      {c.text && <p className="order-text">{c.text}</p>}
      {error && <Alert kind="error">{error}</Alert>}
      <StatusMessage message={message} />
      <div className="button-row">
        {c.can_edit && c.state === 'draft' && (
          <button
            type="button"
            className="button button-primary"
            disabled={busy}
            onClick={() =>
              run(
                () => ordersApi.publish(base, c.id, 'publish'),
                t('Freigegeben: Die Mitglieder können jetzt bestellen.'),
              )
            }
          >
            {t('Freigeben')}
          </button>
        )}
        {c.can_edit && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => setEditing(true)}
          >
            {t('Bearbeiten')}
          </button>
        )}
        {c.can_edit && c.state === 'open' && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(() => ordersApi.publish(base, c.id, 'close'), t('Bestellungen geschlossen.'))
            }
          >
            {t('Jetzt beenden')}
          </button>
        )}
        {c.can_edit && c.state === 'closed' && c.published_at && (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() =>
              run(() => ordersApi.publish(base, c.id, 'reopen'), t('Wieder geöffnet.'))
            }
          >
            {t('Wieder öffnen')}
          </button>
        )}
        <button
          type="button"
          className="button button-ghost"
          disabled={busy}
          onClick={() =>
            run(async () => saveBlob(await ordersApi.export(base, c.id), `bestellung-${c.id}.xlsx`))
          }
        >
          {t('Als Excel')}
        </button>
        {c.can_edit && (
          <button
            type="button"
            className="button button-danger"
            disabled={busy}
            onClick={async () => {
              const yes = await confirmDialog({
                final: true,
                title: t('Sammelbestellung löschen?'),
                message: t(
                  'Die Sammelbestellung und alle Bestellungen werden gelöscht. Angelegte Rechnungen bleiben in den Finanzen.',
                ),
                confirmLabel: t('Löschen'),
              })
              if (!yes) return
              await run(async () => {
                await ordersApi.remove(base, c.id)
                await onClose()
              })
            }}
          >
            {t('Löschen')}
          </button>
        )}
      </div>

      <section className="card stack">
        <h2>{t('Artikel')}</h2>
        <ul className="item-list">
          {c.articles.map((a) => (
            <li key={a.id} className="item-row">
              <div className="item-row-info">
                <strong>{a.name}</strong>
                {priceText(a) && <span className="muted"> · {priceText(a)}</span>}
                {a.variants.length > 0 && (
                  <div className="muted small">
                    {a.variant_label || t('Auswahl')}: {a.variants.join(', ')}
                  </div>
                )}
                {limitText(a) && <div className="muted small">{limitText(a)}</div>}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="card stack">
        <h2>{t('Summen für den Lieferanten')}</h2>
        {c.sums.every((s) => s.quantity === 0) ? (
          <p className="muted">{t('Noch keine Bestellungen.')}</p>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t('Artikel')}</th>
                  <th scope="col">{t('Auswahl')}</th>
                  <th scope="col">{t('Menge')}</th>
                  {prices && <th scope="col">{t('Betrag')}</th>}
                </tr>
              </thead>
              <tbody>
                {c.sums.flatMap((s) =>
                  s.variants
                    .filter((v) => v.quantity > 0)
                    .map((v, i) => (
                      <tr key={`${s.article}-${v.variant}`}>
                        <td>{i === 0 ? s.name : ''}</td>
                        <td>{v.variant || '–'}</td>
                        <td>{v.quantity}</td>
                        {prices && (
                          <td>
                            {i === 0 && s.amount
                              ? t('{x} gesamt ({n} Stück)', {
                                  x: formatEuro(amount(s.amount) ?? 0),
                                  n: s.quantity,
                                })
                              : ''}
                          </td>
                        )}
                      </tr>
                    )),
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card stack">
        <div className="card-head">
          <h2>{t('Bestellungen')}</h2>
          <div className="button-row">
            {c.can_edit && (
              <button
                type="button"
                className="button button-ghost"
                aria-expanded={entering}
                onClick={() => {
                  setEntering((v) => !v)
                  setMember(null)
                }}
              >
                {t('Bestellung eintragen')}
              </button>
            )}
            {c.can_invoice && withoutInvoice > 0 && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  const yes = await confirmDialog({
                    title: t('Rechnungen anlegen?'),
                    message: tn(
                      'Für {n} Bestellung ohne Rechnung entsteht eine Rechnung. Mitglieder mit Lastschriftmandat erscheinen im nächsten Lastschriftlauf, die übrigen überweisen.',
                      'Für {n} Bestellungen ohne Rechnung entsteht je eine Rechnung. Mitglieder mit Lastschriftmandat erscheinen im nächsten Lastschriftlauf, die übrigen überweisen.',
                      withoutInvoice,
                    ),
                    confirmLabel: t('Rechnungen anlegen'),
                    danger: false,
                  })
                  if (!yes) return
                  await run(async () => {
                    const next = await ordersApi.invoices(base, c.id, null)
                    setMessage(
                      tn('{n} Rechnung angelegt.', '{n} Rechnungen angelegt.', next.created ?? 0),
                    )
                    return next
                  })
                }}
              >
                {t('Rechnungen anlegen')}
              </button>
            )}
          </div>
        </div>
        {entering && (
          <div className="stack order-enter">
            <MemberPicker<PickMember>
              orgId={orgId}
              label={t('Mitglied')}
              value={member}
              onChange={setMember}
              search={(term) => ordersApi.members(base, c.id, term).then((r) => r.members)}
            />
            {member && (
              <OrderForm
                key={member.id}
                articles={c.articles}
                order={editingOrder}
                showPrices={prices}
                submitLabel={t('Bestellung speichern')}
                onSave={async (lines, note) => {
                  let ok = false
                  await run(async () => {
                    const next = await ordersApi.setOrder(base, c.id, member.id, lines, note)
                    ok = true
                    setEntering(false)
                    setMember(null)
                    return next
                  }, t('Bestellung gespeichert.'))
                  return ok
                }}
                onCancel={() => setMember(null)}
              />
            )}
          </div>
        )}
        {c.orders.length === 0 ? (
          <p className="muted">{t('Noch keine Bestellungen.')}</p>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t('Name')}</th>
                  <th scope="col">{t('Bestellt')}</th>
                  {prices && <th scope="col">{t('Summe')}</th>}
                  {prices && <th scope="col">{t('Rechnung')}</th>}
                  <th scope="col">{t('Ausgegeben')}</th>
                  {c.can_edit && <th scope="col">{t('Aktionen')}</th>}
                </tr>
              </thead>
              <tbody>
                {c.orders.map((o) => (
                  <tr key={o.id}>
                    <td>
                      {o.name}
                      {o.number && <span className="muted small"> · {o.number}</span>}
                      {o.note && <div className="muted small">{o.note}</div>}
                    </td>
                    <td>
                      <OrderLines order={o} showPrices={false} />
                    </td>
                    {prices && <td>{o.total ? formatEuro(amount(o.total) ?? 0) : '–'}</td>}
                    {prices && (
                      <td>
                        {o.invoice
                          ? `${o.invoice.number}${amount(o.invoice.outstanding) ? '' : ` · ${t('bezahlt')}`}`
                          : '–'}
                      </td>
                    )}
                    <td>
                      <Checkbox
                        label={t('ausgegeben')}
                        checked={o.handed_out}
                        disabled={!c.can_edit || busy}
                        onChange={(v) => run(() => ordersApi.handOut(base, c.id, o.id, v))}
                      />
                    </td>
                    {c.can_edit && (
                      <td className="actions">
                        <div className="button-row">
                          <button
                            type="button"
                            className="button button-ghost"
                            disabled={busy || !!o.invoice}
                            onClick={() => {
                              setEntering(true)
                              setMember({
                                id: o.membership!,
                                first_name: o.name ?? '',
                                last_name: '',
                                name: o.name ?? '',
                                number: o.number ?? '',
                              })
                            }}
                          >
                            {t('Ändern')}
                          </button>
                          <button
                            type="button"
                            className="button button-ghost"
                            disabled={busy || !!o.invoice}
                            onClick={async () => {
                              const yes = await confirmDialog({
                                final: true,
                                title: t('Bestellung löschen?'),
                                message: t('Die Bestellung von {name} wird gelöscht.', {
                                  name: o.name ?? '',
                                }),
                                confirmLabel: t('Löschen'),
                              })
                              if (yes) await run(() => ordersApi.removeOrder(base, c.id, o.id))
                            }}
                          >
                            {t('Löschen')}
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
