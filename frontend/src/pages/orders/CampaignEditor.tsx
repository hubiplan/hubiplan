import { useState } from 'react'
import type { FormEvent } from 'react'
import { ordersApi } from '../../api/orders.ts'
import type { CampaignDetail, CampaignDraft, CampaignList, OrderArticle } from '../../api/orders.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import './orders.css'

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

export function CampaignEditor({
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
