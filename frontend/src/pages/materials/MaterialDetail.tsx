import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { materialApi } from '../../api/materials.ts'
import type { Material, MaterialChoice, MaterialEvent, StockRow } from '../../api/materials.ts'
import { errorMessage, useLoad, whenLabel } from '../../components/forms.ts'
import { t, tn, locale } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { BookingRulesCard } from '../bookings/BookingRulesCard.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading } from '../../components/ui.tsx'
import './materials.css'
import {
  conditionLabel,
  facilityTypeLabel,
  laneLabel,
  ownershipLabel,
  stockRoot,
  type Stock,
  location,
} from './materialsHelpers.ts'
import { ItemForm } from './ItemForm.tsx'
import { MaterialPicker } from './MaterialPicker.tsx'

export function MaterialDetail({
  stock,
  base,
  editable,
}: {
  stock: Stock
  base: string
  editable: boolean
}) {
  const { id } = useParams()
  const [params] = useSearchParams()
  const trash = params.get('trash') === '1'
  const { data, error, reload } = useLoad(
    () => materialApi.get(base, Number(id), trash),
    [base, id, trash],
  )
  const { active: activeOrg, activeDept: activeUnit } = useOrg()
  // Belegung ist ein eigenes Modul (module-neustruktur, M2a)
  const bookingsOn = activeOrg
    ? activeOrg.modules.includes('bookings')
    : activeUnit?.bookings_enabled !== false
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await fn()
      await reload()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (error) return <p role="alert">{error}</p>
  if (!data) return <Loading />
  if (editing)
    return (
      <ItemForm
        key={data.version}
        stock={stock}
        base={base}
        item={data}
        onSaved={() => {
          setEditing(false)
          reload()
        }}
      />
    )
  return (
    <>
      <PageHeader
        title={data.title}
        primary={
          editable && !trash ? { label: t('Bearbeiten'), onClick: () => setEditing(true) } : null
        }
      >
        {data.music_equipment && (
          <p>
            <Link to="/material/musik">{t('Musikausstattung öffnen')}</Link>
            {data.music_equipment.loaned ? ` · ${t('Über den Musikbereich ausgegeben')}` : ''}
          </p>
        )}
      </PageHeader>
      {failure && <p role="alert">{failure}</p>}
      <section className="card">
        <p className="muted">{data.inventory_number}</p>
        <p>{data.description}</p>
        {data.facility_type && (
          <p>
            {facilityTypeLabel(data.facility_type)}
            {data.ownership ? ` · ${ownershipLabel(data.ownership)}` : ''}
            {data.capacity ? ` · ${t('Kapazität {n}', { n: data.capacity })}` : ''}
          </p>
        )}
        {!!data.lanes?.length && (
          <ul>
            {data.lanes.map((lane) => (
              <li key={lane.facility}>
                {laneLabel(lane.facility)}: {tn('{n} Bahn', '{n} Bahnen', lane.count)}
              </li>
            ))}
          </ul>
        )}
        <h2>{t('Standort')}</h2>
        <p>
          {data.location_kind === 'facility' && data.facility && !data.location_review ? (
            <Link to={`/infrastruktur/${data.facility}`}>{location(data)}</Link>
          ) : (
            location(data)
          )}
        </p>
        {data.parent && <p>{Object.values(data.parent.address).filter(Boolean).join(', ')}</p>}
        <p>{data.location_note}</p>
        {data.access_note && (
          <p>
            {t('Zugangshinweis')}: {data.access_note}
          </p>
        )}
        {data.belongs_to && (
          <p>
            {t('Gehört zu')}:{' '}
            <Link to={`/infrastruktur/${data.belongs_to}`}>{data.belongs_to_title}</Link>
          </p>
        )}
        <p>
          {conditionLabel(data.condition, stock.kind)} · {data.condition_note}
        </p>
      </section>
      {stock.kind === 'facility' && !trash && (
        <FacilityParts stock={stock} item={data} editable={editable} />
      )}
      {!trash && bookingsOn && (
        <BookingRulesCard itemBase={base} item={data} editable={editable} onSaved={reload} />
      )}
      {!trash && (
        <section className="card">
          <h2>{stock.kind === 'facility' ? t('Foto') : t('Materialfoto')}</h2>
          {data.photo_url ? (
            <img className="material-photo" src={data.photo_url} alt={data.title} />
          ) : (
            <p>{t('Noch kein Bild vorhanden.')}</p>
          )}
          {editable && (
            <>
              <label>
                {t('Bild hinzufügen oder ersetzen')}
                <input
                  disabled={busy}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    const form = new FormData()
                    form.append('file', file)
                    form.append('version', String(data.version))
                    void act(() => api.post(`${base}${data.id}/photo/`, form))
                    e.target.value = ''
                  }}
                />
              </label>
              <p className="muted">
                {t('JPEG, PNG oder WebP, höchstens 10 MB. Bildmetadaten werden entfernt.')}
              </p>
              {data.photo_url && (
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void act(() =>
                      api.delWith(`${base}${data.id}/photo/`, { version: data.version }),
                    )
                  }
                >
                  {t('Bild entfernen')}
                </button>
              )}
            </>
          )}
        </section>
      )}
      <section className="card">
        <h2>{t('Verwendung')}</h2>
        <p>{data.purpose}</p>
        {data.usage_review && <p role="status">{t('Verwendung prüfen')}</p>}
        {data.events?.map((link) => (
          <div className="material-link" key={link.id}>
            <div>
              <strong>{link.title}</strong>
              <p>
                {eventLabel(link.kind)}
                {link.original_start ? ` · ${whenLabel(link.original_start, link.all_day)}` : ''}
                {link.valid_from ? ` · ${t('Ab')} ${link.valid_from}` : ''}
                {link.valid_until ? ` · ${t('Bis')} ${link.valid_until}` : ''}
              </p>
              <p>{link.note}</p>
              {link.needs_review && <p>{t('Terminbezug prüfen')}</p>}
              {link.cancelled && <p>{t('Abgesagt')}</p>}
              {data.booking_rules?.enabled &&
                !trash &&
                !link.cancelled &&
                link.kind !== 'exclude' &&
                (link.kind !== 'occurrence' || link.original_start) && (
                  <Link
                    to={`/belegung?${new URLSearchParams({
                      buchen: '1',
                      objekt: String(data.id),
                      termin: String(link.event),
                      titel: link.title,
                      ...(link.kind === 'occurrence' && link.original_start
                        ? { vorkommen: link.original_start }
                        : {}),
                    }).toString()}`}
                  >
                    {t('Verbindlich buchen')}
                  </Link>
                )}
            </div>
            {editable && !trash && (
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() =>
                  void act(() =>
                    materialApi.link(base, data, { type: 'event', id: link.id, remove: true }),
                  )
                }
              >
                {t('Zuordnung entfernen')}
              </button>
            )}
          </div>
        ))}
        {!trash && (
          <>
            <h3>{t('Kommende Verwendungen')}</h3>
            {data.uses?.length ? (
              <ul>
                {data.uses.map((u) => (
                  <li key={`${u.event}-${u.original_start}`}>
                    {u.title} · {whenLabel(u.starts_at, u.all_day)}
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t('Keine kommenden Verwendungen im nächsten Jahr.')}</p>
            )}
            <p className="muted">
              {t('Eine Zuordnung erfasst den Bedarf und ist keine verbindliche Reservierung.')}
            </p>
          </>
        )}
        {editable && !trash && data.condition !== 'retired' && (
          <EventEditor
            base={base}
            busy={busy}
            save={(row) => act(() => materialApi.link(base, data, { type: 'event', ...row }))}
          />
        )}
      </section>
      {(['todo', 'document'] as const).map((kind) => (
        <section className="card" key={kind}>
          <h2>{kind === 'todo' ? t('Aufgaben') : t('Dokumente')}</h2>
          {(kind === 'todo' ? data.todos : data.documents)?.map((row) => (
            <div className="material-link" key={row.id}>
              <a
                href={
                  kind === 'todo'
                    ? `/aufgaben?aufgabe=${row.id}`
                    : `${base}${data.id}/documents/${row.id}/`
                }
              >
                {row.title}
                {'status' in row && row.status === 'done' ? ` · ${t('Erledigt')}` : ''}
              </a>
              {editable && !trash && (
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void act(() =>
                      materialApi.link(base, data, { type: kind, id: row.id, remove: true }),
                    )
                  }
                >
                  {t('Zuordnung entfernen')}
                </button>
              )}
            </div>
          ))}
          {editable && !trash && data.condition !== 'retired' && (
            <fieldset disabled={busy}>
              <MaterialPicker
                base={base}
                kind={kind}
                onSelect={(row) =>
                  void act(() => materialApi.link(base, data, { type: kind, id: row.id }))
                }
              />
              {kind === 'todo' && (
                <Link
                  to={`/aufgaben?neu=1&material=${data.id}${stock.kind === 'facility' ? '&art=facility' : ''}`}
                >
                  {stock.kind === 'facility'
                    ? t('Aufgabe für diese Infrastruktur anlegen')
                    : t('Aufgabe für dieses Material anlegen')}
                </Link>
              )}
            </fieldset>
          )}
        </section>
      ))}
      <History
        key={data.version}
        root={stock.root}
        base={base}
        item={data}
        editable={editable}
        act={act}
        busy={busy}
      />
      {editable && (
        <div className="button-row">
          {trash ? (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await materialApi.restore(base, data)
                  navigate(`${stock.root}/${data.id}`)
                })
              }
            >
              {t('Wiederherstellen')}
            </button>
          ) : (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await materialApi.remove(base, data)
                  navigate(`${stock.root}?trash=1&archived=1`)
                })
              }
            >
              {t('In den Papierkorb')}
            </button>
          )}
        </div>
      )}
    </>
  )
}

function eventLabel(kind: MaterialEvent['kind']) {
  return {
    event: t('Einzeltermin'),
    series: t('Ganze Reihe'),
    occurrence: t('Nur dieser Termin'),
    exclude: t('Diesen Termin ausschließen'),
  }[kind]
}

function EventEditor({
  base,
  busy,
  save,
}: {
  base: string
  busy: boolean
  save: (row: object) => Promise<void>
}) {
  const [choice, setChoice] = useState<MaterialChoice | null>(null)
  const [kind, setKind] = useState<MaterialEvent['kind']>('event')
  const [original, setOriginal] = useState('')
  const [from, setFrom] = useState('')
  const [until, setUntil] = useState('')
  const [note, setNote] = useState('')
  return (
    <details>
      <summary>{t('Termin oder Terminreihe zuordnen')}</summary>
      <fieldset disabled={busy}>
        <MaterialPicker
          base={base}
          kind="event"
          onSelect={(row) => {
            setChoice(row)
            setKind(row.series ? 'series' : 'event')
            setOriginal('')
          }}
        />
        {choice && (
          <>
            <p>{choice.title}</p>
            {choice.series && (
              <label>
                {t('Geltung')}
                <select
                  value={kind}
                  onChange={(e) => setKind(e.target.value as MaterialEvent['kind'])}
                >
                  {(['series', 'occurrence', 'exclude'] as const).map((k) => (
                    <option value={k} key={k}>
                      {eventLabel(k)}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {(kind === 'occurrence' || kind === 'exclude') && (
              <label>
                {t('Ursprünglicher Beginn des Vorkommens')}
                <input
                  type="datetime-local"
                  required
                  value={original}
                  onChange={(e) => setOriginal(e.target.value)}
                />
              </label>
            )}
            {kind === 'series' && (
              <div className="material-filters">
                <label>
                  {t('Gültig ab (leer: heute)')}
                  <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
                </label>
                <label>
                  {t('Gültig bis')}
                  <input type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
                </label>
              </div>
            )}
            <label>
              {t('Verwendungshinweis')}
              <input maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} />
            </label>
            <button
              className="button button-ghost"
              type="button"
              disabled={busy || (['occurrence', 'exclude'].includes(kind) && !original)}
              onClick={() =>
                void save({
                  event: choice.id,
                  kind,
                  ...(original ? { original_start: original + ':00' } : {}),
                  ...(from ? { valid_from: from } : {}),
                  valid_until: until || null,
                  note,
                })
              }
            >
              {t('Zuordnen')}
            </button>
          </>
        )}
      </fieldset>
    </details>
  )
}

function History({
  root,
  base,
  item,
  editable,
  act,
  busy,
}: {
  root: string
  base: string
  item: Material
  editable: boolean
  act: (fn: () => Promise<unknown>) => Promise<void>
  busy: boolean
}) {
  const navigate = useNavigate()
  const endpoint = `${base}${item.id}/history/${item.deleted_at ? '?trash=1' : ''}`
  const { data, error } = useLoad(
    () =>
      api.get<{ id: number; at: string; action: string; actor: string; can_undo: boolean }[]>(
        endpoint,
      ),
    [endpoint],
  )
  return (
    <details className="card">
      <summary>{t('Verlauf')}</summary>
      {error && <p role="alert">{error}</p>}
      {data?.map((row, index) => (
        <div className="material-link" key={row.id}>
          <span>
            {new Date(row.at).toLocaleString(locale(), { timeZone: 'Europe/Berlin' })} · {row.actor}{' '}
            ·{' '}
            {
              {
                create: t('Angelegt'),
                update: t('Bearbeitet'),
                links: t('Zuordnungen geändert'),
                photo: t('Bild geändert'),
                delete: t('In den Papierkorb'),
                restore: t('Wiederhergestellt'),
                undo: t('Rückgängig'),
              }[row.action]
            }
          </span>
          {index === 0 && row.can_undo && editable && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const restored = await api.post<Material>(endpoint, {
                    version: item.version,
                    revision: row.id,
                  })
                  if (!!restored.deleted_at !== !!item.deleted_at)
                    navigate(`${root}/${item.id}${restored.deleted_at ? '?trash=1' : ''}`)
                })
              }
            >
              {t('Rückgängig')}
            </button>
          )}
        </div>
      ))}
    </details>
  )
}

function FacilityParts({
  stock,
  item,
  editable,
}: {
  stock: Stock
  item: Material
  editable: boolean
}) {
  const row = (r: StockRow) => (
    <li key={r.id}>
      <Link to={`${stockRoot(r.kind)}/${r.id}`}>
        {r.inventory_number} · {r.title}
      </Link>
      {r.member_name ? ` · ${t('Bei {name}', { name: r.member_name })}` : ''}
      {r.location_note ? ` · ${r.location_note}` : ''}
      {r.condition !== 'ready' ? ` · ${conditionLabel(r.condition, r.kind)}` : ''}
    </li>
  )
  return (
    <>
      {item.location_kind !== 'facility' && (
        <section className="card">
          <h2>{t('Bereiche')}</h2>
          {item.areas?.length ? (
            <ul>{item.areas.map(row)}</ul>
          ) : (
            <p>
              {t('Keine Bereiche. Bereiche sind zum Beispiel Saal, Küche oder einzelne Stände.')}
            </p>
          )}
          {editable && item.condition !== 'retired' && (
            <Link
              to={`${stock.root}/neu?bereich=${item.id}&name=${encodeURIComponent(item.title)}`}
            >
              {t('Bereich anlegen')}
            </Link>
          )}
        </section>
      )}
      {item.contents && (
        <section className="card">
          <h2>{t('Hier gelagertes Material')}</h2>
          {item.contents.length ? (
            <ul>{item.contents.map(row)}</ul>
          ) : (
            <p>{t('Kein Material hier gelagert.')}</p>
          )}
          <h2>{t('Zugehöriges Material')}</h2>
          {item.accessories?.length ? (
            <ul>{item.accessories.map(row)}</ul>
          ) : (
            <p>{t('Kein zugehöriges Material, zum Beispiel Schlüssel.')}</p>
          )}
        </section>
      )}
    </>
  )
}
