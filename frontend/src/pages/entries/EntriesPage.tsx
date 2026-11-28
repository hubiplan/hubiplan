// Meldungen: Ausschreibungen erfassen, Mannschaften und Personen melden, Fassungen.
// Konzept: konzepte/meldungen.md, Doku docs/meldungen.md.
import { PageHeader } from '../../components/PageHeader.tsx'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { STATUS_LABELS, entriesApi, type Call, type CallDetail } from '../../api/entries.ts'
import { DataTable } from '../../components/DataTable.tsx'
import { formatDate, useForm, useLoad } from '../../components/forms.ts'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import {
  Alert,
  Checkbox,
  Field,
  LoadError,
  SelectField,
  Tabs,
  Loading,
} from '../../components/ui.tsx'
import { PERM } from '../../api/orgs.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { UnitEntryPage, UnitsPanel } from './UnitEntries.tsx'
import { ClubOffersCard } from './ClubOffers.tsx'
import { t } from '../../i18n/index.ts'
import { EmptyList } from '../../components/EmptyList.tsx'
import { EntryPanel } from './EntryPanel.tsx'
import { CallEditor } from './CallEditor.tsx'
import { VersionsPanel } from './EntrySubmit.tsx'

export function EntriesPage() {
  return (
    <Routes>
      <Route index element={<CallList />} />
      <Route path=":id/*" element={<CallArea />} />
    </Routes>
  )
}

function statusText(c: Call): string {
  if (c.unit_counts)
    return t('{x1} von {x2} gemeldet', { x1: c.unit_counts.submitted, x2: c.unit_counts.addressed })
  if (!c.entry_status) return t('noch nicht gemeldet')
  const label = STATUS_LABELS[c.entry_status]
  return c.entry_changed && c.entry_status !== 'entwurf' ? `${label}, geändert` : label
}

function CallList() {
  const org = useActiveOrg()
  const navigate = useNavigate()
  const { data, error, reload } = useLoad(() => entriesApi.list(org.id), [org.id])
  const [creating, setCreating] = useState(false)
  return (
    <section>
      <PageHeader name={t('Meldungen')} />
      <p className="muted">
        {t(
          'Mannschaften, Personen und Angaben an einen Veranstalter melden, etwa zu einem Vergleichsschießen oder einem Verbandsfest. Die Meldung geht als Brief auf eurem Briefbogen, per E-Mail oder als Tabelle hinaus; Änderungen werden als neue Fassung festgehalten.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={reload} />}
      <ClubOffersCard />
      {/* Ohne Ausschreibungen steht der Knopf nur im leeren Kasten, nicht doppelt */}
      {!creating && (data?.length ?? 0) > 0 && (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setCreating(true)}>
            {t('Neue Ausschreibung erfassen')}
          </button>
        </div>
      )}
      {creating && (
        <NewCall
          org={org.id}
          onClose={() => setCreating(false)}
          onCreated={(id) => navigate(`/meldungen/${id}/ausschreibung`)}
        />
      )}
      {data && (
        <DataTable<Call>
          label={t('Ausschreibungen')}
          rows={data}
          rowKey={(c) => c.id}
          initialSort={{ key: 'deadline', dir: 'desc' }}
          emptyText={t('Noch keine Ausschreibungen.')}
          empty={
            creating ? undefined : (
              <EmptyList
                title={t('Noch keine Ausschreibungen.')}
                canAdd
                action={{
                  label: t('Neue Ausschreibung erfassen'),
                  onClick: () => setCreating(true),
                }}
              />
            )
          }
          columns={[
            {
              key: 'deadline',
              label: t('Meldeschluss'),
              value: (c) => c.deadline ?? '',
              render: (c) => (c.deadline ? formatDate(c.deadline) : '—'),
            },
            {
              key: 'title',
              label: t('Ausschreibung'),
              value: (c) => c.title,
              render: (c) => <Link to={`/meldungen/${c.id}`}>{c.title}</Link>,
            },
            { key: 'organizer', label: t('Veranstalter'), value: (c) => c.organizer },
            {
              key: 'date',
              label: t('Datum'),
              value: (c) => c.date ?? '',
              render: (c) => (c.date ? formatDate(c.date) : '—'),
              optional: true,
            },
            { key: 'status', label: t('Meldung'), value: statusText, filter: true },
          ]}
        />
      )}
    </section>
  )
}

function NewCall({
  org,
  onClose,
  onCreated,
}: {
  org: number
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const active = useActiveOrg()
  const canIssue = active.permissions.includes(PERM.entriesManage)
  const form = useForm({
    title: '',
    organizer: '',
    date: '',
    deadline: '',
    template: 'mannschaften',
    internal: false,
  })
  const { values: v, set, errors } = form
  const draft = useChangesGuard(v)

  async function save(e: FormEvent) {
    e.preventDefault()
    const created = await form.submit(() =>
      entriesApi.create(org, {
        title: v.title,
        organizer: v.internal ? '' : v.organizer,
        internal: v.internal,
        date: v.date || null,
        deadline: v.deadline || null,
        template: v.template,
      }),
    )
    if (created) {
      draft.markSaved()
      onCreated((created as CallDetail).id)
    }
  }

  return (
    <div className="card card-wide">
      <form onSubmit={save}>
        <div className="card-head">
          <h2>{t('Neue Ausschreibung')}</h2>
          <button
            type="button"
            className="button button-ghost push-right"
            disabled={form.busy}
            onClick={async () => {
              if (await confirmDiscard(draft.dirty)) onClose()
            }}
          >
            {t('Abbrechen')}
          </button>
        </div>
        {canIssue && (
          <Checkbox
            label={t('Wir schreiben selbst aus, unsere Untereinheiten melden')}
            hint={t('z. B. ein Turnier, zu dem die Untereinheiten ihre Mannschaften melden')}
            checked={v.internal}
            onChange={(on) => set('internal', on)}
          />
        )}
        <p className="muted">
          {v.internal
            ? t(
                'Die Untereinheiten finden die Ausschreibung in ihrem Bereich unter „Meldungen“ und melden dort; ihr bestätigt im Eingang.',
              )
            : t(
                'Übertragt hier die Ausschreibung, die ihr per Brief oder Mail bekommen habt. Bei jährlichen Anlässen könnt ihr später die Ausschreibung des Vorjahres kopieren.',
              )}
        </p>
        <div className="grid-3">
          <Field
            label={t('Titel')}
            required
            placeholder={t('z. B. Kreismeisterschaft 2027')}
            value={v.title}
            error={errors.title}
            onChange={(e) => set('title', e.target.value)}
          />
          {!v.internal && (
            <Field
              label={t('Veranstalter')}
              required
              placeholder={t('z. B. Kreisverband Musterstadt')}
              value={v.organizer}
              error={errors.organizer}
              onChange={(e) => set('organizer', e.target.value)}
            />
          )}
          <SelectField
            label={t('Vorlage')}
            value={v.template}
            onChange={(e) => set('template', e.target.value)}
          >
            <option value="mannschaften">{t('Mannschaften melden')}</option>
            <option value="">{t('leer (Bausteine selbst anlegen)')}</option>
          </SelectField>
          <Field
            label={t('Datum des Anlasses')}
            type="date"
            value={v.date}
            error={errors.date}
            onChange={(e) => set('date', e.target.value)}
          />
          <Field
            label={t('Meldeschluss')}
            type="date"
            value={v.deadline}
            error={errors.deadline}
            onChange={(e) => set('deadline', e.target.value)}
          />
        </div>
        {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
        <div className="button-row">
          <button type="submit" className="button" disabled={form.busy}>
            {t('Anlegen')}
          </button>
        </div>
      </form>
    </div>
  )
}

function CallArea() {
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const call = useLoad(() => entriesApi.get(org.id, id), [org.id, id])
  const entry = useLoad(() => entriesApi.entry(org.id, id), [org.id, id])
  const options = useLoad(() => entriesApi.options(org.id), [org.id])
  const error = call.error || entry.error || options.error
  if (error)
    return (
      <LoadError
        message={error}
        onRetry={() => {
          void call.reload()
          void entry.reload()
          void options.reload()
        }}
      />
    )
  if (!call.data || !options.data || (entry.loading && entry.data === null)) return <Loading />
  const c = call.data
  const base = `/meldungen/${id}`
  return (
    <section>
      <PageHeader title={c.title} />
      <p className="muted">
        {t('Veranstalter: ')}
        {c.organizer}
        {c.date ? ` · ${formatDate(c.date)}` : ''}
        {c.location ? ` · ${c.location}` : ''}
        {c.deadline ? t(' · Meldeschluss {x1}', { x1: formatDate(c.deadline) }) : ''}
      </p>
      {c.internal ? (
        <Tabs
          items={[
            { to: base, label: t('Eingang') },
            { to: `${base}/ausschreibung`, label: t('Ausschreibung') },
          ]}
        />
      ) : (
        <Tabs
          items={[
            { to: base, label: t('Meldung') },
            { to: `${base}/ausschreibung`, label: t('Ausschreibung') },
            { to: `${base}/fassungen`, label: t('Fassungen') },
          ]}
        />
      )}
      {c.internal && (
        <Routes>
          <Route index element={<UnitsPanel org={org.id} call={c} />} />
          <Route
            path="einheit/:unit"
            element={<UnitEntryPage org={org.id} call={c} options={options.data} />}
          />
        </Routes>
      )}
      <Routes>
        <Route
          index
          element={
            c.internal ? null : (
              <EntryPanel
                org={org.id}
                call={c}
                entry={entry.data ?? null}
                options={options.data}
                setEntry={(e) => {
                  entry.setData(e)
                  void call.reload()
                }}
              />
            )
          }
        />
        <Route
          path="ausschreibung"
          element={
            <CallEditor
              org={org.id}
              call={c}
              options={options.data}
              onChanged={(d) => call.setData(d)}
              reload={() => {
                void call.reload()
                void entry.reload()
              }}
            />
          }
        />
        <Route
          path="fassungen"
          element={<VersionsPanel org={org.id} call={c} entry={entry.data ?? null} />}
        />
      </Routes>
    </section>
  )
}

// --- Meldung zusammenstellen ---
