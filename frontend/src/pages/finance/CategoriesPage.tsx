import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client.ts'
import { financeApi } from '../../api/finance.ts'
import type { Category, CategoryUsage } from '../../api/finance.ts'
import { PERM } from '../../api/orgs.ts'
import { errorMessage, useAutoSave, useForm } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SaveStatus, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { useFinanceCategories, useFinanceSettings } from '../../components/masterData.ts'
import { CategoryTemplates } from './CategoryTemplates.tsx'

const CATEGORY_KIND = {
  both: t('Einnahmen und Ausgaben'),
  income: t('nur Einnahmen'),
  expense: t('nur Ausgaben'),
}

export function CategoriesPage() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.financeEdit)
  const { data, error, reload } = useFinanceCategories(org.id)
  const settings = useFinanceSettings(org.id)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [removing, setRemoving] = useState<{ category: Category; usage: CategoryUsage } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null)
  const form = useForm({ name: '', kind: 'both', tax_area: '' })

  if (error ?? settings.error) return <Alert kind="error">{error ?? settings.error}</Alert>
  if (!data || !settings.data) return <Loading />
  const areas = settings.data.tax_areas_enabled ? settings.data.tax_areas : []
  const datevOn = !!settings.data.datev_enabled
  const artistsOn = org.modules.includes('tax')
  // Umsatzsteuer-Vorgabe je Kategorie (S2): mit Modul Steuern bei Steuerpflicht
  const vatOn = artistsOn && (!!settings.data.vat_registered || data.some((c) => !!c.vat_rate))
  const current = data.filter((c) => c.is_active)
  const archived = data.filter((c) => !c.is_active)

  async function run(action: () => Promise<unknown>, success?: string) {
    setMessage(null)
    setBusy(true)
    try {
      await action()
      setRemoving(null)
      setRenaming(null)
      if (success) setMessage({ kind: 'success', text: success })
      await reload()
    } catch (err) {
      const text =
        err instanceof ApiError ? (Object.values(err.fieldErrors)[0] ?? err.message) : null
      setMessage({ kind: 'error', text: text ?? errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function askRemove(category: Category) {
    setMessage(null)
    try {
      setRemoving({ category, usage: await financeApi.categoryUsage(org.id, category.id) })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  function confirmRemove() {
    if (!removing) return
    const { category, usage } = removing
    if (usage.deletable) {
      void run(
        () => financeApi.deleteCategory(org.id, category.id),
        t('„{name}“ wurde gelöscht.', { name: category.name }),
      )
    } else {
      void run(
        () => financeApi.archiveCategory(org.id, category.id),
        t('„{name}“ wurde archiviert.', { name: category.name }),
      )
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault()
    const ok = await form.submit(
      () => financeApi.createCategory(org.id, form.values as Partial<Category>),
      t('Kategorie angelegt.'),
    )
    if (ok) {
      form.setValues({ name: '', kind: form.values.kind, tax_area: form.values.tax_area })
      await reload()
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Kategorien')}</h2>
      <p className="muted small">
        {t(
          'Kategorien ordnen Einnahmen und Ausgaben, zum Beispiel Beiträge, Sommerfest, Getränke oder Saalmiete.',
        )}
        {areas.length > 0 && t(' Jede Kategorie gehört zu einem steuerlichen Bereich.')}
      </p>
      {canEdit && org.modules.includes('tax') && (
        <>
          <Checkbox
            label={t(
              'Kategorien den vier steuerlichen Bereichen zuordnen (ideeller Bereich, Vermögensverwaltung, Zweckbetrieb, wirtschaftlicher Geschäftsbetrieb)',
            )}
            checked={settings.data.tax_areas_enabled}
            onChange={(on) =>
              void run(async () => {
                settings.setData(await financeApi.updateSettings(org.id, { tax_areas_enabled: on }))
              })
            }
          />
          <p className="muted small">
            {t(
              'Ob die Kasse so unterteilt werden muss, entscheidet ihr selbst, zum Beispiel mit eurem Steuerberater. Name und Bereich einer Kategorie werden beim Jahresabschluss festgehalten: Spätere Änderungen gelten nur für noch offene Geschäftsjahre.',
            )}
          </p>
          <Why k="tax_areas" />
        </>
      )}
      {canEdit && <CategoryTemplates onApplied={reload} startOpen={data.length === 0} />}
      {removing && (
        <div className="subcard" role="dialog" aria-label={t('Kategorie entfernen')}>
          {removing.usage.deletable ? (
            <p>
              {t('„{name}“ wird nirgends verwendet und wird', { name: removing.category.name })}{' '}
              <strong>{t('gelöscht')}</strong>.
            </p>
          ) : (
            <>
              <p>
                {t('„{name}“ wird noch verwendet und wird deshalb', {
                  name: removing.category.name,
                })}{' '}
                <strong>{t('archiviert')}</strong> {t('statt gelöscht:')}
              </p>
              <ul>
                {removing.usage.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <p className="muted small">
                {t(
                  'Archivierte Kategorien stehen für neue Buchungen nicht mehr zur Auswahl. Bestehende Buchungen und Kassenberichte bleiben unverändert, und die Kategorie lässt sich jederzeit wiederherstellen.',
                )}
              </p>
            </>
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-danger"
              disabled={busy}
              onClick={confirmRemove}
            >
              {removing.usage.deletable ? t('Löschen') : t('Archivieren')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setRemoving(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {current.length === 0 ? (
        <p className="muted">{t('Noch keine Kategorien.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Kategorie')}</th>
              <th>{t('gilt für')}</th>
              {areas.length > 0 && <th>{t('steuerlicher Bereich')}</th>}
              {org.donations_enabled && <th>{t('Spenden')}</th>}
              {artistsOn && <th>{t('Künstlerhonorare')}</th>}
              {vatOn && <th>{t('Umsatzsteuer')}</th>}
              {datevOn && <th>{t('DATEV-Konto')}</th>}
              <th className="num">{t('Buchungen')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {current.map((c) => (
              <tr key={c.id}>
                <td>
                  {renaming?.id === c.id ? (
                    <CategoryRename
                      orgId={org.id}
                      category={c}
                      onDone={(name) =>
                        void run(
                          async () => {},
                          name !== c.name
                            ? t('„{name}“ heißt jetzt „{name2}“.', { name: c.name, name2: name })
                            : undefined,
                        )
                      }
                    />
                  ) : (
                    <strong>{c.name}</strong>
                  )}
                </td>
                <td>
                  {canEdit ? (
                    <select
                      aria-label={t('{name}: gilt für', { name: c.name })}
                      value={c.kind}
                      onChange={(e) =>
                        void run(() =>
                          financeApi.updateCategory(org.id, c.id, {
                            kind: e.target.value as Category['kind'],
                          }),
                        )
                      }
                    >
                      {Object.entries(CATEGORY_KIND).map(([k, label]) => (
                        <option key={k} value={k}>
                          {label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    c.kind_label
                  )}
                </td>
                {areas.length > 0 && (
                  <td>
                    {canEdit ? (
                      <select
                        aria-label={t('{name}: steuerlicher Bereich', { name: c.name })}
                        value={c.tax_area}
                        onChange={(e) =>
                          void run(() =>
                            financeApi.updateCategory(org.id, c.id, { tax_area: e.target.value }),
                          )
                        }
                      >
                        <option value="">{t('ohne Zuordnung')}</option>
                        {areas.map((a) => (
                          <option key={a.value} value={a.value}>
                            {a.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      c.tax_area_label || '–'
                    )}
                  </td>
                )}
                {org.donations_enabled && (
                  <td>
                    {c.kind !== 'expense' && (
                      <input
                        type="checkbox"
                        aria-label={t('{name}: Spenden (Zuwendungsbestätigung möglich)', {
                          name: c.name,
                        })}
                        title={t('Einnahmen lassen sich unter Zuwendungsbestätigungen übernehmen')}
                        checked={c.donations}
                        disabled={!canEdit}
                        onChange={(e) =>
                          void run(() =>
                            financeApi.updateCategory(org.id, c.id, {
                              donations: e.target.checked,
                            }),
                          )
                        }
                      />
                    )}
                  </td>
                )}
                {vatOn && (
                  <td>
                    {canEdit ? (
                      <select
                        aria-label={t('{name}: Umsatzsteuer', { name: c.name })}
                        value={c.vat_rate ?? ''}
                        onChange={(e) =>
                          void run(() =>
                            financeApi.updateCategory(org.id, c.id, {
                              vat_rate: e.target.value as Category['vat_rate'],
                            }),
                          )
                        }
                      >
                        <option value="">{t('keine (nicht steuerbar)')}</option>
                        <option value="19">{t('19 %')}</option>
                        <option value="7">{t('7 %')}</option>
                        <option value="exempt">{t('steuerfrei')}</option>
                      </select>
                    ) : (
                      ((
                        { '19': t('19 %'), '7': t('7 %'), exempt: t('steuerfrei') } as Record<
                          string,
                          string
                        >
                      )[c.vat_rate ?? ''] ?? '–')
                    )}
                  </td>
                )}
                {artistsOn && (
                  <td>
                    {c.kind !== 'income' && (
                      <input
                        type="checkbox"
                        aria-label={t('{name}: Honorare an Künstler (Künstlersozialabgabe)', {
                          name: c.name,
                        })}
                        title={t('Ausgaben zählen für die Meldung an die Künstlersozialkasse')}
                        checked={!!c.artist_fees}
                        disabled={!canEdit}
                        onChange={(e) =>
                          void run(() =>
                            financeApi.updateCategory(org.id, c.id, {
                              artist_fees: e.target.checked,
                            }),
                          )
                        }
                      />
                    )}
                  </td>
                )}
                {datevOn && (
                  <td>
                    {canEdit ? (
                      <input
                        size={8}
                        inputMode="numeric"
                        aria-label={t('{name}: DATEV-Konto', { name: c.name })}
                        defaultValue={c.datev_account ?? ''}
                        onBlur={(e) => {
                          const value = e.target.value.trim()
                          if (value !== (c.datev_account ?? ''))
                            void run(() =>
                              financeApi.updateCategory(org.id, c.id, { datev_account: value }),
                            )
                        }}
                      />
                    ) : (
                      c.datev_account || '–'
                    )}
                  </td>
                )}
                <td className="num">{c.booking_count}</td>
                <td className="actions">
                  {canEdit && (
                    <>
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('{name} umbenennen', { name: c.name })}
                        onClick={() => {
                          setMessage(null)
                          setRenaming({ id: c.id, name: c.name })
                        }}
                      >
                        {t('Umbenennen')}
                      </button>{' '}
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('{name} löschen', { name: c.name })}
                        onClick={() => void askRemove(c)}
                      >
                        {t('Löschen')}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {archived.length > 0 && (
        <>
          <h3>{t('Archivierte Kategorien')}</h3>
          <p className="muted small">
            {t(
              'Nicht mehr für neue Buchungen wählbar, in Buchungen, Filtern und Kassenberichten weiter sichtbar.',
            )}
          </p>
          <ul className="role-list">
            {archived.map((c) => (
              <li key={c.id} className="role-row">
                <strong>{c.name}</strong>
                <span className="muted small">
                  {c.booking_count} {c.booking_count === 1 ? t('Buchung') : t('Buchungen')}
                </span>
                {canEdit && (
                  <button
                    type="button"
                    className="button button-ghost push-right"
                    disabled={busy}
                    aria-label={t('{name} wiederherstellen', { name: c.name })}
                    onClick={() =>
                      void run(
                        () => financeApi.restoreCategory(org.id, c.id),
                        t('„{name}“ ist wieder verfügbar.', { name: c.name }),
                      )
                    }
                  >
                    {t('Wiederherstellen')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {canEdit && (
        <form className="subcard" onSubmit={add}>
          <h3>{t('Neue Kategorie')}</h3>
          <div className="grid-3">
            <Field
              label={t('Name')}
              required
              value={form.values.name}
              error={form.errors.name}
              onChange={(e) => form.set('name', e.target.value)}
            />
            <SelectField
              label={t('gilt für')}
              value={form.values.kind}
              onChange={(e) => form.set('kind', e.target.value)}
            >
              {Object.entries(CATEGORY_KIND).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </SelectField>
            {areas.length > 0 && (
              <SelectField
                label={t('steuerlicher Bereich')}
                value={form.values.tax_area}
                onChange={(e) => form.set('tax_area', e.target.value)}
              >
                <option value="">{t('ohne Zuordnung')}</option>
                {areas.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </SelectField>
            )}
          </div>
          {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
          <button type="submit" className="button button-primary" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </form>
      )}
    </div>
  )
}

/** Kategorie umbenennen; der Name speichert automatisch, „Schließen“ wartet darauf und schließt. */
function CategoryRename({
  orgId,
  category,
  onDone,
}: {
  orgId: number
  category: Category
  onDone: (name: string) => void
}) {
  const form = useForm({ name: category.name })
  const auto = useAutoSave(form, (changes) =>
    financeApi.updateCategory(orgId, category.id, { name: changes.name?.trim() }),
  )
  return (
    <form
      className="inline-edit"
      onSubmit={(e) => {
        e.preventDefault()
        void auto.flush().then((ok) => {
          if (ok) onDone(form.values.name.trim())
        })
      }}
    >
      <input
        aria-label={t('Neuer Name für {name}', { name: category.name })}
        value={form.values.name}
        maxLength={100}
        autoFocus
        onChange={(e) => form.set('name', e.target.value)}
      />
      <button type="submit" className="link-button">
        {t('Schließen')}
      </button>
      {auto.state !== 'idle' && <SaveStatus auto={auto} />}
      {form.errors.name && <Alert kind="error">{form.errors.name}</Alert>}
    </form>
  )
}
