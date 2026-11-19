// Vor Ort (Anmeldung A6, Konzept 3.11): Namensschilder und Aufkleber mit wählbaren Angaben
// drucken, Material (Namensschild, Tasche, Leihgerät …) ausgeben und zurücknehmen.
import { useEffect, useState } from 'react'
import type { CalendarBase } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { LabelOptions, MaterialBoard } from '../../api/registrations.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, Loading, SelectField } from '../ui.tsx'
import { confirmDialog } from '../dialog.ts'
import { useRowSearch } from '../RowSearch.tsx'
import { t } from '../../i18n/index.ts'

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

const FORMAT_LABELS: Record<string, () => string> = {
  badge: () => t('Namensschilder 85 × 54 mm (10 je Seite)'),
  label24: () => t('Aufkleber 70 × 37 mm (24 je Bogen)'),
  label8: () => t('Aufkleber 105 × 74 mm (8 je Bogen)'),
}

const FIELD_LABELS: Record<string, () => string> = {
  event: () => t('Veranstaltung'),
  name: () => t('Name'),
  club: () => t('Verein'),
  price: () => t('Tarif'),
  addons: () => t('Zusatzleistungen'),
  number: () => t('Anmeldenummer'),
  qr: () => t('QR-Code der Eintrittskarte'),
}

/** Druck: Format und Angaben wählen, PDF öffnen. */
export function PrintPanel({
  base,
  eventId,
  options,
}: {
  base: CalendarBase
  eventId: number
  options: LabelOptions
}) {
  const [format, setFormat] = useState(options.formats[0] ?? 'badge')
  const [fields, setFields] = useState<string[]>(options.default_fields)
  const all = [
    ...options.fields.map((f) => ({ key: f, label: FIELD_LABELS[f]?.() ?? f })),
    ...options.questions.map((q) => ({ key: `q${q.id}`, label: q.text })),
  ]
  function toggle(key: string, on: boolean) {
    // Reihenfolge wie in der Auswahl, damit der Druck vorhersehbar ist
    const next = new Set(fields)
    if (on) next.add(key)
    else next.delete(key)
    setFields(all.map((f) => f.key).filter((k) => next.has(k)))
  }
  return (
    <div className="stack">
      <SelectField label={t('Format')} value={format} onChange={(e) => setFormat(e.target.value)}>
        {options.formats.map((f) => (
          <option key={f} value={f}>
            {FORMAT_LABELS[f]?.() ?? f}
          </option>
        ))}
      </SelectField>
      <fieldset className="stack-sm">
        <legend>{t('Angaben')}</legend>
        {all.map((f) => (
          <Checkbox
            key={f.key}
            label={f.label}
            checked={fields.includes(f.key)}
            onChange={(on) => toggle(f.key, on)}
          />
        ))}
      </fieldset>
      {options.questions.length === 0 && (
        <p className="muted small">
          {t('Firmenname oder Funktion druckt ihr über eine Zusatzfrage je Person, z. B. „Firma“.')}
        </p>
      )}
      <div className="button-row">
        <a
          className="button"
          href={registrationApi.badgesUrl(base, eventId, format, fields)}
          target="_blank"
          rel="noopener"
          aria-disabled={fields.length === 0}
        >
          {t('PDF erstellen')}
        </a>
      </div>
    </div>
  )
}

/** Druckauswahl mit den Optionen vom Server */
export function PrintLoader({ base, eventId }: { base: CalendarBase; eventId: number }) {
  const { data, error } = useLoad(() => registrationApi.materials(base, eventId), [base, eventId])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  return <PrintPanel base={base} eventId={eventId} options={data.labels} />
}

/** Material ausgeben und zurücknehmen, mit Liste je Person (lädt alle 10 Sekunden neu). */
export function MaterialPanel({ base, eventId }: { base: CalendarBase; eventId: number }) {
  const { data, error, setData } = useLoad(
    () => registrationApi.materials(base, eventId),
    [base, eventId],
  )
  const [name, setName] = useState('')
  const [returnable, setReturnable] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const rows = data?.rows ?? []
  const search = useRowSearch(rows, (r) => `${r.name} ${r.number}`, t('Personen'))

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.hidden) return
      registrationApi
        .materials(base, eventId)
        .then((fresh) => setData(fresh))
        .catch(() => undefined)
    }, 10000)
    return () => window.clearInterval(timer)
  }, [base, eventId, setData])

  async function run(action: () => Promise<MaterialBoard | unknown>) {
    setFailed(null)
    try {
      const res = await action()
      if (res && typeof res === 'object' && 'rows' in res) setData(res as MaterialBoard)
      else setData(await registrationApi.materials(base, eventId))
    } catch (e) {
      setFailed(errorMessage(e))
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  const mats = data.materials
  return (
    <div className="stack">
      {mats.length > 0 && (
        <p>
          {mats
            .map((m) => {
              const c = data.counts[String(m.id)] ?? { out: 0, returned: 0 }
              return m.returnable
                ? t('{name}: {out} ausgegeben, {returned} zurück', {
                    name: m.name,
                    out: c.out,
                    returned: c.returned,
                  })
                : t('{name}: {out} von {total} ausgegeben', {
                    name: m.name,
                    out: c.out,
                    total: rows.length,
                  })
            })
            .join(' · ')}
        </p>
      )}
      {failed && <Alert kind="error">{failed}</Alert>}
      {data.can_edit && (
        <form
          className="stack-sm"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              await registrationApi.addMaterial(base, eventId, { name: name.trim(), returnable })
              setName('')
              setReturnable(false)
            })
          }}
        >
          <Field
            label={t('Neues Material')}
            hint={t('z. B. Namensschild, Tasche oder Leihgerät')}
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
          />
          <Checkbox label={t('mit Rückgabe')} checked={returnable} onChange={setReturnable} />
          <div className="button-row">
            <button type="submit" className="button button-ghost" disabled={!name.trim()}>
              {t('Material anlegen')}
            </button>
            {mats.map((m) => (
              <button
                key={m.id}
                type="button"
                className="button button-ghost small"
                onClick={async () => {
                  if (
                    await confirmDialog({
                      final: false,
                      title: t('„{name}“ entfernen?', { name: m.name }),
                      confirmLabel: t('Entfernen'),
                    })
                  )
                    void run(() => registrationApi.removeMaterial(base, eventId, m.id))
                }}
              >
                {t('„{name}“ entfernen', { name: m.name })}
              </button>
            ))}
          </div>
        </form>
      )}
      {mats.length > 0 && (
        <>
          {search.field}
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Name')}</th>
                  {mats.map((m) => (
                    <th key={m.id}>{m.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {search.shown.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {r.name}
                      <div className="muted small">
                        {r.number} · {r.price_name}
                      </div>
                    </td>
                    {mats.map((m) => {
                      const h = r.items[String(m.id)]
                      const act = (action: 'out' | 'return' | 'undo') =>
                        void run(() =>
                          registrationApi.handout(base, eventId, {
                            participant: r.id,
                            material: m.id,
                            action,
                          }),
                        )
                      return (
                        <td key={m.id}>
                          {h ? (
                            <>
                              <span className="badge badge-yes">
                                {t('ausgegeben {time}', { time: time(h.handed_out_at) })}
                              </span>
                              {h.returned_at && (
                                <>
                                  {' '}
                                  <span className="badge">
                                    {t('zurück {time}', { time: time(h.returned_at) })}
                                  </span>
                                </>
                              )}
                              {h.via && <div className="muted small">{h.via}</div>}
                            </>
                          ) : (
                            <span className="muted small">{t('offen')}</span>
                          )}
                          {data.can_edit && (
                            <div className="button-row">
                              {!h && (
                                <button
                                  type="button"
                                  className="button button-ghost small"
                                  aria-label={t('{material} an {name} ausgeben', {
                                    material: m.name,
                                    name: r.name,
                                  })}
                                  onClick={() => act('out')}
                                >
                                  {t('Ausgeben')}
                                </button>
                              )}
                              {h && m.returnable && !h.returned_at && (
                                <button
                                  type="button"
                                  className="button button-ghost small"
                                  aria-label={t('{material} von {name} zurücknehmen', {
                                    material: m.name,
                                    name: r.name,
                                  })}
                                  onClick={() => act('return')}
                                >
                                  {t('Rücknahme')}
                                </button>
                              )}
                              {h && (
                                <button
                                  type="button"
                                  className="button button-ghost small"
                                  onClick={() => act('undo')}
                                >
                                  {t('Rückgängig')}
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
