import { useState } from 'react'
import { levelsOf, peeringApi } from '../../api/peering.ts'
import type { Coupling, Levels } from '../../api/peering.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { InvoiceList } from './InvoiceList.tsx'
import { ReceivedInfo } from './ReceivedInfo.tsx'
import { RegisterCard } from './RegisterCard.tsx'
import { PacketToggles } from './PacketToggles.tsx'
import { TransferCard } from './TransferCard.tsx'

const KIND_LABELS: Record<string, string> = {
  get 'coupling.accept'() {
    return t('Kopplung bestätigt')
  },
  get 'coupling.config'() {
    return t('Freigaben geändert')
  },
  get 'coupling.end'() {
    return t('Kopplung gelöst')
  },
  get 'register.numbers'() {
    return t('Verbandsnummern')
  },
  get 'circular.forward'() {
    return t('Rundschreiben zur Weitergabe')
  },
  get 'circular.report'() {
    return t('Rückmeldung zum Rundschreiben')
  },
  get 'register.suggest'() {
    return t('Korrekturvorschlag')
  },
  get 'transfer.request'() {
    return t('Wechselanfrage')
  },
  get 'transfer.decision'() {
    return t('Entscheidung zum Wechsel')
  },
  get 'transfer.cancel'() {
    return t('Wechselanfrage zurückgezogen')
  },
  get 'invoice.issue'() {
    return t('Rechnung')
  },
  get 'invoice.cancel'() {
    return t('Rechnung storniert')
  },
  get 'invoice.status'() {
    return t('Zahlungsstand')
  },
  get 'invoice.paid'() {
    return t('als bezahlt gemeldet')
  },
}

function kindLabel(kind: string, coupling: Coupling): string {
  if (KIND_LABELS[kind]) return KIND_LABELS[kind]
  const key = kind.replace(/^packet\./, '')
  const packet =
    coupling.send.find((p) => p.key === key) ?? coupling.receive.find((p) => p.key === key)
  return packet ? packet.label.replace(/ \(.*\)$/, '') : kind
}

export function CouplingCard({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const org = useActiveOrg()
  const [levels, setLevels] = useState<Levels>(levelsOf(coupling.send))
  const [details, setDetails] = useState<Coupling | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const above = coupling.direction === 'parent'

  async function run(fn: () => Promise<unknown>) {
    setErr(null)
    setBusy(true)
    try {
      await fn()
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function end() {
    const ok = await confirmDialog({
      final: true,
      message: t(
        'Kopplung mit „{name}“ lösen? Übermittelte Kopien werden auf beiden Seiten entfernt; Rechnungen bleiben.',
        { name: coupling.remote.name },
      ),
      confirmLabel: t('Lösen'),
    })
    if (ok) await run(() => peeringApi.end(org.id, coupling.id))
  }

  const changed = JSON.stringify(levels) !== JSON.stringify(levelsOf(coupling.send))
  return (
    <div className="card card-wide">
      <h3>
        {coupling.remote.name}{' '}
        <span className="muted small">
          ({above ? t('Einheit darüber') : t('Einheit darunter')} · {coupling.state_label})
        </span>
      </h3>
      <p className="muted small">
        {coupling.remote.base_url}
        {coupling.remote.country &&
          t(' · Server in {country}', { country: coupling.remote.country })}{' '}
        {t('· Fingerabdruck')} <code>{coupling.remote.fingerprint}</code>
        <br />
        {coupling.last_contact_at
          ? t('Zuletzt Kontakt {x}', { x: formatDateTime(coupling.last_contact_at) })
          : t('Noch kein Kontakt')}
        {coupling.last_sync_at &&
          t(' · abgeglichen {x}', { x: formatDateTime(coupling.last_sync_at) })}
        {coupling.queued > 0 && t(' · {queued} Paket(e) warten', { queued: coupling.queued })}
      </p>
      {coupling.reception_budget?.initialized && (
        <p className="muted small">
          {t(
            'Empfangsreservierung: {mib} MiB und {count} Nachrichten. Änderungen von Ständen zählen mit.',
            {
              mib: Math.ceil(coupling.reception_budget.bytes / 1024 / 1024),
              count: coupling.reception_budget.messages,
            },
          )}
        </p>
      )}
      {coupling.error_since && (
        <Alert kind="error">
          {t(
            'Seit {x} nicht zustellbar: {last_error}. Die Pakete werden automatisch nachgeschickt.',
            { x: formatDateTime(coupling.error_since), last_error: coupling.last_error },
          )}
        </Alert>
      )}
      {(coupling.organizations_withheld ?? 0) > 0 && (
        <Alert kind="info">
          {t(
            'Gegenstelle zu alt für Organisationsmitglieder: {n} Organisationen gehen nicht mit, bis die andere Instanz aktualisiert ist.',
            { n: coupling.organizations_withheld ?? 0 },
          )}
        </Alert>
      )}
      {coupling.state === 'pending' && (
        <Alert kind="info">
          {coupling.remote.name}{' '}
          {t(
            'möchte sich unter {name} koppeln. Prüfe Adresse und Fingerabdruck mit der anderen Seite.',
            { name: org.name },
          )}
        </Alert>
      )}
      {coupling.state === 'requested' && (
        <Alert kind="info">
          {t('Angefragt. Die andere Seite muss die Kopplung noch bestätigen.')}
        </Alert>
      )}
      {coupling.state === 'moving' && coupling.move && (
        <MoveConfirm coupling={coupling} onChange={onChange} />
      )}
      {coupling.keys && <KeysPending coupling={coupling} />}
      {coupling.wants_more.length > 0 && <MoreWanted coupling={coupling} onChange={onChange} />}
      <PacketToggles
        choices={coupling.send}
        levels={levels}
        onChange={setLevels}
        disabled={busy || coupling.state === 'requested'}
      />
      <p className="muted small">
        {t('Die andere Seite gibt frei:')}{' '}
        {coupling.receive
          .filter((r) => r.value)
          .map((r) => r.label)
          .join(', ') || t('nichts')}
        .
      </p>
      <ReceivedInfo coupling={coupling} />
      {coupling.register && <RegisterCard coupling={coupling} onChange={onChange} />}
      <CircularsInfo coupling={coupling} onChange={onChange} />
      {above &&
        coupling.state === 'active' &&
        coupling.send.some((p) => p.key === 'members' && p.value === 'b') && (
          <TransferCard coupling={coupling} onChange={onChange} />
        )}
      {coupling.invoices?.length > 0 && <InvoiceList coupling={coupling} onChange={onChange} />}
      {(coupling.hidden?.length ?? 0) > 0 && (
        <p className="muted small">
          {t('Ausgeblendet, weil dir das Recht fehlt:')}{' '}
          {coupling
            .hidden!.map((h) =>
              h === 'names'
                ? t('Namen bei Klärfällen und Wechseln (Mitglieder ansehen)')
                : t('Eingangsrechnungen (Beiträge/Rechnungen ansehen)'),
            )
            .join('; ')}
          .
        </p>
      )}
      {err && <Alert kind="error">{err}</Alert>}
      <div className="button-row">
        {coupling.state === 'pending' && (
          <>
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                void run(() => peeringApi.action(org.id, coupling.id, 'accept', levels))
              }
            >
              {t('Bestätigen')}
            </button>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void run(() => peeringApi.action(org.id, coupling.id, 'decline'))}
            >
              {t('Ablehnen')}
            </button>
          </>
        )}
        {changed && coupling.state !== 'pending' && (
          <button
            type="button"
            className="button button-primary"
            disabled={busy}
            onClick={() => void run(() => peeringApi.setPackets(org.id, coupling.id, levels))}
          >
            {t('Freigaben speichern')}
          </button>
        )}
        {coupling.state === 'active' && (
          <>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void run(() => peeringApi.action(org.id, coupling.id, 'sync'))}
            >
              {t('Jetzt abgleichen')}
            </button>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void run(() => peeringApi.action(org.id, coupling.id, 'pause'))}
            >
              {t('Pausieren')}
            </button>
          </>
        )}
        {coupling.state === 'paused' && (
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => void run(() => peeringApi.action(org.id, coupling.id, 'resume'))}
          >
            {t('Fortsetzen')}
          </button>
        )}
        {coupling.state !== 'pending' && coupling.state !== 'moving' && (
          <button
            type="button"
            className="button button-danger"
            disabled={busy}
            onClick={() => void end()}
          >
            {t('Lösen')}
          </button>
        )}
        <button
          type="button"
          className="button"
          onClick={() =>
            details
              ? setDetails(null)
              : void peeringApi
                  .detail(org.id, coupling.id)
                  .then(setDetails, (e) => setErr(errorMessage(e)))
          }
        >
          {details ? t('Datenfluss ausblenden') : t('Datenfluss anzeigen')}
        </button>
      </div>
      {details?.messages && (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Zeit')}</th>
              <th>{t('Richtung')}</th>
              <th>{t('Inhalt')}</th>
              <th>{t('Personen')}</th>
              <th>{t('Stand')}</th>
            </tr>
          </thead>
          <tbody>
            {details.messages.map((m) => (
              <tr key={`${m.direction}-${m.seq}-${m.created_at}`}>
                <td>{formatDateTime(m.created_at)}</td>
                <td>{m.direction === 'out' ? t('gesendet') : t('empfangen')}</td>
                <td>{kindLabel(m.kind, coupling)}</td>
                <td>{m.persons || '–'}</td>
                <td>
                  {m.state_label}
                  {m.last_error && <span className="muted small"> · {m.last_error}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function MoveConfirm({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const org = useActiveOrg()
  const [fingerprint, setFingerprint] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const move = coupling.move!

  async function run(fn: () => Promise<unknown>) {
    setErr(null)
    setBusy(true)
    try {
      await fn()
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="move-confirm">
      {move.import ? (
        <Alert kind="info">
          {t('Die Kopplung mit {x0} kam mit der Vereinsdatei. Gegenstelle:', {
            x0: coupling.remote.name,
          })}{' '}
          <strong>{move.base_url}</strong>
          {move.country && t(' (Server in {x0})', { x0: move.country })}
          {t(
            '. Bis zur Bestätigung ruht die Kopplung, es gehen keine Daten hinaus und keine herein.',
          )}
        </Alert>
      ) : (
        <Alert kind="info">
          {coupling.remote.name} {t('meldet einen Umzug von')} <strong>{move.from}</strong>{' '}
          {t('nach')} <strong>{move.base_url}</strong>
          {move.country && t(' (Server in {x0})', { x0: move.country })}
          {t('. Bis zur Bestätigung ruht die Kopplung, es gehen keine Daten hinaus.')}
        </Alert>
      )}
      <p>
        {move.import
          ? t('Fingerabdruck der anderen Instanz:')
          : t('Fingerabdruck der neuen Instanz:')}{' '}
        <code>{move.fingerprint}</code>
        {move.import
          ? t(
              '. Lass ihn dir von der anderen Seite auf anderem Weg (Telefon, Mail) nennen und gib ihn hier ein. Kennt die andere Seite diese Kopplung nicht: ablehnen.',
            )
          : t(
              '. Lass ihn dir von der anderen Seite auf anderem Weg (Telefon, Mail) nennen und gib ihn hier ein. Wenn ihr nichts von einem Umzug wisst: ablehnen.',
            )}
      </p>
      <label className="field">
        <span>{t('Fingerabdruck von der anderen Seite')}</span>
        <input
          value={fingerprint}
          onChange={(e) => setFingerprint(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      {err && <Alert kind="error">{err}</Alert>}
      <div className="button-row">
        <button
          type="button"
          className="button button-primary"
          disabled={busy || !fingerprint.trim()}
          onClick={() => void run(() => peeringApi.confirmMove(org.id, coupling.id, fingerprint))}
        >
          {move.import ? t('Kopplung bestätigen') : t('Umzug bestätigen')}
        </button>
        <button
          type="button"
          className="button button-danger"
          disabled={busy}
          onClick={() => void run(() => peeringApi.action(org.id, coupling.id, 'move-decline'))}
        >
          {t('Ablehnen und Kopplung lösen')}
        </button>
      </div>
    </div>
  )
}

/** Gegenseite möchte mehr senden, als hier beim Koppeln angenommen wurde (Härtung H4). */
function MoreWanted({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const org = useActiveOrg()
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function decide(key: string, accept: boolean) {
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.decideMore(org.id, coupling.id, key, accept)
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="move-confirm">
      <Alert kind="info">
        {coupling.remote.name}{' '}
        {t(
          'möchte mehr senden, als ihr beim Koppeln angenommen habt. Bis ihr zustimmt, nimmt HUBIplan nur die bisherige Stufe an.',
        )}
      </Alert>
      <ul className="plain-list">
        {coupling.wants_more.map((w) => (
          <li key={w.key}>
            <strong>{w.label}</strong>: {w.level_label} {t('(bisher')} {w.accepted_label})
            {w.personal && <span className="muted small"> · {w.personal}</span>}
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={() => void decide(w.key, true)}
              >
                {t('Annehmen')}
              </button>
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => void decide(w.key, false)}
              >
                {t('Ablehnen')}
              </button>
            </div>
          </li>
        ))}
      </ul>
      <p className="muted small">
        {t('Nach dem Annehmen kommen die Daten spätestens beim täglichen Abgleich.')}
      </p>
      {err && <Alert kind="error">{err}</Alert>}
    </div>
  )
}

/** Notfallwechsel der Schlüssel einer Gegenstelle: bestätigt die Plattformverwaltung (FQ-11). */
function KeysPending({ coupling }: { coupling: Coupling }) {
  const keys = coupling.keys!
  return (
    <div className="move-confirm">
      <Alert kind="error">
        {coupling.remote.base_url}{' '}
        {t(
          'meldet einen Notfallwechsel der Schlüssel: Die alten wurden dort vermutlich gestohlen. Bis zur Bestätigung ruht der Austausch mit dieser Instanz.',
        )}
      </Alert>
      <p>
        {t('Neuer Fingerabdruck:')} <code>{keys.fingerprint}</code>
        {t(
          '. Den Wechsel prüft und bestätigt die Plattformverwaltung dieser HUBIplan-Instanz, weil er für alle Kopplungen mit dieser Instanz gilt. Ihr bekommt danach eine Mitteilung. Wisst ihr von keinem Notfall bei der anderen Seite, sagt bitte der Plattformverwaltung Bescheid.',
        )}
      </p>
    </div>
  )
}

function CircularsInfo({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const org = useActiveOrg()
  const above = coupling.direction === 'parent'
  const receives = coupling.receive.some((r) => r.key === 'circulars' && r.value)
  const [err, setErr] = useState<string | null>(null)
  if (!coupling.circulars?.length && !(above && receives)) return null

  async function toggle(value: boolean) {
    setErr(null)
    try {
      await peeringApi.setOptions(org.id, coupling.id, { circulars_auto: value })
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    }
  }

  return (
    <div>
      <h4>
        {t('Rundschreiben')}{' '}
        {above ? t('von {name}', { name: coupling.remote.name }) : t('zur Weitergabe')}
      </h4>
      {above && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={!!coupling.options?.circulars_auto}
            onChange={(e) => void toggle(e.target.checked)}
          />{' '}
          {t('Automatisch an die eigenen Mitglieder weitergeben (sonst als Entwurf zum Prüfen)')}
        </label>
      )}
      {coupling.circulars.length > 0 && (
        <ul className="plain-list">
          {coupling.circulars.map((c) => (
            <li key={c.id}>
              {formatDate(c.created_at)} · {c.subject} · {c.status_label}
              {c.status === 'sent' &&
                t(' · {x} Mails versandt', { x: c.report.sent ?? 0 }) +
                  (c.report.failed
                    ? t(', {failed} fehlgeschlagen', { failed: c.report.failed })
                    : '') +
                  (c.report.letter ? t(', {letter} Briefe', { letter: c.report.letter }) : '')}
            </li>
          ))}
        </ul>
      )}
      {err && <Alert kind="error">{err}</Alert>}
    </div>
  )
}
