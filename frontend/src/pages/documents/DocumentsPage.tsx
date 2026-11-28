// Dokumente: Ablage der aktiven Organisation, Abteilung oder des Mitgliederbereichs.
import { useState } from 'react'
import './documents.css'
import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { PERM } from '../../api/orgs.ts'
import { DEPT_PERM } from '../../api/portal.ts'
import { docApi, docBase } from '../../api/documents.ts'
import type { DocBase } from '../../api/documents.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { Why } from '../../learning/Aids.tsx'
import { SubpageUnavailable } from '../NoticePages.tsx'
import { t } from '../../i18n/index.ts'
import { type Msg } from './documentsHelpers.ts'
import { Library } from './Library.tsx'

export function DocumentsPage() {
  const { active, activeDept, activePortal } = useOrg()
  const { pathname } = useLocation()
  let base: DocBase | null = null
  let manage = false
  let orgId: number | null = null
  let canEditStatute = false
  if (
    active &&
    (active.type === 'club' || active.type === 'federation') &&
    active.permissions.includes(PERM.docsView)
  ) {
    base = docBase.org(active.id)
    manage = active.permissions.includes(PERM.docsManage)
    orgId = active.id
    canEditStatute = active.permissions.includes(PERM.orgEdit)
  } else if (activeDept) {
    base = docBase.dept(activeDept.id)
    manage = activeDept.permissions.includes(DEPT_PERM.docsManage)
  } else if (activePortal) {
    return (
      <section>
        <PageHeader />
        <MemberDocuments key={activePortal.id} base={docBase.portal(activePortal.id)} />
      </section>
    )
  }
  if (!base) {
    return (
      <section>
        <h1>{t('Dokumente')}</h1>
        <p className="muted">{t('Für diesen Bereich gibt es keine Dokumentenablage.')}</p>
      </section>
    )
  }
  // Papierkorb ist kein Menüpunkt, sondern ein Link in der Ablage: eigener Titel im Kopf
  const inTrash = manage && /^\/dokumente\/papierkorb\/?$/.test(pathname)
  return (
    <section>
      <PageHeader title={inTrash ? t('Papierkorb') : undefined} />
      <DocumentArea
        key={base}
        base={base}
        orgId={orgId}
        canEditStatute={canEditStatute}
        trash={manage}
      />
    </section>
  )
}

/** Ablage mit Auswahl der Abteilung (für Papierkorb und Ablage gemeinsam). */
function DocumentArea({
  base,
  orgId,
  canEditStatute,
  trash,
}: {
  base: DocBase
  orgId: number | null
  canEditStatute: boolean
  trash: boolean
}) {
  const { data, error, reload } = useLoad(() => docApi.overview(base), [base])
  return (
    <Routes>
      <Route
        index
        element={
          <>
            {/* Papierkorb als Link in der Seite wie bei Aufgaben und Material (Menüprüfung M-21) */}
            {trash && (
              <p className="small">
                <Link to="papierkorb">{t('Papierkorb')}</Link>
              </p>
            )}
            {error && <Alert kind="error">{error}</Alert>}
            {!data && !error && <Loading />}
            {data && (
              <Library
                base={base}
                data={data}
                reload={reload}
                orgId={orgId}
                canEditStatute={canEditStatute}
              />
            )}
          </>
        }
      />
      {trash && <Route path="papierkorb" element={<TrashPanel base={base} />} />}
      <Route
        path="*"
        element={<SubpageUnavailable to="/dokumente" label={t('Zur Dokumentenablage')} />}
      />
    </Routes>
  )
}

function TrashPanel({ base }: { base: DocBase }) {
  const { data, error, reload } = useLoad(() => docApi.trash(base), [base])
  const [message, setMessage] = useState<Msg>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true)
    setMessage(null)
    try {
      await action()
      await reload()
      setMessage({ kind: 'success', text: success })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <div>
      <p className="small">
        <Link to="/dokumente">{t('Zur Dokumentenablage')}</Link>
      </p>
      <p className="muted small">
        {t(
          'Gelöschte Dokumente bleiben 30 Tage im Papierkorb und werden danach endgültig entfernt.',
        )}
      </p>
      <Why k="docs_trash" />
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {data.length === 0 ? (
        <p className="muted">{t('Der Papierkorb ist leer.')}</p>
      ) : (
        <ul className="statute-list">
          {data.map((d) => (
            <li key={d.id}>
              <div>
                <strong>{d.title}</strong> <span className="muted">· {d.folder_name}</span>
                <div className="muted small">
                  {t('gelöscht am')} {d.deleted_at && formatDate(d.deleted_at)}
                  {d.deleted_by && t(' von {deleted_by}', { deleted_by: d.deleted_by })}
                </div>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void run(() => docApi.restore(base, d.id), t('Das Dokument ist wieder da.'))
                  }
                >
                  {t('Wiederherstellen')}
                </button>
                <button
                  type="button"
                  className="button button-danger"
                  disabled={busy}
                  onClick={async () => {
                    if (
                      await confirmDialog({
                        final: true,
                        title: t('„{title}“ endgültig löschen?', { title: d.title }),
                        message: t('Das lässt sich nicht rückgängig machen.'),
                        confirmLabel: t('Endgültig löschen'),
                      })
                    )
                      await run(() => docApi.purge(base, d.id), t('Das Dokument wurde gelöscht.'))
                  }}
                >
                  {t('Endgültig löschen')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Mitgliederbereich: freigegebene Dokumente des Vereins und der eigenen Abteilungen. */
function MemberDocuments({ base }: { base: DocBase }) {
  const { data, error, reload } = useLoad(() => docApi.overview(base), [base])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  if (!data.folders.some((folder) => folder.documents.length > 0))
    return <p className="muted">{t('Für dich sind keine Dokumente freigegeben.')}</p>
  return (
    <Library
      base={base}
      data={{ ...data, can_manage: false }}
      reload={reload}
      orgId={null}
      canEditStatute={false}
    />
  )
}
