// Sammelbestellungen in der Verwaltung: Artikel mit Größen, Frist, Summen für den Lieferanten,
// Rechnungen (freiwillig) und Ausgabe (Lückenliste 20.11.2026, B4).
import { useState } from 'react'
import type { FormEvent } from 'react'
import { saveBlob } from '../../api/client.ts'
import { PERM } from '../../api/orgs.ts'
import { amount, ordersApi } from '../../api/orders.ts'
import type {
  CampaignDetail,
  CampaignDraft,
  CampaignList,
  OrderArticle,
  PickMember,
} from '../../api/orders.ts'
import { EmptyList } from '../../components/EmptyList.tsx'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useRowSearch } from '../../components/RowSearch.tsx'
import { useRowSort } from '../../components/RowSort.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Loading, StatusMessage } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { formatDay, formatEuro } from '../../i18n/format.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { OrderForm, OrderLines } from './OrderForm.tsx'
import { limitText, priceText, stateLabel } from './format.ts'
import './orders.css'

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

interface ArticleRow {
  id?: number
  name: string
  text: string
  price: string
  variants: string
  variant_label: string
  max_per_member: string
  max_total: string
}

function toRow(a: OrderArticle): ArticleRow {
  return {
    id: a.id,
    name: a.name,
    text: a.text,
    price: a.price ?? '',
    variants: a.variants.join(', '),
    variant_label: a.variant_label,
    max_per_member: a.max_per_member ? String(a.max_per_member) : '',
    max_total: a.max_total ? String(a.max_total) : '',
  }
}

function fromRow(r: ArticleRow): OrderArticle {
  return {
    id: r.id,
    name: r.name.trim(),
    text: r.text.trim(),
    price: r.price.trim() ? r.price.trim().replace(',', '.') : null,
    variants: r.variants
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean),
    variant_label: r.variant_label.trim(),
    max_per_member: r.max_per_member ? Number(r.max_per_member) : null,
    max_total: r.max_total ? Number(r.max_total) : null,
  }
}

const EMPTY_ROW: ArticleRow = {
  name: '',
  text: '',
  price: '',
  variants: '',
  variant_label: '',
  max_per_member: '',
  max_total: '',
}

function inTwoWeeks() {
  const d = new Date()
  d.setDate(d.getDate() + 14)
  return d.toISOString().slice(0, 10)
}

function CampaignEditor({
  base,
  list,
  campaign,
  onDone,
}: {
  base: string
  list: CampaignList
  campaign: CampaignDetail | null
  onDone: (saved: CampaignDetail | null) => Promise<void>
}) {
  const [title, setTitle] = useState(campaign?.title ?? '')
  const [text, setText] = useState(campaign?.text ?? '')
  const [deadline, setDeadline] = useState(campaign?.deadline ?? inTwoWeeks())
  const [department, setDepartment] = useState<number | null>(campaign?.department ?? null)
  const [clubPays, setClubPays] = useState(campaign?.club_pays ?? false)
  const [category, setCategory] = useState<number | null>(campaign?.payment_category ?? null)
  const [push, setPush] = useState(campaign?.push ?? false)
  const [rows, setRows] = useState<ArticleRow[]>(
    campaign?.articles.length ? campaign.articles.map(toRow) : [{ ...EMPTY_ROW }],
  )
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const setRow = (index: number, patch: Partial<ArticleRow>) =>
    setRows((cur) => cur.map((r, i) => (i === index ? { ...r, ...patch } : r)))
  const hasOrders = !!campaign?.orders.length
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    const draft: CampaignDraft = {
      title,
      text,
      deadline,
      department,
      club_pays: clubPays,
      payment_category: category,
      push,
      articles: rows.filter((r) => r.name.trim()).map(fromRow),
    }
    try {
      const saved = campaign
        ? await ordersApi.update(base, campaign.id, { ...draft, version: campaign.version })
        : await ordersApi.create(base, draft)
      await onDone(saved)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="card stack" onSubmit={submit}>
      <h2>{campaign ? t('Sammelbestellung bearbeiten') : t('Neue Sammelbestellung')}</h2>
      <div className="grid-2">
        <label className="field">
          <span>{t('Titel')}</span>
          <input
            required
            maxLength={200}
            value={title}
            placeholder={t('z. B. Vereinskleidung 2027')}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t('Bestellen bis')}</span>
          <input
            type="date"
            required
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>{t('Beschreibung (optional)')}</span>
        <textarea
          rows={3}
          maxLength={4000}
          value={text}
          placeholder={t('z. B. Ausgabe beim Sommerfest, Lieferzeit etwa vier Wochen')}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      {list.departments.length > 0 && (
        <label className="field">
          <span>{t('Wer darf bestellen?')}</span>
          <select
            value={department ?? ''}
            disabled={hasOrders}
            onChange={(e) => setDepartment(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('alle Mitglieder')}</option>
            {list.departments.map((d) => (
              <option key={d.id} value={d.id}>
                {t('nur {name}', { name: d.name })}
              </option>
            ))}
          </select>
        </label>
      )}
      <Checkbox
        label={t('Der Verein bezahlt')}
        hint={t('Mitglieder sehen keine Preise, es gibt keine Rechnungen')}
        checked={clubPays}
        onChange={setClubPays}
      />
      {!clubPays && list.categories.length > 0 && (
        <label className="field">
          <span>{t('Kategorie für Rechnungen (optional)')}</span>
          <select
            value={category ?? ''}
            onChange={(e) => setCategory(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{t('wie in den Rechnungseinstellungen')}</option>
            {list.categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <Checkbox
        label={t('Beim Freigeben Push an die App senden')}
        hint={t('nur an Mitglieder mit App und Benachrichtigungen, keine E-Mail')}
        checked={push}
        onChange={setPush}
      />
      <h3>{t('Artikel')}</h3>
      {rows.map((row, index) => (
        <fieldset key={row.id ?? `neu-${index}`} className="order-article-edit stack">
          <legend>{row.name || t('Artikel {n}', { n: index + 1 })}</legend>
          <div className="grid-2">
            <label className="field">
              <span>{t('Name')}</span>
              <input
                maxLength={100}
                value={row.name}
                placeholder={t('z. B. Poloshirt')}
                onChange={(e) => setRow(index, { name: e.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('Preis in Euro (optional)')}</span>
              <input
                inputMode="decimal"
                value={row.price}
                placeholder={t('leer: ohne Preis')}
                onChange={(e) => setRow(index, { price: e.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('Größen oder Varianten (optional)')}</span>
              <input
                value={row.variants}
                placeholder={t('z. B. S, M, L, XL')}
                onChange={(e) => setRow(index, { variants: e.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('Überschrift der Auswahl')}</span>
              <input
                maxLength={40}
                value={row.variant_label}
                placeholder={t('z. B. Größe')}
                onChange={(e) => setRow(index, { variant_label: e.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('Höchstens je Mitglied (optional)')}</span>
              <input
                type="number"
                min={1}
                value={row.max_per_member}
                onChange={(e) => setRow(index, { max_per_member: e.target.value })}
              />
            </label>
            <label className="field">
              <span>{t('Höchstens insgesamt (optional)')}</span>
              <input
                type="number"
                min={1}
                value={row.max_total}
                onChange={(e) => setRow(index, { max_total: e.target.value })}
              />
            </label>
          </div>
          <label className="field">
            <span>{t('Hinweis (optional)')}</span>
            <input
              maxLength={300}
              value={row.text}
              placeholder={t('z. B. mit gesticktem Vereinswappen')}
              onChange={(e) => setRow(index, { text: e.target.value })}
            />
          </label>
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              onClick={() => setRows((cur) => cur.filter((_, i) => i !== index))}
            >
              {t('Artikel entfernen')}
            </button>
          </div>
        </fieldset>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() => setRows((cur) => [...cur, { ...EMPTY_ROW }])}
        >
          {t('Artikel hinzufügen')}
        </button>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button className="button button-primary" type="submit" disabled={busy}>
          {busy ? t('Wird gespeichert …') : t('Sammelbestellung speichern')}
        </button>
        <button className="button button-ghost" type="button" onClick={() => onDone(null)}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

// --- Einzelansicht ---

function Campaign({
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
