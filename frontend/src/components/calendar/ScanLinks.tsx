// Scan-Links für Personal ohne Konto (Anmeldung A6, Konzept 3.11): Der Link öffnet auf dem
// Handy nur den Kartenscanner, für den Einlass oder für eine Zusatzleistung wie das Essen.
import { useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import type { CalendarBase } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { ScanLink } from '../../api/registrations.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, Loading, SelectField } from '../ui.tsx'
import { confirmDialog } from '../dialog.ts'
import { t } from '../../i18n/index.ts'

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function LinkRow({ link, onRevoke }: { link: ScanLink; onRevoke: (link: ScanLink) => void }) {
  const [qr, setQr] = useState(false)
  const [note, setNote] = useState('')
  async function copy() {
    if (!link.url) return
    try {
      await navigator.clipboard.writeText(link.url)
      setNote(t('Link kopiert.'))
    } catch {
      setNote(t('Kopieren ging nicht. Bitte den Link markieren.'))
    }
  }
  return (
    <li className="stack-sm">
      <div>
        <strong>{link.label}</strong> · {link.station}{' '}
        <span className="muted small">
          {link.revoked
            ? t('gesperrt')
            : link.active
              ? t('gültig bis {when}', { when: when(link.expires_at) })
              : t('abgelaufen')}
          {' · '}
          {t('{n} Scans', { n: link.scans })}
          {link.allow_search && ` · ${t('mit Namenssuche')}`}
        </span>
      </div>
      {link.active && link.url && (
        <>
          <div className="button-row">
            <button type="button" className="button button-ghost small" onClick={() => void copy()}>
              {t('Link kopieren')}
            </button>
            <button
              type="button"
              className="button button-ghost small"
              aria-pressed={qr}
              onClick={() => setQr(!qr)}
            >
              {qr ? t('QR-Code ausblenden') : t('QR-Code zeigen')}
            </button>
            <button
              type="button"
              className="button button-ghost small"
              onClick={() => onRevoke(link)}
            >
              {t('Sperren')}
            </button>
          </div>
          {note && <span className="muted small">{note}</span>}
          {qr && (
            <QRCodeSVG
              value={link.url}
              size={200}
              marginSize={2}
              title={t('QR-Code für {label}', { label: link.label })}
            />
          )}
        </>
      )}
    </li>
  )
}

export function ScanLinksPanel({ base, eventId }: { base: CalendarBase; eventId: number }) {
  const { data, error, reload } = useLoad(
    () => registrationApi.scanLinks(base, eventId),
    [base, eventId],
  )
  const [label, setLabel] = useState('')
  const [station, setStation] = useState('')
  const [allowSearch, setAllowSearch] = useState(false)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)

  async function add() {
    setBusy(true)
    setFailed(null)
    try {
      await registrationApi.addScanLink(base, eventId, {
        label: label.trim(),
        addon: station.startsWith('a') ? Number(station.slice(1)) : null,
        material:
          station.startsWith('m') || station.startsWith('r') ? Number(station.slice(1)) : null,
        material_return: station.startsWith('r'),
        allow_search: allowSearch,
      })
      setLabel('')
      await reload()
    } catch (e) {
      setFailed(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function revoke(link: ScanLink) {
    const ok = await confirmDialog({
      final: false,
      title: t('Scan-Link „{label}“ sperren?', { label: link.label }),
      confirmLabel: t('Sperren'),
    })
    if (!ok) return
    try {
      await registrationApi.revokeScanLink(base, eventId, link.id)
      await reload()
    } catch (e) {
      setFailed(errorMessage(e))
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  return (
    <div className="stack">
      <p className="muted small">
        {t(
          'Wer den Link auf dem Handy oder Tablet öffnet, kann nur Eintrittskarten scannen, ohne Konto und ohne Teilnehmerliste. Angezeigt werden Gültigkeit, Name und Geburtsdatum zum Abgleich mit dem Ausweis, Tarif, gebuchte Leistungen und ob die Karte schon gescannt wurde. Der Link gilt bis zum Tag nach der Veranstaltung und lässt sich jederzeit sperren.',
        )}
      </p>
      {data.links.length > 0 && (
        <ul className="plain-list stack">
          {data.links.map((link) => (
            <LinkRow key={link.id} link={link} onRevoke={(l) => void revoke(l)} />
          ))}
        </ul>
      )}
      {failed && <Alert kind="error">{failed}</Alert>}
      <form
        className="stack-sm"
        onSubmit={(e) => {
          e.preventDefault()
          void add()
        }}
      >
        <Field
          label={t('Bezeichnung')}
          hint={t('z. B. Eingang Nord oder Essensausgabe')}
          value={label}
          maxLength={100}
          onChange={(e) => setLabel(e.target.value)}
        />
        <SelectField
          label={t('Station')}
          value={station}
          onChange={(e) => setStation(e.target.value)}
        >
          <option value="">{t('Einlass')}</option>
          {data.addons.map((a) => (
            <option key={`a${a.id}`} value={`a${a.id}`}>
              {a.name}
            </option>
          ))}
          {data.materials.map((m) => (
            <option key={`m${m.id}`} value={`m${m.id}`}>
              {t('Ausgabe: {name}', { name: m.name })}
            </option>
          ))}
          {data.materials
            .filter((m) => m.returnable)
            .map((m) => (
              <option key={`r${m.id}`} value={`r${m.id}`}>
                {t('Rückgabe: {name}', { name: m.name })}
              </option>
            ))}
        </SelectField>
        <Checkbox
          label={t('Namenssuche erlauben')}
          hint={t(
            'Ohne Karte: Das Personal sucht Angemeldete ab drei Buchstaben und bucht sie nach dem Abgleich mit dem Ausweis ein.',
          )}
          checked={allowSearch}
          onChange={setAllowSearch}
        />
        <div className="button-row">
          <button type="submit" className="button" disabled={busy || !label.trim()}>
            {t('Scan-Link anlegen')}
          </button>
        </div>
      </form>
    </div>
  )
}
