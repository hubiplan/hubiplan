// Fremde Kalender: Termine aus Vereinsplaner oder einem iCal-Abo stündlich übernehmen.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { eventApi } from '../../api/events.ts'
import type {
  CalendarBase,
  EventCategory,
  ExternalCalendar,
  ExternalCalendarInput,
  ExternalKind,
  Visibility,
} from '../../api/events.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField, Loading } from '../../components/ui.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { formatDay } from '../../i18n/format.ts'
import { useTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'

type Message = { kind: 'error' | 'success'; text: string } | null

export function ExternalCalendarsPanel({ base }: { base: CalendarBase }) {
  const { data, error, reload } = useLoad(
    () => Promise.all([eventApi.externals(base), eventApi.categories(base)]),
    [base],
  )
  const [message, setMessage] = useState<Message>(null)

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  const [calendars, categories] = data
  return (
    <div className="stack">
      <div className="card card-wide stack-sm">
        <p className="muted small">
          {t(
            'Termine anderer Kalender erscheinen hier als Kopie, z. B. die des Dachverbands aus Vereinsplaner. HUBIplan holt sie stündlich ab. Ändern lassen sie sich nur im fremden Kalender; einzelne Termine kannst du hier ausblenden.',
          )}
        </p>
        {message && <Alert kind={message.kind}>{message.text}</Alert>}
      </div>
      {calendars.map((c) => (
        <ExternalCard
          key={c.id}
          base={base}
          cal={c}
          categories={categories}
          onChanged={reload}
          onMessage={setMessage}
        />
      ))}
      <AddExternal
        base={base}
        categories={categories}
        onAdded={async (cal) => {
          await reload()
          setMessage(
            cal.last_error
              ? {
                  kind: 'error',
                  text: t('Angelegt, aber der Abruf ging nicht: {error}', {
                    error: cal.last_error,
                  }),
                }
              : {
                  kind: 'success',
                  text: t('Angelegt. {n} Termine übernommen.', { n: cal.event_count }),
                },
          )
        }}
      />
    </div>
  )
}

function visibilityOptions() {
  const labels: Record<Visibility, string> = {
    public: t('nach außen öffentlich'),
    members: t('Mitglieder'),
    board: t('nur Vorstand'),
  }
  return (Object.keys(labels) as Visibility[]).map((v) => (
    <option key={v} value={v}>
      {labels[v]}
    </option>
  ))
}

function CategorySelect({
  categories,
  value,
  onChange,
  disabled,
}: {
  categories: EventCategory[]
  value: number | null
  onChange: (value: number | null) => void
  disabled?: boolean
}) {
  return (
    <SelectField
      label={t('Kategorie')}
      value={value ?? ''}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">{t('keine')}</option>
      {categories
        .filter((c) => c.is_active !== false || c.id === value)
        .map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
    </SelectField>
  )
}

function tokenLabel(kind: ExternalKind): string {
  return kind === 'vereinsplaner' ? t('API-Token (x-api-token)') : t('Link zum Kalender-Abo')
}

function AddExternal({
  base,
  categories,
  onAdded,
}: {
  base: CalendarBase
  categories: EventCategory[]
  onAdded: (cal: ExternalCalendar) => Promise<void>
}) {
  const tm = useTerms()
  const empty: ExternalCalendarInput = {
    name: '',
    kind: 'vereinsplaner',
    token: '',
    secret: '',
    category: null,
    visibility: 'members',
    share_down: true,
    is_active: true,
  }
  const [form, setForm] = useState(empty)
  const [busy, setBusy] = useState(false)
  const [fail, setFail] = useState<string | null>(null)

  function set<K extends keyof ExternalCalendarInput>(key: K, value: ExternalCalendarInput[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setFail(null)
    try {
      const cal = await eventApi.createExternal(base, form)
      setForm(empty)
      await onAdded(cal)
    } catch (err) {
      setFail(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card card-wide stack-sm" onSubmit={submit}>
      <h3>{t('Fremden Kalender hinzufügen')}</h3>
      {fail && <Alert kind="error">{fail}</Alert>}
      <div className="grid-2">
        <SelectField
          label={t('Art')}
          value={form.kind}
          onChange={(e) => set('kind', e.target.value as ExternalKind)}
        >
          <option value="vereinsplaner">Vereinsplaner</option>
          <option value="ical">{t('Kalender-Abo (iCal)')}</option>
        </SelectField>
        <Field
          label={t('Name')}
          required
          maxLength={80}
          placeholder={t('z. B. Dachverband')}
          value={form.name}
          onChange={(e) => set('name', e.target.value)}
        />
      </div>
      <Field
        label={tokenLabel(form.kind)}
        required
        autoComplete="off"
        value={form.token}
        hint={
          form.kind === 'vereinsplaner'
            ? t(
                'Das Token erzeugt der andere Verein in Vereinsplaner unter den Einstellungen der Schnittstelle. Es kommen nur Termine, die dort für die Schnittstelle freigegeben sind.',
              )
            : t(
                'Beginnt mit https:// oder webcal://, z. B. aus Google Kalender, Nextcloud oder einer anderen Vereinssoftware.',
              )
        }
        onChange={(e) => set('token', e.target.value)}
      />
      {form.kind === 'vereinsplaner' && (
        <Field
          label={t('API-Secret (nur bei privaten Tokens)')}
          autoComplete="off"
          value={form.secret}
          onChange={(e) => set('secret', e.target.value)}
        />
      )}
      <div className="grid-2">
        <CategorySelect
          categories={categories}
          value={form.category}
          onChange={(v) => set('category', v)}
        />
        <SelectField
          label={t('Sichtbarkeit')}
          value={form.visibility}
          onChange={(e) => set('visibility', e.target.value as Visibility)}
        >
          {visibilityOptions()}
        </SelectField>
      </div>
      <Checkbox
        label={t('An die {pl} weitergeben', { pl: tm.pl })}
        checked={form.share_down}
        onChange={(v) => set('share_down', v)}
      />
      <div>
        <button type="submit" className="button button-primary" disabled={busy}>
          {busy ? t('Ruft ab …') : t('Hinzufügen und abrufen')}
        </button>
      </div>
    </form>
  )
}

function ExternalCard({
  base,
  cal,
  categories,
  onChanged,
  onMessage,
}: {
  base: CalendarBase
  cal: ExternalCalendar
  categories: EventCategory[]
  onChanged: () => Promise<unknown>
  onMessage: (m: Message) => void
}) {
  const tm = useTerms()
  const [busy, setBusy] = useState(false)
  const [token, setToken] = useState('')

  async function run(action: () => Promise<unknown>, success?: string) {
    setBusy(true)
    onMessage(null)
    try {
      await action()
      await onChanged()
      if (success) onMessage({ kind: 'success', text: success })
    } catch (err) {
      onMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  const update = (data: Partial<ExternalCalendarInput>) =>
    run(() => eventApi.updateExternal(base, cal.id, data))

  return (
    <section className="card card-wide stack-sm" aria-label={cal.name}>
      <div className="card-head">
        <h3>
          {cal.name} <span className="badge">{cal.kind_label}</span>
        </h3>
      </div>
      {cal.last_error ? (
        <Alert kind="error">
          {t('Letzter Abruf ging nicht: {error}', { error: cal.last_error })}
          {cal.last_sync_at && (
            <p>{t('Letzter Abrufversuch: {when}.', { when: formatDateTime(cal.last_sync_at) })}</p>
          )}
          <p>
            {cal.last_successful_sync_at
              ? t('Letzter erfolgreicher Abruf: {when}. Die vorhandenen Kopien bleiben erhalten.', {
                  when: formatDateTime(cal.last_successful_sync_at),
                })
              : t('Letzter erfolgreicher Abruf unbekannt. Vorhandene Kopien können veraltet sein.')}
          </p>
          <p>
            {cal.stale_hidden
              ? t(
                  'Seit 14 Tagen kein erfolgreicher Abruf: Die Termine sind ausgeblendet und erscheinen wieder, sobald ein Abruf klappt.',
                )
              : t('Nach 14 Tagen ohne erfolgreichen Abruf werden die Termine ausgeblendet.')}
          </p>
        </Alert>
      ) : (
        <>
          <p className="muted small">
            {cal.last_successful_sync_at
              ? t('{n} Termine, zuletzt abgerufen {when}.', {
                  n: cal.event_count,
                  when: formatDateTime(cal.last_successful_sync_at),
                })
              : cal.last_sync_at
                ? t(
                    'Letzter erfolgreicher Abruf unbekannt. Vorhandene Kopien können veraltet sein.',
                  )
                : t('Noch nicht abgerufen.')}
          </p>
          {!cal.last_successful_sync_at && cal.last_sync_at && (
            <p className="muted small">
              {t('Letzter Abrufversuch: {when}.', { when: formatDateTime(cal.last_sync_at) })}
            </p>
          )}
        </>
      )}
      <fieldset disabled={busy} className="stack-sm">
        <div className="grid-2">
          <CategorySelect
            categories={categories}
            value={cal.category?.id ?? null}
            onChange={(v) => void update({ category: v })}
          />
          <SelectField
            label={t('Sichtbarkeit')}
            value={cal.visibility}
            onChange={(e) => void update({ visibility: e.target.value as Visibility })}
          >
            {visibilityOptions()}
          </SelectField>
        </div>
        <Checkbox
          label={t('An die {pl} weitergeben', { pl: tm.pl })}
          checked={cal.share_down}
          onChange={(v) => void update({ share_down: v })}
        />
        <Checkbox
          label={t('Abruf aktiv')}
          hint={t('aus: die übernommenen Termine verschwinden')}
          checked={cal.is_active}
          onChange={(v) => void update({ is_active: v })}
        />
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            if (!token.trim()) return
            void run(async () => {
              await eventApi.updateExternal(base, cal.id, { token })
              setToken('')
            }, t('Gespeichert.'))
          }}
        >
          <Field
            label={
              cal.kind === 'vereinsplaner' ? t('Neues API-Token') : t('Neuer Link zum Kalender-Abo')
            }
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <button type="submit" className="button">
            {t('Ersetzen')}
          </button>
        </form>
        <div className="button-row">
          <button
            type="button"
            className="button button-primary"
            disabled={!cal.is_active}
            onClick={() => void run(() => eventApi.syncExternal(base, cal.id))}
          >
            {t('Jetzt abrufen')}
          </button>
          <button
            type="button"
            className="button button-danger"
            onClick={async () => {
              if (
                await confirmDialog({
                  title: t('Fremden Kalender „{name}“ entfernen?', { name: cal.name }),
                  message: t('Alle übernommenen Termine verschwinden aus dem Kalender.'),
                  confirmLabel: t('Entfernen'),
                })
              ) {
                void run(
                  () => eventApi.removeExternal(base, cal.id),
                  t('Der fremde Kalender wurde entfernt.'),
                )
              }
            }}
          >
            {t('Entfernen')}
          </button>
        </div>
      </fieldset>
      {cal.hidden.length > 0 && (
        <div className="stack-sm">
          <strong>{t('Ausgeblendete Termine')}</strong>
          <ul className="plain-list">
            {cal.hidden.map((h) => (
              <li key={h.key}>
                {h.title} <span className="muted small">{formatDay(h.starts_at)}</span>{' '}
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
                  onClick={() => void run(() => eventApi.showExternal(base, cal.id, h.key))}
                >
                  {t('wieder zeigen')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
