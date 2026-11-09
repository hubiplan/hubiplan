// Finanzen › Buchen › Anlagen: Anlagenverzeichnis mit Abschreibung (AfA).
// Die AfA erscheint nur hier und in der steuerlichen Auswertung, nie im Kassenbuch.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { euro, financeApi, parseAmount } from '../../api/finance.ts'
import type { AssetMethod, FixedAsset } from '../../api/finance.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useForm, useLoad } from '../../components/forms.ts'
import { Alert, Field, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Term, Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'

function methodOptions(): { value: AssetMethod; label: string }[] {
  return [
    { value: 'linear', label: t('linear über die Nutzungsdauer') },
    { value: 'gwg', label: t('geringwertig, sofort abschreiben (bis 800 € netto)') },
    { value: 'pool', label: t('Sammelposten über 5 Jahre (250 bis 1.000 € netto)') },
    { value: 'none', label: t('keine Abschreibung (nur Verzeichnis)') },
  ]
}

function disposalOptions(): { value: string; label: string }[] {
  return [
    { value: '', label: t('im Bestand') },
    { value: 'sold', label: t('verkauft') },
    { value: 'scrapped', label: t('verschrottet bzw. verloren') },
    { value: 'given', label: t('verschenkt') },
  ]
}

function AssetForm({
  asset,
  preset,
  taxAreas,
  materials,
  canEdit,
  onDone,
}: {
  asset: FixedAsset | null
  preset: Record<string, string>
  taxAreas: { value: string; label: string }[]
  materials: { id: number; name: string }[]
  canEdit: boolean
  onDone: () => void
}) {
  const org = useActiveOrg()
  const form = useForm({
    name: asset?.name ?? preset.name ?? '',
    acquired_on: asset?.acquired_on ?? preset.datum ?? '',
    cost: (asset?.cost ?? preset.betrag ?? '').replace('.', ','),
    net_cost: (asset?.net_cost ?? '').replace('.', ','),
    tax_area: asset?.tax_area ?? 'ideal',
    method: (asset?.method ?? 'linear') as string,
    useful_life: String(asset?.useful_life ?? 5),
    booking: String(asset?.booking ?? preset.buchung ?? ''),
    material_item: String(asset?.material_item ?? ''),
    disposal: (asset?.disposal ?? '') as string,
    disposed_on: asset?.disposed_on ?? '',
    note: asset?.note ?? '',
  })
  const { values: v, errors, set } = form

  async function save(e: FormEvent) {
    e.preventDefault()
    const payload = {
      name: v.name,
      acquired_on: v.acquired_on,
      cost: parseAmount(v.cost),
      net_cost: v.net_cost.trim() ? parseAmount(v.net_cost) : null,
      tax_area: v.tax_area,
      method: v.method,
      useful_life: Number(v.useful_life) || 1,
      booking: v.booking ? Number(v.booking) : null,
      material_item: v.material_item ? Number(v.material_item) : null,
      disposal: v.disposal,
      disposed_on: v.disposal ? v.disposed_on || null : null,
      note: v.note,
    }
    const saved = await form.submit(() =>
      asset
        ? financeApi.updateAsset(org.id, asset.id, payload)
        : financeApi.createAsset(org.id, payload),
    )
    if (saved) onDone()
  }

  return (
    <form className="card card-wide" onSubmit={(e) => void save(e)}>
      <h3>{asset ? asset.name : t('Neue Anlage')}</h3>
      <fieldset disabled={!canEdit || form.busy}>
        <div className="grid-2">
          <Field
            label={t('Bezeichnung')}
            required
            value={v.name}
            error={errors.name}
            placeholder={t('z. B. Festzelt 10 × 20 m')}
            onChange={(e) => set('name', e.target.value)}
          />
          <Field
            label={t('Anschaffungsdatum')}
            type="date"
            required
            value={v.acquired_on}
            error={errors.acquired_on}
            onChange={(e) => set('acquired_on', e.target.value)}
          />
          <Field
            label={t('Anschaffungskosten')}
            inputMode="decimal"
            required
            value={v.cost}
            error={errors.cost}
            hint={t('Ohne Vorsteuerabzug der Bruttobetrag')}
            onChange={(e) => set('cost', e.target.value)}
          />
          <Field
            label={t('Nettobetrag (optional)')}
            inputMode="decimal"
            value={v.net_cost}
            error={errors.net_cost}
            hint={t('Für die Grenzen 250, 800 und 1.000 €')}
            onChange={(e) => set('net_cost', e.target.value)}
          />
          <SelectField
            label={t('Steuerlicher Bereich')}
            value={v.tax_area}
            error={errors.tax_area}
            onChange={(e) => set('tax_area', e.target.value)}
          >
            {taxAreas.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </SelectField>
          <SelectField
            label={t('Abschreibung')}
            value={v.method}
            error={errors.method}
            onChange={(e) => set('method', e.target.value)}
          >
            {methodOptions().map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </SelectField>
          {v.method === 'linear' && (
            <Field
              label={t('Nutzungsdauer in Jahren')}
              type="number"
              min={1}
              max={50}
              value={v.useful_life}
              error={errors.useful_life}
              hint={t('Laut AfA-Tabelle, z. B. Büromöbel 13, Computer 1 Jahr')}
              onChange={(e) => set('useful_life', e.target.value)}
            />
          )}
          {materials.length > 0 && (
            <SelectField
              label={t('Gegenstand im Inventar (optional)')}
              value={v.material_item}
              error={errors.material_item}
              onChange={(e) => set('material_item', e.target.value)}
            >
              <option value="">{t('keiner')}</option>
              {materials.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </SelectField>
          )}
          <SelectField
            label={t('Abgang')}
            value={v.disposal}
            error={errors.disposal}
            onChange={(e) => set('disposal', e.target.value)}
          >
            {disposalOptions().map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </SelectField>
          {v.disposal && (
            <Field
              label={t('Abgangsdatum')}
              type="date"
              value={v.disposed_on}
              error={errors.disposed_on}
              onChange={(e) => set('disposed_on', e.target.value)}
            />
          )}
          <Field
            label={t('Notiz (optional)')}
            value={v.note}
            error={errors.note}
            onChange={(e) => set('note', e.target.value)}
          />
        </div>
        {asset?.booking_number && (
          <p className="muted small">
            {t('Ausgabe der Anschaffung: {n}', { n: asset.booking_number })}
          </p>
        )}
        {!asset && v.booking && (
          <p className="muted small">{t('Wird mit der Ausgabe aus dem Kassenbuch verknüpft.')}</p>
        )}
      </fieldset>
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        {canEdit && (
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {asset ? t('Speichern') : t('Anlegen')}
          </button>
        )}
        <button type="button" className="button button-ghost" onClick={onDone}>
          {canEdit ? t('Abbrechen') : t('Schließen')}
        </button>
      </div>
    </form>
  )
}

export function AssetsPage({ canEdit }: { canEdit: boolean }) {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const settings = useLoad(() => financeApi.settings(org.id), [org.id])
  const [year, setYear] = useState<number | null>(null)
  const current = year ?? settings.data?.current_year ?? null
  const register = useLoad(
    () => (current === null ? Promise.resolve(null) : financeApi.assets(org.id, current)),
    [org.id, current],
  )
  const materials = useLoad(() => financeApi.assetMaterials(org.id), [org.id])
  const preset = Object.fromEntries(params.entries())
  const [editing, setEditing] = useState<FixedAsset | 'new' | null>(
    preset.buchung && canEdit ? 'new' : null,
  )
  const [error, setError] = useState<string | null>(null)

  const loadError = settings.error ?? register.error
  if (loadError) return <Alert kind="error">{loadError}</Alert>
  if (!settings.data || !register.data) return <Loading />
  const data = register.data

  function done() {
    setEditing(null)
    if (params.toString()) setParams({}, { replace: true })
    register.reload()
  }

  async function remove(asset: FixedAsset) {
    const ok = await confirmDialog({
      title: t('Anlage löschen?'),
      message: t('„{name}“ wird aus dem Anlagenverzeichnis gelöscht. Buchungen bleiben.', {
        name: asset.name,
      }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    try {
      await financeApi.deleteAsset(org.id, asset.id)
      register.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="stack">
      <h2 className="section-heading">{t('Anlagenverzeichnis')}</h2>
      <Why k="asset_method" />
      <div className="card card-wide filters">
        <label>
          {t('Geschäftsjahr')}{' '}
          <select value={data.year} onChange={(e) => setYear(Number(e.target.value))}>
            {settings.data.years.map((y) => (
              <option key={y.year} value={y.year}>
                {y.label}
              </option>
            ))}
          </select>
        </label>
        <span className="push-right">
          {canEdit && (
            <button
              type="button"
              className="button button-primary"
              onClick={() => setEditing('new')}
            >
              {t('Anlage hinzufügen')}
            </button>
          )}{' '}
          <a className="button button-ghost" href={financeApi.assetsXlsxUrl(org.id, data.year)}>
            {t('Excel')}
          </a>
        </span>
      </div>
      <p className="muted small">
        {t(
          'Gegenstände ab {x} netto, die mehrere Jahre genutzt werden, z. B. Zelte, Kühlanhänger oder Möbel. Die Abschreibung erscheint nur hier und in der steuerlichen Auswertung, nie im Kassenbuch.',
          { x: euro(data.suggest_from) },
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {editing && (
        <AssetForm
          asset={editing === 'new' ? null : editing}
          preset={editing === 'new' ? preset : {}}
          taxAreas={settings.data.tax_areas}
          materials={materials.data ?? []}
          canEdit={canEdit}
          onDone={done}
        />
      )}
      <div className="card card-wide">
        {data.assets.length === 0 ? (
          <p className="muted">{t('Noch keine Anlagen erfasst.')}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t('Bezeichnung')}</th>
                <th>{t('Anschaffung')}</th>
                <th className="num">{t('Anschaffungskosten')}</th>
                <th>
                  <Term k="depreciation">{t('Abschreibung')}</Term>
                </th>
                <th className="num">{t('AfA {y}', { y: data.label })}</th>
                <th className="num">
                  <Term k="book_value">{t('Buchwert')}</Term> {t('am Jahresende')}
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.assets.map((a) => (
                <tr key={a.id}>
                  <td>
                    <button type="button" className="link-button" onClick={() => setEditing(a)}>
                      {a.name}
                    </button>
                    <div className="muted small">
                      {a.tax_area_label}
                      {a.disposal && ` · ${a.disposal_label} ${formatDate(a.disposed_on ?? '')}`}
                      {a.material_name && ` · ${a.material_name}`}
                    </div>
                  </td>
                  <td>
                    {formatDate(a.acquired_on)}
                    {a.booking_number && <div className="muted small">{a.booking_number}</div>}
                  </td>
                  <td className="num">{euro(a.cost)}</td>
                  <td>
                    {a.method_label}
                    {a.method === 'linear' && (
                      <div className="muted small">{t('{n} Jahre', { n: a.useful_life })}</div>
                    )}
                  </td>
                  <td className="num">{euro(a.values?.depreciation ?? '0')}</td>
                  <td className="num">{euro(a.values?.book_end ?? '0')}</td>
                  <td>
                    {canEdit && (
                      <button
                        type="button"
                        className="button button-ghost"
                        onClick={() => void remove(a)}
                      >
                        {t('Löschen')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              <tr>
                <th colSpan={4}>{t('Summe')}</th>
                <th className="num">{euro(data.totals.depreciation)}</th>
                <th className="num">{euro(data.totals.book_end)}</th>
                <th />
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
