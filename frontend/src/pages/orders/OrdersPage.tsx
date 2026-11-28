// Sammelbestellungen in der Verwaltung: Artikel mit Größen, Frist, Summen für den Lieferanten,
// Rechnungen (freiwillig) und Ausgabe (Lückenliste 20.11.2026, B4).
import { useState } from 'react'
import { PERM } from '../../api/orgs.ts'
import { ordersApi } from '../../api/orders.ts'
import { EmptyList } from '../../components/EmptyList.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { useLoad } from '../../components/forms.ts'
import { Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { formatDay } from '../../i18n/format.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { stateLabel } from './format.ts'
import './orders.css'
import { Campaign } from './Campaign.tsx'
import { CampaignEditor } from './CampaignEditor.tsx'

export function OrdersPage() {
  const { active } = useOrg()
  const permissions = active?.permissions ?? []
  if (
    !active ||
    !active.modules.includes('orders') ||
    !(permissions.includes(PERM.ordersView) || permissions.includes(PERM.ordersEdit))
  ) {
    return <NoAccessPage reason="right" />
  }
  const base = `/api/orgs/${active.id}/orders/`
  return <Campaigns key={base} base={base} orgId={active.id} />
}

function Campaigns({ base, orgId }: { base: string; orgId: number }) {
  const detail = useDetailParam('bestellung')
  const list = useLoad(() => ordersApi.list(base), [base])
  const [creating, setCreating] = useState(false)
  const search = useRowSearch(list.data?.campaigns ?? [], (c) => c.title, t('Sammelbestellungen'))
  const sorting = useRowSort(search.shown, {
    title: (c) => c.title,
    deadline: (c) => c.deadline,
    orders: (c) => c.orders,
    state: (c) => c.state,
  })
  const canEdit = !!list.data?.can_edit
  if (detail.value && list.data) {
    return (
      <Campaign
        base={base}
        orgId={orgId}
        id={Number(detail.value)}
        list={list.data}
        onClose={async () => {
          detail.close()
          await list.reload()
        }}
      />
    )
  }
  return (
    <div className="orders stack">
      <PageHeader
        subtitle={t(
          'Sammelbestellungen wie Vereinskleidung, Festschrift oder Uniformteile, auch reine Größenabfragen. Mitglieder bestellen bis zur Frist im Mitgliederbereich oder in der App.',
        )}
        primary={
          canEdit && !creating
            ? { label: t('Neue Sammelbestellung'), onClick: () => setCreating(true) }
            : null
        }
      />
      {creating && list.data && (
        <CampaignEditor
          base={base}
          list={list.data}
          campaign={null}
          onDone={async (saved) => {
            setCreating(false)
            if (saved) {
              await list.reload()
              detail.open(String(saved.id))
            }
          }}
        />
      )}
      {list.error && <p role="alert">{list.error}</p>}
      {!list.data && !list.error && <Loading />}
      {search.field}
      {list.data && !list.data.campaigns.length
        ? !creating && (
            <EmptyList
              title={t('Noch keine Sammelbestellung.')}
              canAdd={canEdit}
              action={{ label: t('Neue Sammelbestellung'), onClick: () => setCreating(true) }}
            >
              {t(
                'Lege Artikel mit Größen und auf Wunsch einem Preis an. Ohne Preis ist es eine reine Abfrage, etwa der Größen für neue Jacken.',
              )}
            </EmptyList>
          )
        : sorting.rows.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  {sorting.head('title', t('Sammelbestellung'))}
                  {sorting.head('deadline', t('Bestellen bis'))}
                  {sorting.head('orders', t('Bestellungen'))}
                  {sorting.head('state', t('Stand'))}
                </tr>
              </thead>
              <tbody>
                {sorting.rows.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => detail.open(String(c.id))}
                      >
                        {c.title}
                      </button>
                      {c.unit && <span className="muted small"> · {c.unit}</span>}
                    </td>
                    <td>{formatDay(c.deadline)}</td>
                    <td>{c.orders}</td>
                    <td>
                      <span className="badge">{stateLabel(c.state)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
    </div>
  )
}

// --- Anlegen und Bearbeiten ---
