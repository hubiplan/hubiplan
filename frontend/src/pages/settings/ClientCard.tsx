import { useState } from 'react'
import { nextcloudApi } from '../../api/nextcloud.ts'
import type { NextcloudClient, NextcloudInput, NextcloudRoleChoice } from '../../api/nextcloud.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { formatDayTime } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { GroupStatus } from './GroupStatus.tsx'
import { AccountList } from './AccountList.tsx'
import { RetentionFields } from './RetentionFields.tsx'

function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="field">
      <span>{label}</span>
      <div className="button-row">
        <code className="break-all">{value}</code>
        <button
          type="button"
          className="button"
          onClick={() => {
            void navigator.clipboard?.writeText(value).then(() => setCopied(true))
          }}
        >
          {copied ? t('Kopiert') : t('Kopieren')}
        </button>
      </div>
    </div>
  )
}

function groupsAsText(groups: Record<string, string[]>): Record<string, string> {
  return Object.fromEntries(Object.entries(groups ?? {}).map(([id, g]) => [id, g.join(', ')]))
}

// Gruppen je Rolle: z. B. „1. Kassierer“ und „2. Kassierer“ beide in „Kassierer“.
// An der Rolle (nicht am Namen) festgemacht, Umbenennen ändert nichts.
function RoleGroups({
  roles,
  value,
  onChange,
}: {
  roles: NextcloudRoleChoice[]
  value: Record<string, string>
  onChange: (v: Record<string, string>) => void
}) {
  if (!roles?.length) return null
  const mapped = Object.values(value).filter((g) => g.trim()).length
  return (
    <details className="small" open={mapped > 0}>
      <summary>
        {t('Gruppen für einzelne Rollen anpassen')}
        {mapped > 0 && ` (${mapped})`}
      </summary>
      <p className="muted small">
        {t(
          'Leer heißt: Die Rolle geht unter ihrem Namen an die Nextcloud (wenn „je Rolle eine Gruppe“ an ist). Mit Eintrag gehen stattdessen die genannten Gruppen mit, mehrere mit Komma, auch wenn „je Rolle eine Gruppe“ aus ist. So kommen etwa „1. Kassierer“ und „2. Kassierer“ beide in „Kassierer“. Umbenennen der Rolle ändert daran nichts.',
        )}
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{t('Rolle')}</th>
              <th>{t('Gruppen in der Nextcloud')}</th>
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => {
              const label = role.unit ? `${role.name} (${role.unit})` : role.name
              return (
                <tr key={role.id}>
                  <td>{label}</td>
                  <td>
                    <input
                      aria-label={t('Gruppen für {role}', { role: label })}
                      value={value[String(role.id)] ?? ''}
                      placeholder={label}
                      maxLength={300}
                      onChange={(e) => onChange({ ...value, [String(role.id)]: e.target.value })}
                    />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function CalendarStatus({
  org,
  client,
  onChanged,
}: {
  org: number
  client: NextcloudClient
  onChanged: (c: NextcloudClient) => void
}) {
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  if (!client.calendar_members && !client.calendar_board) return null

  async function run() {
    setMessage(null)
    setBusy(true)
    try {
      const r = await nextcloudApi.calendars(org, client.id)
      onChanged(r.client)
      const counts = [r.result.members, r.result.board]
      const sum = (k: 'written' | 'deleted') => counts.reduce((n, c) => n + (c?.[k] ?? 0), 0)
      setMessage(
        r.result.error
          ? { kind: 'error', text: r.result.error }
          : {
              kind: 'success',
              text: t('Geschrieben: {written}, gelöscht: {deleted}', {
                written: sum('written'),
                deleted: sum('deleted'),
              }),
            },
      )
    } catch (e) {
      setMessage({ kind: 'error', text: errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h3>{t('Kalender in der Nextcloud')}</h3>
      {client.calendar_error && <Alert kind="error">{client.calendar_error}</Alert>}
      <p className="muted small">
        {client.calendar_synced_at
          ? t('Zuletzt abgeglichen: {when}', { when: formatDayTime(client.calendar_synced_at) })
          : t('Noch nicht abgeglichen.')}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="button-row">
        <button type="button" className="button" disabled={busy} onClick={() => void run()}>
          {t('Kalender jetzt abgleichen')}
        </button>
      </div>
    </>
  )
}

export function ClientCard({
  org,
  isClub,
  client,
  secret,
  onChanged,
  onRemoved,
}: {
  org: number
  isClub: boolean
  client: NextcloudClient
  secret: string
  onChanged: (c: NextcloudClient) => void
  onRemoved: () => void
}) {
  const [values, setValues] = useState<NextcloudInput>({
    name: client.name,
    base_url: client.base_url,
    audience: client.audience,
    require_mfa: client.require_mfa,
    require_pkce: client.require_pkce ?? true,
    groups_board: client.groups_board,
    groups_roles: client.groups_roles,
    groups_units: client.groups_units,
    groups_members: client.groups_members,
    usernames: client.usernames,
    role_groups: groupsAsText(client.role_groups),
    manage_accounts: client.manage_accounts,
    service_user: client.service_user,
    service_password: '',
    account_group: client.account_group,
    calendar_members: client.calendar_members,
    calendar_members_group: client.calendar_members_group,
    calendar_board: client.calendar_board,
    calendar_board_group: client.calendar_board_group,
    sync_groups: client.sync_groups,
    sync_groups_list: client.sync_groups_list,
    files_enabled: client.files_enabled,
    files_root: client.files_root,
    files_board_group: client.files_board_group,
    files_finance_group: client.files_finance_group,
    files_members_group: client.files_members_group,
    files_retention: client.files_retention ?? {},
    files_source: client.files_source,
    talk_enabled: client.talk_enabled,
    talk_keep_days: client.talk_keep_days ?? 7,
    is_active: client.is_active,
  })
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const set = <K extends keyof NextcloudInput>(key: K, value: NextcloudInput[K]) => {
    setSaved(false)
    setValues((v) => ({ ...v, [key]: value }))
  }

  async function save() {
    setError(null)
    try {
      onChanged(await nextcloudApi.update(org, client.id, values))
      setValues((v) => ({ ...v, service_password: '' }))
      setSaved(true)
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  async function renew() {
    if (
      !(await confirmDialog({
        final: true,
        title: t('Neues Geheimnis erzeugen?'),
        message: t(
          'Das bisherige Geheimnis gilt sofort nicht mehr. Bis das neue in der Nextcloud eingetragen ist, kann sich dort niemand mit HUBIplan anmelden.',
        ),
        confirmLabel: t('Neu erzeugen'),
      }))
    )
      return
    try {
      onChanged(await nextcloudApi.renewSecret(org, client.id))
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  async function remove() {
    if (
      !(await confirmDialog({
        final: false,
        title: t('Nextcloud-Anmeldung entfernen?'),
        message: t(
          'Danach kann sich niemand mehr mit dem HUBIplan-Konto bei dieser Nextcloud anmelden. Konten und Dateien in der Nextcloud bleiben.',
        ),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    try {
      await nextcloudApi.remove(org, client.id)
      onRemoved()
    } catch (e) {
      setError(errorMessage(e))
    }
  }

  return (
    <section className="card card-wide">
      <h2>
        {client.name} <span className="muted small">{client.base_url}</span>
      </h2>
      {!client.is_active && (
        <Alert kind="info">{t('Ausgeschaltet: Niemand kann sich anmelden.')}</Alert>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <Field
          label={t('Name')}
          value={values.name ?? ''}
          maxLength={100}
          onChange={(e) => set('name', e.target.value)}
        />
        <Field
          label={t('Adresse der Nextcloud')}
          type="url"
          value={values.base_url ?? ''}
          onChange={(e) => set('base_url', e.target.value)}
        />
        <SelectField
          label={t('Wer darf sich anmelden?')}
          value={values.audience}
          onChange={(e) => set('audience', e.target.value as NextcloudInput['audience'])}
          hint={t(
            'Zählt nur, was bei dieser Einheit gilt: aktive Rollen, Ämter in Untereinheiten und, falls gewählt, Mitglieder mit Zugang und laufender Mitgliedschaft. Wer austritt oder seine Rolle abgibt, kommt nicht mehr hinein.',
          )}
        >
          <option value="board">{t('Vorstand und Rollen (auch Ämter in Untereinheiten)')}</option>
          <option value="roles">
            {t('Nur Rollen dieser Einheit (ohne Ämter in Untereinheiten)')}
          </option>
          {isClub && <option value="members">{t('zusätzlich Mitglieder mit Zugang')}</option>}
        </SelectField>
        <Checkbox
          label={t('Nur mit Zwei-Faktor-Anmeldung')}
          checked={Boolean(values.require_mfa)}
          onChange={(v) => set('require_mfa', v)}
          hint={t('empfohlen, wenn in der Nextcloud Vorstandsunterlagen liegen')}
        />
        <Checkbox
          label={t('Nur mit PKCE (S256)')}
          checked={values.require_pkce !== false}
          onChange={(v) => set('require_pkce', v)}
          hint={t(
            'Schützt den Anmeldecode. Die Nextcloud-App „user_oidc“ nutzt PKCE von selbst; nur für ältere Anwendungen ohne PKCE ausschalten.',
          )}
        />
        <fieldset>
          <legend>{t('Gruppen in der Nextcloud')}</legend>
          <Checkbox
            label={t('„Vorstand“ für alle mit einer Vorstandsrolle')}
            checked={Boolean(values.groups_board)}
            onChange={(v) => set('groups_board', v)}
          />
          <Checkbox
            label={t('je Rolle eine Gruppe (z. B. „Kassierer“, „Zugführer (Jäger)“)')}
            checked={Boolean(values.groups_roles)}
            onChange={(v) => set('groups_roles', v)}
          />
          <Checkbox
            label={t('je Untereinheit eine Gruppe für ihre Mitglieder')}
            checked={Boolean(values.groups_units)}
            onChange={(v) => set('groups_units', v)}
          />
          <Checkbox
            label={t('„Mitglieder“ für alle mit laufender Mitgliedschaft')}
            checked={Boolean(values.groups_members)}
            onChange={(v) => set('groups_members', v)}
          />
          <RoleGroups
            roles={client.role_choices}
            value={values.role_groups ?? {}}
            onChange={(v) => set('role_groups', v)}
          />
        </fieldset>
        {(client.blocked_usernames ?? []).length > 0 && (
          <Alert kind="error">
            {t(
              'Diese Zeilen zeigen auf Verwaltungs- oder Dienstkonten der Nextcloud und werden nie zugeordnet. Bitte entfernen:',
            )}{' '}
            {(client.blocked_usernames ?? []).join('; ')}
          </Alert>
        )}
        <label className="field">
          <span>{t('Bisherige Benutzernamen in der Nextcloud')}</span>
          <textarea
            rows={4}
            placeholder="maria.muster@example.org = mmuster"
            value={values.usernames ?? ''}
            onChange={(e) => set('usernames', e.target.value)}
          />
          <small className="muted">
            {t(
              'Für Konten, die es in der Nextcloud schon gibt: je Zeile die Anmelde-E-Mail bei HUBIplan und der bisherige Benutzername. Wer hier steht, landet bei der ersten Anmeldung in seinem vorhandenen Konto mit allen Dateien. Wer fehlt, bekommt ein neues Konto. Nur eintragen, wenn es wirklich dieselbe Person ist.',
            )}
          </small>
        </label>
        <fieldset>
          <legend>{t('Konten automatisch deaktivieren')}</legend>
          <p className="muted small">
            {t(
              'Endet der Zugang bei HUBIplan (Rolle beendet, Austritt, Konto gesperrt), deaktiviert HUBIplan das Nextcloud-Konto sofort und prüft jede Nacht nach. Bekommt die Person wieder eine Rolle, wird es wieder aktiviert. Dateien bleiben erhalten. Angefasst werden nur Konten, die sich über HUBIplan angemeldet haben.',
            )}
          </p>
          <Field
            label={t('Gruppe der Konten über HUBIplan')}
            value={values.account_group ?? ''}
            maxLength={64}
            placeholder="HUBIplan"
            onChange={(e) => set('account_group', e.target.value)}
            hint={t(
              'Geht bei jeder Anmeldung mit. In der Nextcloud Gruppen-Provisionierung mit Whitelist nur für diese Gruppe einschalten.',
            )}
          />
          <Field
            label={t('Dienstkonto in der Nextcloud')}
            value={values.service_user ?? ''}
            maxLength={64}
            autoComplete="off"
            onChange={(e) => set('service_user', e.target.value)}
            hint={t('eigenes Konto, Gruppen-Admin der Gruppe oben')}
          />
          <Field
            label={t('App-Passwort des Dienstkontos')}
            type="password"
            autoComplete="new-password"
            value={values.service_password ?? ''}
            placeholder={client.has_service_password ? t('gespeichert') : ''}
            onChange={(e) => set('service_password', e.target.value)}
            hint={t(
              'wird verschlüsselt gespeichert und nie wieder angezeigt; leer lassen behält es',
            )}
          />
          <Checkbox
            label={t('Konten automatisch deaktivieren')}
            checked={Boolean(values.manage_accounts)}
            onChange={(v) => set('manage_accounts', v)}
          />
          <Why k="nextcloud_auto_disable" />
        </fieldset>
        <fieldset>
          <legend>{t('Gruppen laufend abgleichen')}</legend>
          <p className="muted small">
            {t(
              'Die Nextcloud setzt Gruppen sonst nur beim Anmelden. Sync-Apps melden sich nie neu an: Wer eine Rolle abgibt, behielte die Gruppe mit ihren Ordnern. Mit dem Abgleich setzt HUBIplan die Gruppen gleich nach jeder Änderung an Rollen, Ämtern oder Untereinheiten und jede Nacht. Verlören mehr als drei Konten auf einmal Gruppen, hält der Abgleich an, bis jemand ihn hier bestätigt.',
            )}
          </p>
          <Field
            label={t('Gruppen, die HUBIplan abgleicht')}
            value={values.sync_groups_list ?? ''}
            maxLength={500}
            placeholder={t('Vorstand, Mitglieder, Kassierer')}
            onChange={(e) => set('sync_groups_list', e.target.value)}
            hint={t(
              'mit Komma getrennt; dazu kommt immer die Gruppe der Konten über HUBIplan. Andere Gruppen (z. B. von Hand gepflegte Ordnergruppen) und „admin“ fasst HUBIplan nie an. Das Dienstkonto muss Gruppen-Admin jeder dieser Gruppen sein.',
            )}
          />
          <Checkbox
            label={t('Gruppen laufend abgleichen')}
            checked={Boolean(values.sync_groups)}
            onChange={(v) => set('sync_groups', v)}
            hint={t('vorher mit „Gruppen vergleichen“ unten prüfen, was sich ändern würde')}
          />
        </fieldset>
        <fieldset>
          <legend>{t('Dateien in der Nextcloud')}</legend>
          <p className="muted small">
            {t(
              'Mit „In Nextcloud ablegen“ erscheint neben Kassenbericht, Steuerauswertung, Kassenzählung, Protokollen, Beschlussbuch und Dokumenten ein Knopf, der die Datei in einen Ordner des Dienstkontos legt. Jeder Ordner ist nur zum Lesen an eine Gruppe freigegeben. Nach der Frist je Art löscht HUBIplan die Datei dort wieder (in den Papierkorb des Dienstkontos).',
            )}
          </p>
          {client.files_error && <Alert kind="error">{client.files_error}</Alert>}
          <Checkbox
            label={t('In Nextcloud ablegen')}
            checked={Boolean(values.files_enabled)}
            onChange={(v) => set('files_enabled', v)}
          />
          {values.files_enabled && (
            <>
              <Field
                label={t('Ordner im Dienstkonto')}
                value={values.files_root ?? ''}
                maxLength={100}
                placeholder="HUBIplan"
                onChange={(e) => set('files_root', e.target.value)}
                hint={t('darin die Ordner „Vorstand“, „Kasse“ und „Mitglieder“')}
              />
              <Field
                label={t('Ordner „Vorstand“: lesen darf die Gruppe')}
                value={values.files_board_group ?? ''}
                maxLength={64}
                onChange={(e) => set('files_board_group', e.target.value)}
              />
              <Field
                label={t('Ordner „Kasse“: lesen darf die Gruppe')}
                value={values.files_finance_group ?? ''}
                maxLength={64}
                onChange={(e) => set('files_finance_group', e.target.value)}
              />
              <Field
                label={t('Ordner „Mitglieder“: lesen darf die Gruppe')}
                value={values.files_members_group ?? ''}
                maxLength={64}
                onChange={(e) => set('files_members_group', e.target.value)}
                hint={t('leer: nur das Dienstkonto sieht den Ordner')}
              />
              <RetentionFields
                value={values.files_retention ?? {}}
                onChange={(v) => set('files_retention', v)}
              />
            </>
          )}
          <Field
            label={t('Ordner zum Übernehmen')}
            value={values.files_source ?? ''}
            maxLength={300}
            placeholder={t('An HUBIplan')}
            onChange={(e) => set('files_source', e.target.value)}
            hint={t(
              'Für „Aus Nextcloud“ beim Hochladen: einen Ordner in der Nextcloud an das Dienstkonto freigeben und hier seinen Namen eintragen, wie er beim Dienstkonto heißt. Wer in HUBIplan Dateien hochladen darf, sieht alles darin. Leer: aus.',
            )}
          />
        </fieldset>
        <fieldset>
          <legend>{t('Videoraum am Termin')}</legend>
          <p className="muted small">
            {t(
              'Am Termin erscheint „Videoraum anlegen“. HUBIplan legt dann im Dienstkonto ein Talk-Gespräch mit Link und Passwort an. Beides sehen alle, die den Termin sehen (auch in den Apps, in Einladung und Erinnerung und im Kalender der Nextcloud), nie die öffentliche Webseite. Ohne eigenen Videodienst der Nextcloud klappt Video nur mit wenigen Teilnehmern gut.',
            )}
          </p>
          <Checkbox
            label={t('Videoraum am Termin')}
            checked={Boolean(values.talk_enabled)}
            onChange={(v) => set('talk_enabled', v)}
            hint={t('braucht Talk in der Nextcloud und Dienstkonto mit App-Passwort')}
          />
          {values.talk_enabled && (
            <Field
              label={t('Raum löschen nach … Tagen')}
              type="number"
              min={0}
              max={90}
              value={String(values.talk_keep_days ?? 7)}
              onChange={(e) => set('talk_keep_days', Number(e.target.value || 0))}
              hint={t('gezählt ab dem Ende des Termins, bei Serien ab dem Ende der Wiederholung')}
            />
          )}
        </fieldset>
        <fieldset>
          <legend>{t('Termine in den Kalender der Nextcloud')}</legend>
          <p className="muted small">
            {t(
              'HUBIplan schreibt die Termine alle 15 Minuten in Kalender des Dienstkontos und gibt sie nur zum Lesen für eine Gruppe frei. Bearbeitet wird weiter in HUBIplan. Dafür reichen Dienstkonto und App-Passwort oben.',
            )}
          </p>
          <Checkbox
            label={t('Termine für Mitglieder')}
            checked={Boolean(values.calendar_members)}
            onChange={(v) => set('calendar_members', v)}
            hint={t('was jedes Mitglied der Einheit sieht, wie im Kalender-Abo')}
          />
          {values.calendar_members && (
            <Field
              label={t('Für diese Gruppe freigeben')}
              value={values.calendar_members_group ?? ''}
              maxLength={64}
              onChange={(e) => set('calendar_members_group', e.target.value)}
              hint={t('leer: nur das Dienstkonto sieht den Kalender')}
            />
          )}
          <Checkbox
            label={t('Termine „nur Vorstand“')}
            checked={Boolean(values.calendar_board)}
            onChange={(v) => set('calendar_board', v)}
            hint={t('wie im Vorstands-Abo; nur für eine Gruppe, in der allein der Vorstand ist')}
          />
          {values.calendar_board && (
            <Field
              label={t('Für diese Gruppe freigeben')}
              value={values.calendar_board_group ?? ''}
              maxLength={64}
              onChange={(e) => set('calendar_board_group', e.target.value)}
              hint={t('leer: nur das Dienstkonto sieht den Kalender')}
            />
          )}
        </fieldset>
        <Checkbox
          label={t('Eingeschaltet')}
          checked={Boolean(values.is_active)}
          onChange={(v) => set('is_active', v)}
        />
        {error && <Alert kind="error">{error}</Alert>}
        {saved && <Alert kind="success">{t('Gespeichert.')}</Alert>}
        <div className="button-row">
          <button type="submit" className="button button-primary">
            {t('Speichern')}
          </button>
        </div>
      </form>

      <AccountList org={org} client={client} onChanged={onChanged} />
      <GroupStatus org={org} client={client} onChanged={onChanged} />
      <CalendarStatus org={org} client={client} onChanged={onChanged} />

      <h3>{t('In der Nextcloud eintragen')}</h3>
      <p className="muted small">
        {t(
          'In der Nextcloud als Administrator die App „OpenID Connect user backend“ (user_oidc) installieren, dann unter Verwaltung › OpenID Connect einen Anbieter mit diesen Angaben anlegen. Dort „Gruppen-Provisionierung“ einschalten und als Gruppen-Zuordnung „groups“ eintragen. Für bisherige Benutzernamen: Benutzer-ID-Zuordnung „preferred_username“, „Eindeutige Benutzer-ID verwenden“ aus und in der config.php „soft_auto_provision“ an (siehe Anleitung).',
        )}
      </p>
      <Copyable label={t('Discovery-Endpunkt')} value={client.discovery_url} />
      <Copyable label={t('Client-ID')} value={client.client_id} />
      {secret ? (
        <>
          <Alert kind="info">
            {t(
              'Das Geheimnis wird nur jetzt angezeigt. Bitte gleich in der Nextcloud eintragen; HUBIplan speichert nur eine Prüfsumme.',
            )}
          </Alert>
          <Copyable label={t('Client-Geheimnis')} value={secret} />
        </>
      ) : (
        <p className="muted small">
          {t('Client-Geheimnis: nur beim Anlegen sichtbar. Vergessen? Dann ein neues erzeugen.')}
        </p>
      )}
      <Copyable label={t('Rückleitung (zur Kontrolle)')} value={client.redirect_uri} />
      <p className="muted small">
        {client.last_used_at
          ? t('Zuletzt benutzt: {when}', { when: formatDayTime(client.last_used_at) })
          : t('Noch nicht benutzt.')}
      </p>
      <div className="button-row">
        <button type="button" className="button" onClick={() => void renew()}>
          {t('Neues Geheimnis')}
        </button>
        <button type="button" className="button button-danger" onClick={() => void remove()}>
          {t('Entfernen')}
        </button>
      </div>
    </section>
  )
}
