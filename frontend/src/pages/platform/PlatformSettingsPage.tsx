import { useState } from 'react'
import type { FormEvent } from 'react'
import { displayName, platformApi } from '../../api/orgs.ts'
import type { PlatformSettings } from '../../api/orgs.ts'
import { Alert, Checkbox, Field, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { errorMessage, formatDate, useForm, useLoad } from '../../components/forms.ts'
import { peeringApi } from '../../api/peering.ts'
import type { InstanceKeys, PendingPeerKeys } from '../../api/peering.ts'
import { Why } from '../../learning/Aids.tsx'
import { t, tn } from '../../i18n/index.ts'
import { confirmDialog } from '../../components/dialog.ts'

export function PlatformSettingsPage() {
  const { data, error, setData } = useLoad(() => platformApi.settings(), [])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <div className="stack">
      <SettingsForm settings={data} onSaved={setData} />
      <AddressesCard />
    </div>
  )
}

/**
 * Weitere Adressen der Instanz je Einheit (White Label W7): Wer HUBIplan über eine
 * solche Adresse aufruft, sieht Name, Farben, Wappen und Symbol der Einheit.
 */
function AddressesCard() {
  const list = useLoad(() => platformApi.addresses(), [])
  const orgs = useLoad(() => platformApi.orgs(), [])
  const [hostname, setHostname] = useState('')
  const [organization, setOrganization] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function add(e: FormEvent) {
    e.preventDefault()
    if (!hostname.trim() || !organization) {
      setError(t('Bitte Adresse und Einheit angeben.'))
      return
    }
    setBusy(true)
    setError(null)
    try {
      await platformApi.addAddress(hostname.trim(), Number(organization))
      setHostname('')
      setOrganization('')
      await list.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number, host: string) {
    if (
      !(await confirmDialog({
        final: true,
        message: t('Adresse „{x}“ entfernen?', { x: host }),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    setBusy(true)
    setError(null)
    try {
      await platformApi.removeAddress(id)
      await list.reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Adressen je Einheit')}</h2>
      <p className="small">
        {t(
          'HUBIplan kann unter weiteren Adressen erreichbar sein. Wer eine solche Adresse aufruft, sieht auf der Anmeldeseite Name, Farben, Wappen und Symbol der zugeordneten Einheit; nach der Anmeldung ist sie vorausgewählt. Die Adresse muss per DNS auf diesen Server zeigen und beim Betrieb als erlaubte Adresse eingetragen sein.',
        )}
      </p>
      {list.error && <LoadError message={list.error} onRetry={() => void list.reload()} />}
      {list.data && list.data.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{t('Adresse')}</th>
              <th scope="col">{t('Einheit')}</th>
              <th scope="col">
                <span className="sr-only">{t('Aktionen')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {list.data.map((a) => (
              <tr key={a.id}>
                <td>{a.hostname}</td>
                <td>{a.organization_name}</td>
                <td>
                  <button
                    type="button"
                    className="button button-ghost"
                    disabled={busy}
                    onClick={() => void remove(a.id, a.hostname)}
                  >
                    {t('Entfernen')}
                    <span className="sr-only"> {a.hostname}</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {list.data && list.data.length === 0 && (
        <p className="muted">{t('Noch keine weiteren Adressen.')}</p>
      )}
      <form onSubmit={add} className="stack">
        <div className="grid-2">
          <Field
            label={t('Adresse')}
            value={hostname}
            placeholder={t('z. B. mitglieder.verein.example')}
            onChange={(e) => setHostname(e.target.value)}
          />
          <SelectField
            label={t('Einheit')}
            value={organization}
            onChange={(e) => setOrganization(e.target.value)}
          >
            <option value="">{t('Bitte wählen')}</option>
            {(orgs.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {displayName(o)}
              </option>
            ))}
          </SelectField>
        </div>
        {error && <Alert kind="error">{error}</Alert>}
        <div>
          <button type="submit" className="button button-primary" disabled={busy}>
            {t('Adresse hinzufügen')}
          </button>
        </div>
      </form>
    </div>
  )
}

function SettingsForm({
  settings,
  onSaved,
}: {
  settings: PlatformSettings
  onSaved: (s: PlatformSettings) => void
}) {
  const form = useForm(settings)
  async function save(e: FormEvent) {
    e.preventDefault()
    const saved = await form.submit(() => platformApi.updateSettings(form.values))
    if (saved) onSaved(saved as PlatformSettings)
  }
  return (
    <form className="card card-wide" onSubmit={save}>
      <h2>{t('Einstellungen der Plattform')}</h2>
      <SelectField
        label={t('Personendaten bei Mitgliedschaft in mehreren Einheiten')}
        value={form.values.person_data_mode}
        error={form.errors.person_data_mode}
        onChange={(e) =>
          form.set('person_data_mode', e.target.value as PlatformSettings['person_data_mode'])
        }
      >
        <option value="shared">
          {t('gemeinsam gepflegt (eine Änderung gilt für alle Einheiten)')}
        </option>
        <option value="per_club">{t('eigene Kopie je Einheit')}</option>
      </SelectField>
      <Why k="person_data_mode" />
      <Field
        label={t('Löschfrist nach Austritt (Monate)')}
        type="number"
        min={1}
        max={600}
        value={form.values.deletion_period_months}
        error={form.errors.deletion_period_months}
        hint={t('Danach bleibt nur ein Minimum: Name, Geburtsdatum, Verbandsnummer und Zeiträume.')}
        onChange={(e) => form.set('deletion_period_months', Number(e.target.value))}
      />
      <Field
        label={t('Speicher für Webseitenbilder je Einheit (MB)')}
        type="number"
        min={0}
        value={form.values.website_image_quota_mb ?? 2048}
        error={form.errors.website_image_quota_mb}
        hint={t('0 heißt ohne Grenze. Gilt für Bilder der Webseite, nicht für Dokumente.')}
        onChange={(e) => form.set('website_image_quota_mb', Number(e.target.value))}
      />
      {settings.deletion_shorter_from && (
        <Alert kind="info">
          {t(
            'Die kürzere Frist gilt erst ab {x}. Bis dahin wird weiter nach {n} Monaten gelöscht, damit ein Versehen auffällt, bevor Daten weg sind.',
            {
              x: formatDate(settings.deletion_shorter_from),
              n: settings.deletion_period_effective ?? settings.deletion_period_months,
            },
          )}
        </Alert>
      )}
      <Why k="deletion_period" />
      <h3>{t('Verbund mit anderen HUBIplan-Instanzen')}</h3>
      <Checkbox
        label={t('Einheiten dürfen sich mit Einheiten auf anderen Instanzen koppeln')}
        checked={form.values.peering_enabled}
        onChange={(v) => form.set('peering_enabled', v)}
        hint={t('Aus: alles bleibt wie bisher auf dieser Instanz.')}
      />
      {form.values.peering_enabled && (
        <>
          <label className="field">
            <span>{t('Erlaubte Instanzen (eine Domain je Zeile, leer = alle)')}</span>
            <textarea
              rows={3}
              value={form.values.peering_allowed_hosts}
              onChange={(e) => form.set('peering_allowed_hosts', e.target.value)}
            />
          </label>
          {!form.values.peering_allowed_hosts.trim() && (
            <Alert kind="info">
              {t(
                'Die Liste ist leer: Jede HUBIplan-Instanz kann sich mit einem Kopplungscode koppeln. Für den Echtbetrieb besser nur die Instanzen eintragen, mit denen ihr wirklich zusammenarbeitet.',
              )}
            </Alert>
          )}
          <Checkbox
            label={t('Anmelden mit dem Zugang einer gekoppelten Instanz erlauben')}
            checked={form.values.peering_login}
            onChange={(v) => form.set('peering_login', v)}
            hint={t(
              'Nur nach eigener Verknüpfung unter Mein Konto; Rechte vergibt weiter diese Instanz. Plattformverwaltung meldet sich nie so an.',
            )}
          />
          <PeeringInstanceInfo />
        </>
      )}
      <p className="muted small">
        {t(
          'Das Erscheinungsbild der Plattform (Standard für alle) stellst du unter Einstellungen → Erscheinungsbild ein.',
        )}
      </p>
      {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
      <button type="submit" className="button button-primary" disabled={form.busy}>
        {t('Speichern')}
      </button>
    </form>
  )
}

function PeeringInstanceInfo() {
  const { data, reload } = useLoad(() => peeringApi.platform(), [])
  if (!data) return null
  return (
    <>
      <p className="muted small">
        {t('Diese Instanz: {base_url} · Fingerabdruck', { base_url: data.instance.base_url })}{' '}
        <code>{data.instance.fingerprint}</code>{' '}
        {tn('· {n} Kopplung', '· {n} Kopplungen', data.couplings.length)}
      </p>
      {(data.pending_keys ?? []).map((p) => (
        <PeerKeysConfirm key={p.id} pending={p} onChange={reload} />
      ))}
      <InstanceKeysBox keys={data.keys} onChange={reload} />
    </>
  )
}

/** Notfallwechsel einer Gegenstelle bestätigen: nur die Plattform, gilt für alle (FQ-11). */
function PeerKeysConfirm({
  pending,
  onChange,
}: {
  pending: PendingPeerKeys
  onChange: () => void
}) {
  const [fingerprint, setFingerprint] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: 'confirm' | 'decline') {
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.peerKeys(pending.id, action, fingerprint)
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="move-confirm">
      <Alert kind="error">
        {pending.base_url}{' '}
        {t(
          'meldet einen Notfallwechsel der Schlüssel: Die alten wurden dort vermutlich gestohlen. Bis zur Bestätigung ruht der Austausch mit dieser Instanz',
        )}
        {pending.units.length > 0 && t(' (betrifft: {x0})', { x0: pending.units.join(', ') })}.
      </Alert>
      <p>
        {t('Neuer Fingerabdruck:')} <code>{pending.fingerprint}</code>
        {t(
          '. Lass ihn dir von der anderen Seite auf anderem Weg (Telefon) nennen und gib ihn hier ein. Wenn dort niemand von einem Notfall weiß: ablehnen. Die betroffenen Einheiten bekommen danach eine Mitteilung.',
        )}
      </p>
      <Field
        label={t('Fingerabdruck von der anderen Seite')}
        value={fingerprint}
        autoComplete="off"
        spellCheck={false}
        onChange={(e) => setFingerprint(e.target.value)}
      />
      {err && <Alert kind="error">{err}</Alert>}
      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          disabled={busy || !fingerprint.trim()}
          onClick={() => void run('confirm')}
        >
          {t('Neue Schlüssel bestätigen')}
        </button>
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => void run('decline')}
        >
          {t('Ablehnen')}
        </button>
      </div>
    </div>
  )
}

/** Schlüssel der Instanz wechseln: geplant oder im Notfall (Härtung H6). */
export function InstanceKeysBox({ keys, onChange }: { keys: InstanceKeys; onChange: () => void }) {
  const [mode, setMode] = useState<'planned' | 'emergency' | null>(null)
  const [word, setWord] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const needed = mode === 'emergency' ? 'NOTFALL' : 'WECHSELN'
  const unaware = keys.peers.filter((p) => !p.knows_current)

  async function rotate() {
    if (!mode) return
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.rotateKeys(mode, word)
      setMode(null)
      setWord('')
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="keys-box">
      <h4>{t('Schlüssel der Instanz')}</h4>
      <p className="muted small">
        {t('Zuletzt gewechselt:')} {formatDate(keys.rotated_at ?? keys.created)}
        {keys.next_rotation &&
          t(' · nächster automatischer Wechsel: {x}', { x: formatDate(keys.next_rotation) })}
        {keys.previous_until &&
          !keys.emergency &&
          t(' · alter Schlüssel gilt noch bis {x}', { x: formatDate(keys.previous_until) })}
      </p>
      {keys.emergency && keys.previous_until && (
        <Alert kind="info">
          {t(
            'Notfallwechsel: Die Plattformverwaltung jeder Partner-Instanz muss den neuen Fingerabdruck',
          )}{' '}
          <code>{keys.fingerprint}</code>{' '}
          {t('bestätigen. Teile ihn ihr auf anderem Weg (Telefon) mit.')}
        </Alert>
      )}
      {unaware.length > 0 && (
        <p className="muted small">
          {t('Kennen den aktuellen Schlüssel noch nicht:')}{' '}
          {unaware.map((p) => p.base_url).join(', ')}
        </p>
      )}
      {mode ? (
        <div className="keys-confirm">
          <p>
            {mode === 'emergency'
              ? t(
                  'Notfallwechsel, wenn der Server vermutlich gehackt wurde: Der alte Schlüssel gilt sofort nicht mehr, und jeder Partner muss den neuen Fingerabdruck bestätigen. Bis dahin ruht der Austausch.',
                )
              : t(
                  'Geplanter Wechsel: Die Partner übernehmen den neuen Schlüssel automatisch, der alte gilt noch 30 Tage.',
                )}{' '}
            {t('Zum Bestätigen bitte {word} eingeben.', { word: needed })}
          </p>
          <Field label={t('Bestätigung')} value={word} onChange={(e) => setWord(e.target.value)} />
          {err && <Alert kind="error">{err}</Alert>}
          <div className="button-row">
            <button
              type="button"
              className={mode === 'emergency' ? 'button button-danger' : 'button button-primary'}
              disabled={busy || word.trim().toUpperCase() !== needed}
              onClick={() => void rotate()}
            >
              {mode === 'emergency' ? t('Notfallwechsel ausführen') : t('Schlüssel wechseln')}
            </button>
            <button type="button" className="button" onClick={() => setMode(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      ) : (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setMode('planned')}>
            {t('Schlüssel wechseln')}
          </button>
          <button
            type="button"
            className="button button-danger"
            onClick={() => setMode('emergency')}
          >
            {t('Notfallwechsel …')}
          </button>
        </div>
      )}
    </div>
  )
}
