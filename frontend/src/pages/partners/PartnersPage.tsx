// Geschäftspartner (Konzept geschaeftspartner.md, P1): Lieferanten, Dienstleister, Sponsoren,
// Behörden und andere außerhalb der Mitgliederliste, mit Ansprechpartnern.
import { useMemo, useRef, useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { PARTNER_KINDS, PARTNER_ROLES, partnerApi, partnerFieldApi } from '../../api/partners.ts'
import type { BusinessPartner, ImportResult, PartnerRole } from '../../api/partners.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmLeave } from '../../components/leaveGuard.ts'
import { Alert, Checkbox, Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { FieldsAdmin } from '../settings/FieldsPage.tsx'
import { MailingCard } from './MailingCard.tsx'
import { kindLabel, partnerAccess, roleLabel } from './access.ts'
import { PartnerForm } from './PartnerForm.tsx'

export function PartnersPage() {
  const org = useActiveOrg()
  const access = partnerAccess(org.permissions)
  const load = useLoad(() => partnerApi.list(org.id), [org.id])
  const [selected, setSelected] = useState<BusinessPartner | 'new' | null>(null)
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState('')
  const [role, setRole] = useState('')
  const [inactive, setInactive] = useState(false)
  const [importing, setImporting] = useState(false)
  const [mailing, setMailing] = useState(false)
  const [fields, setFields] = useState(false)
  const [error, setError] = useState('')
  const rows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    return (load.data ?? []).filter((p) => {
      if (!inactive && !p.is_active) return false
      if (kind && p.kind !== kind) return false
      if (role && !p.roles.includes(role as PartnerRole)) return false
      if (!needle) return true
      const hay = [
        p.name,
        p.number,
        p.details.city,
        p.details.email,
        ...p.contacts.map((c) => `${c.first_name} ${c.last_name}`),
      ]
      return hay.some((v) => (v ?? '').toLocaleLowerCase().includes(needle))
    })
  }, [load.data, search, kind, role, inactive])
  // Der Seitenkopf steht auch beim Laden und bei Fehlern (Seitenkopf-Rundgang)
  if (load.error || !load.data)
    return (
      <div className="stack">
        <PageHeader title={t('Geschäftspartner')} />
        {load.error ? <LoadError message={load.error} onRetry={load.reload} /> : <Loading />}
      </div>
    )
  const open = (value: BusinessPartner | 'new') =>
    void confirmLeave().then((ok) => {
      if (ok) setSelected(value)
    })
  return (
    <div className="stack">
      <PageHeader
        title={t('Geschäftspartner')}
        subtitle={t(
          'Lieferanten, Dienstleister, Sponsoren, Behörden und alle anderen außerhalb der Mitgliederliste.',
        )}
        primary={
          access.edit ? { label: t('Geschäftspartner anlegen'), onClick: () => open('new') } : null
        }
        actions={[
          access.list && {
            label: t('Als Excel exportieren'),
            onClick: () => {
              setError('')
              partnerApi
                .exportFile(org.id)
                .then((blob) => saveBlob(blob, 'geschaeftspartner.xlsx'))
                .catch((err: unknown) => setError(errorMessage(err)))
            },
          },
          access.edit && { label: t('Aus Excel importieren'), onClick: () => setImporting(true) },
          access.edit &&
            access.list && {
              label: t('Serienbrief und Verteiler'),
              onClick: () => setMailing(true),
            },
          { label: t('Zusatzfelder'), onClick: () => setFields((x) => !x) },
        ]}
      />
      {error && <Alert kind="error">{error}</Alert>}
      {mailing && <MailingCard onClose={() => setMailing(false)} />}
      {fields && (
        <div className="stack">
          <FieldsAdmin api={partnerFieldApi} editable={access.edit} partners />
          <div className="button-row">
            <button type="button" className="button" onClick={() => setFields(false)}>
              {t('Schließen')}
            </button>
          </div>
        </div>
      )}
      {importing && (
        <ImportCard
          onClose={(changed) => {
            setImporting(false)
            if (changed) void load.reload()
          }}
        />
      )}
      {org.modules.includes('finance') && org.permissions.includes('finance.edit') && (
        <SuggestionsCard onAdopted={() => void load.reload()} />
      )}
      {selected && (
        <PartnerForm
          key={selected === 'new' ? 'new' : selected.id}
          partner={selected === 'new' ? undefined : selected}
          others={load.data.filter((p) => selected === 'new' || p.id !== selected.id)}
          onSaved={(saved) => {
            void load.reload()
            setSelected(saved ?? null)
          }}
          onChanged={() => void load.reload()}
          onClose={() => setSelected(null)}
        />
      )}
      <div className="card stack">
        <div className="grid-4">
          <Field
            label={t('Suchen')}
            type="search"
            value={search}
            placeholder={t('Name, Nummer, Ort oder Ansprechpartner')}
            onChange={(e) => setSearch(e.target.value)}
          />
          <SelectField label={t('Art')} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{t('Alle')}</option>
            {PARTNER_KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </SelectField>
          <SelectField label={t('Rolle')} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="">{t('Alle')}</option>
            {PARTNER_ROLES.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </SelectField>
          <Checkbox label={t('Inaktive zeigen')} checked={inactive} onChange={setInactive} />
        </div>
        {rows.length === 0 ? (
          <p className="muted">
            {load.data.length === 0
              ? t('Noch keine Geschäftspartner vorhanden.')
              : t('Keine Treffer.')}
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('Nummer')}</th>
                  <th>{t('Name')}</th>
                  <th>{t('Art')}</th>
                  <th>{t('Rollen')}</th>
                  <th>{t('Ort')}</th>
                  <th>{t('Ansprechpartner')}</th>
                  <th>{t('Telefon')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const primary = p.contacts[0]
                  return (
                    <tr key={p.id}>
                      <td>{p.number}</td>
                      <td>
                        <button className="button button-ghost" onClick={() => open(p)}>
                          {p.name}
                        </button>
                        {!p.is_active && <span className="muted small"> · {t('Inaktiv')}</span>}
                      </td>
                      <td>{kindLabel(p.kind)}</td>
                      <td>{p.roles.map(roleLabel).join(', ') || '—'}</td>
                      <td>{p.details.city || '—'}</td>
                      <td>
                        {primary
                          ? `${primary.first_name} ${primary.last_name}`.trim()
                          : p.details.contact || '—'}
                      </td>
                      <td>{primary?.phone || p.details.phone || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function ImportCard({ onClose }: { onClose: (changed: boolean) => void }) {
  const org = useActiveOrg()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [probe, setProbe] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async (dry: boolean) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const result = await partnerApi.importFile(org.id, file, dry)
      if (dry) setProbe(result)
      else
        onClose(
          result.created + result.updated + result.contacts_created + result.contacts_updated > 0,
        )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack">
      <h3>{t('Geschäftspartner aus Excel importieren')}</h3>
      <p className="muted small">
        {t(
          'Am einfachsten exportieren, in Excel ändern und wieder einlesen. Eine bekannte Nummer aktualisiert den Partner, leere Zellen ändern nichts. Zeilen ohne Nummer mit schon vorhandenem Namen werden übersprungen. Das Blatt „Ansprechpartner“ ergänzt und ändert Ansprechpartner.',
        )}
      </p>
      <input
        ref={input}
        type="file"
        accept=".xlsx"
        aria-label={t('Excel-Datei')}
        onChange={(e) => {
          setFile(e.target.files?.[0] ?? null)
          setProbe(null)
        }}
      />
      {probe && (
        <Alert kind={probe.errors.length ? 'error' : 'info'}>
          {t('{created} neu, {updated} geändert, {skipped} unverändert oder übersprungen.', {
            created: probe.created,
            updated: probe.updated,
            skipped: probe.skipped,
          })}{' '}
          {t('Ansprechpartner: {created} neu, {updated} geändert.', {
            created: probe.contacts_created,
            updated: probe.contacts_updated,
          })}
          {probe.errors.length > 0 && (
            <ul>
              {probe.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </Alert>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        {!probe ? (
          <button
            type="button"
            className="button button-primary"
            disabled={!file || busy}
            onClick={() => void run(true)}
          >
            {t('Datei prüfen')}
          </button>
        ) : (
          <button
            type="button"
            className="button button-primary"
            disabled={
              busy ||
              probe.created + probe.updated + probe.contacts_created + probe.contacts_updated === 0
            }
            onClick={() => void run(false)}
          >
            {t('Importieren')}
          </button>
        )}
        <button type="button" className="button" onClick={() => onClose(false)}>
          {t('Abbrechen')}
        </button>
      </div>
    </section>
  )
}

function SuggestionsCard({ onAdopted }: { onAdopted: () => void }) {
  const org = useActiveOrg()
  const list = useLoad(() => partnerApi.suggestions(org.id), [org.id])
  const [error, setError] = useState('')
  const [done, setDone] = useState('')
  if (!list.data?.length) return null
  return (
    <details className="card">
      <summary>{t('Vorschläge aus dem Kassenbuch ({n})', { n: list.data.length })}</summary>
      <p className="muted small">
        {t(
          'Diese Namen stehen mehrfach als Empfänger oder Zahler im Kassenbuch. „Übernehmen“ legt einen Geschäftspartner an und verknüpft die Buchungen mit genau diesem Namen.',
        )}
      </p>
      {done && <Alert kind="success">{done}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <ul className="item-list">
        {list.data.map((s) => (
          <li key={s.name} className="item-row">
            <div className="item-row-info">
              <strong>{s.name}</strong>
              <div className="muted small">{t('{n}-mal verwendet', { n: s.count })}</div>
            </div>
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={async () => {
                  setError('')
                  try {
                    const created = await partnerApi.adopt(org.id, s.name)
                    setDone(
                      t('„{name}“ übernommen, {n} Buchungen verknüpft.', {
                        name: created.name,
                        n: created.linked,
                      }),
                    )
                    list.setData((list.data ?? []).filter((x) => x.name !== s.name))
                    onAdopted()
                  } catch (err) {
                    setError(errorMessage(err))
                  }
                }}
              >
                {t('Übernehmen')}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </details>
  )
}
