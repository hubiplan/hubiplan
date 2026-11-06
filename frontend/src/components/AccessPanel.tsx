import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { portalApi } from '../api/portal.ts'
import type { AccessInfo } from '../api/portal.ts'
import { errorMessage, formatDateTime, useLoad } from './forms.ts'
import { Alert } from './ui.tsx'
import { confirmDialog } from './dialog.ts'
import { useTerms } from '../org/terms.ts'
import { t } from '../i18n/index.ts'

export function AccessPanel({
  access,
  hasEmail,
  contactEmail,
  canManage,
  disabledHint,
  onSend,
  onRemove,
}: {
  access: AccessInfo | null
  hasEmail: boolean
  /** Aktuelle Kontakt-Adresse: weicht sie vom Zugang ab, gibt es „übertragen“ */
  contactEmail?: string
  canManage: boolean
  disabledHint?: ReactNode
  onSend: (transfer?: boolean) => Promise<{ sent: 'link' | 'password' }>
  onRemove: () => Promise<unknown>
}) {
  const tm = useTerms()
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<string>) {
    setBusy(true)
    setMessage(null)
    try {
      setMessage({ kind: 'success', text: await action() })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  const moved =
    !!access && !!contactEmail && contactEmail.toLowerCase() !== access.email.toLowerCase()

  async function transfer() {
    if (!access) return
    const ok = await confirmDialog({
      title: t('Freischaltung auf neue Adresse übertragen?'),
      message:
        t('Die Freischaltung hängt bisher an {email}. Danach meldet sich das Mitglied mit ', {
          email: access.email,
        }) +
        t('{x} an; die bisherige Adresse bekommt eine ', {
          x: contactEmail ?? t('der neuen Adresse'),
        }) +
        t(
          'Mitteilung. Nur übertragen, wenn sicher ist, dass die neue Adresse dem Mitglied gehört.',
        ),
      confirmLabel: t('Übertragen'),
    })
    if (!ok) return
    void run(async () => {
      await onSend(true)
      return t('Freischaltung übertragen; Link an die neue Adresse gesendet.')
    })
  }

  return (
    <div className="card card-wide">
      <h2>{t('Konto und Mitgliederbereich')}</h2>
      {access ? (
        <p>
          {t('Mitgliederbereich freigeschaltet für')} <strong>{access.email}</strong> {t('seit')}{' '}
          {formatDateTime(access.created_at)}
          <br />
          <span className="muted small">
            {access.last_login
              ? t('zuletzt angemeldet {x}', { x: formatDateTime(access.last_login) })
              : t('noch nicht angemeldet')}{' '}
            {t('· Anmeldung')}{' '}
            {access.login === 'link' ? t('per Anmeldelink oder Passwort') : t('mit Passwort')}
          </span>
        </p>
      ) : (
        <p className="muted">
          {t(
            'Mitgliederbereich nicht freigeschaltet. Mit der Freischaltung sieht das Mitglied seine Daten und kann Änderungen melden; Inhaber von Rollen {im} arbeiten mit demselben Konto in {ihrem}.',
            { im: tm.im, ihrem: tm.ihrem },
          )}
        </p>
      )}
      {disabledHint && <Alert kind="info">{disabledHint}</Alert>}
      {moved && canManage && (
        <Alert kind="info">
          {t(
            'Die Kontakt-Adresse ist jetzt {contactEmail}. Die Freischaltung bleibt bei {email}, bis ihr sie ausdrücklich übertragt.',
            { contactEmail, email: access?.email },
          )}
        </Alert>
      )}
      {canManage && !disabledHint && (
        <div className="button-row">
          <button
            type="button"
            className="button button-primary"
            disabled={busy || !hasEmail}
            onClick={() =>
              void run(async () => {
                const r = await onSend(false)
                return r.sent === 'link'
                  ? t('Anmeldelink per E-Mail gesendet.')
                  : t('Link zum Festlegen des Passworts gesendet (Konto mit Rollenrechten).')
              })
            }
          >
            {access
              ? t('Neuen Link senden{x}', { x: moved ? t(' an {x0}', { x0: access.email }) : '' })
              : t('Freischalten und Anmeldelink senden')}
          </button>
          {moved && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void transfer()}
            >
              {t('Freischaltung auf neue Adresse übertragen')}
            </button>
          )}
          {access && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={async () => {
                if (
                  await confirmDialog({
                    title: t('Mitgliederbereich sperren?'),
                    message: t(
                      'Die Person kommt danach nicht mehr in den Mitgliederbereich. Rollen mit Rechten behalten ihr Konto.',
                    ),
                    confirmLabel: t('Sperren'),
                  })
                ) {
                  void run(async () => {
                    await onRemove()
                    return t('Mitgliederbereich gesperrt.')
                  })
                }
              }}
            >
              {t('Mitgliederbereich sperren')}
            </button>
          )}
        </div>
      )}
      {!hasEmail && canManage && (
        <p className="muted small">
          {t('Für die Freischaltung braucht das Mitglied eine E-Mail-Adresse.')}
        </p>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
    </div>
  )
}

/** Zugang in der Mitgliedsakte des Vereins (lädt den Status selbst). */
export function MemberAccessSection({
  orgId,
  memberId,
  hasEmail,
  contactEmail,
  canManage,
}: {
  orgId: number
  memberId: number
  hasEmail: boolean
  contactEmail?: string
  canManage: boolean
}) {
  const tm = useTerms()
  const { data, error, setData } = useLoad(
    () => portalApi.memberAccess(orgId, memberId),
    [orgId, memberId],
  )
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return null
  const enabled = data.portal_enabled || data.department_access_enabled
  return (
    <AccessPanel
      access={data.access}
      hasEmail={hasEmail}
      contactEmail={contactEmail}
      canManage={canManage}
      disabledHint={
        enabled || data.access ? undefined : (
          <>
            {t('Der Mitgliederbereich ist ausgeschaltet. Ihr schaltet ihn unter')}{' '}
            <Link to="/mitglieder/einrichtung/mitgliederbereich">
              {t('Mitglieder › Einrichtung › Mitgliederbereich & Fotos')}
            </Link>{' '}
            {t('ein, die Freischaltung für {pl} unter', { pl: tm.pl })}{' '}
            <Link to="/einstellungen/organisation">{t('Einstellungen › Organisation')}</Link>.
          </>
        )
      }
      onSend={async (transfer) => {
        const r = await portalApi.sendMemberAccess(orgId, memberId, transfer)
        setData({ ...data, access: r.access })
        return r
      }}
      onRemove={async () => {
        await portalApi.removeMemberAccess(orgId, memberId)
        setData({ ...data, access: null })
      }}
    />
  )
}
