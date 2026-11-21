// Sammelbestellungen im Mitgliederbereich: offene zuerst, bis zur Frist bestellen und ändern.
import { useState } from 'react'
import { amount, portalOrdersApi, portalOrdersBase } from '../../api/orders.ts'
import type { MemberCampaign } from '../../api/orders.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, EmptyState, LoadError, Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { formatDay, formatEuro } from '../../i18n/format.ts'
import { OrderForm, OrderLines } from '../orders/OrderForm.tsx'
import '../orders/orders.css'

export function PortalOrders({ accessId }: { accessId: number }) {
  const base = portalOrdersBase(accessId)
  const { data, error, reload } = useLoad(() => portalOrdersApi.list(base), [base])
  const [notice, setNotice] = useState('')
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const open = data.campaigns.filter((c) => c.state === 'open')
  const closed = data.campaigns.filter((c) => c.state !== 'open')
  const done = async (text: string) => {
    setNotice(text)
    await reload()
  }
  return (
    <div className="stack">
      {notice && <Alert kind="success">{notice}</Alert>}
      {!data.campaigns.length && (
        <EmptyState title={t('Keine Bestellungen')}>
          {t('Gerade läuft keine Sammelbestellung für dich.')}
        </EmptyState>
      )}
      {open.map((c) => (
        <CampaignCard key={c.id} base={base} campaign={c} onDone={done} />
      ))}
      {closed.length > 0 && <h2>{t('Beendete Sammelbestellungen')}</h2>}
      {closed.map((c) => (
        <CampaignCard key={c.id} base={base} campaign={c} onDone={done} headingLevel={3} />
      ))}
    </div>
  )
}

function CampaignCard({
  base,
  campaign,
  onDone,
  headingLevel = 2,
}: {
  base: string
  campaign: MemberCampaign
  onDone: (notice: string) => Promise<void>
  headingLevel?: 2 | 3
}) {
  const [detail, setDetail] = useState<MemberCampaign | null>(null)
  const [failure, setFailure] = useState('')
  const [busy, setBusy] = useState(false)
  const Heading = headingLevel === 2 ? 'h2' : 'h3'
  const prices = !campaign.club_pays
  const order = campaign.order
  const openForm = async () => {
    setBusy(true)
    setFailure('')
    try {
      setDetail(await portalOrdersApi.get(base, campaign.id))
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack">
      <Heading>{campaign.title}</Heading>
      <p className="muted">
        {campaign.from}
        {' · '}
        {campaign.state === 'open'
          ? t('Bestellen bis {date}', { date: formatDay(campaign.deadline) })
          : t('Bestellfrist vorbei ({date})', { date: formatDay(campaign.deadline) })}
        {campaign.club_pays && ` · ${t('Der Verein bezahlt')}`}
      </p>
      {failure && <Alert kind="error">{failure}</Alert>}
      {order && !detail && (
        <div className="stack">
          <p>
            <strong>{t('Deine Bestellung')}</strong>
          </p>
          <OrderLines order={order} showPrices={prices} />
          {prices && order.total && (
            <p>{t('Summe: {x}', { x: formatEuro(amount(order.total) ?? 0) })}</p>
          )}
          {order.invoice && (
            <p className="muted small">
              {t('Rechnung {number}', { number: order.invoice.number })}
              {amount(order.invoice.outstanding) ? '' : ` · ${t('bezahlt')}`}
            </p>
          )}
          {order.handed_out && <p className="muted small">{t('Ausgegeben')}</p>}
        </div>
      )}
      {!order && campaign.state !== 'open' && (
        <p className="muted">{t('Du hast nichts bestellt.')}</p>
      )}
      {detail ? (
        <>
          {detail.text && <p className="order-text">{detail.text}</p>}
          {detail.can_order ? (
            <OrderForm
              articles={detail.articles ?? []}
              order={detail.order}
              showPrices={prices}
              submitLabel={detail.order ? t('Bestellung ändern') : t('Bestellen')}
              onSave={async (lines, note) => {
                setFailure('')
                try {
                  await portalOrdersApi.order(base, campaign.id, lines, note)
                  setDetail(null)
                  await onDone(t('Danke, deine Bestellung ist gespeichert.'))
                  return true
                } catch (err) {
                  setFailure(errorMessage(err))
                  return false
                }
              }}
              onWithdraw={async () => {
                const yes = await confirmDialog({
                  final: false,
                  title: t('Bestellung zurückziehen?'),
                  message: campaign.title,
                  confirmLabel: t('Bestellung zurückziehen'),
                })
                if (!yes) return
                try {
                  await portalOrdersApi.withdraw(base, campaign.id)
                  setDetail(null)
                  await onDone(t('Bestellung zurückgezogen.'))
                } catch (err) {
                  setFailure(errorMessage(err))
                }
              }}
              onCancel={() => setDetail(null)}
            />
          ) : (
            <p className="muted">
              {t('Die Bestellung lässt sich nicht mehr ändern. Bitte wende dich an den Vorstand.')}
            </p>
          )}
        </>
      ) : (
        campaign.state === 'open' && (
          <div className="button-row">
            <button
              className="button button-primary"
              type="button"
              disabled={busy}
              onClick={openForm}
            >
              {order ? t('Bestellung ansehen oder ändern') : t('Jetzt bestellen')}
            </button>
          </div>
        )
      )}
    </section>
  )
}
