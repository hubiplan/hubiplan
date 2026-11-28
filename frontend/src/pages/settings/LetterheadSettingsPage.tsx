import { useState } from 'react'
import { Link } from 'react-router-dom'
import { saveBlob } from '../../api/client.ts'
import { docApi, docBase } from '../../api/documents.ts'
import type { DocFolder } from '../../api/documents.ts'
import { letterFileName, letterheadApi } from '../../api/letterhead.ts'
import type { FileFormat, LetterheadProposal, LetterheadState } from '../../api/letterhead.ts'
import { orgApi, PERM, unitName } from '../../api/orgs.ts'
import type { Department } from '../../api/orgs.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { flushAllForms } from '../../components/leaveGuard.ts'
import { Alert, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { formatDay } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'
import { LetterheadEditor } from './LetterheadEditor.tsx'

function NeutralCard({
  orgId,
  unit,
  unitLabel,
}: {
  orgId: number
  unit: number | null
  unitLabel: string
}) {
  const { active, can } = useOrg()
  const withDocs = !!active && can(PERM.docsManage)
  const folders = useLoad(
    () =>
      withDocs
        ? docApi.overview(docBase.org(orgId)).then((o) => o.folders)
        : Promise.resolve([] as DocFolder[]),
    [orgId, withDocs],
  )
  const [folder, setFolder] = useState<number | ''>('')
  const [format, setFormat] = useState<FileFormat>('dotx')
  const [message, setMessage] = useState<{ kind: 'info' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  // Erzeugt wird aus dem gespeicherten Stand: erst alles speichern (UI-Audit NAF-01)
  async function saved(): Promise<boolean> {
    if (await flushAllForms()) return true
    setMessage({
      kind: 'error',
      text: t('Die Vorlage wurde noch nicht erstellt. Bitte zuerst die Änderungen speichern.'),
    })
    return false
  }

  async function download() {
    setMessage(null)
    if (!(await saved())) return
    try {
      saveBlob(await letterheadApi.neutral(orgId, format, unit), letterFileName(unitLabel, format))
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function publish() {
    if (!folder) return
    setBusy(true)
    setMessage(null)
    try {
      if (!(await saved())) return
      const res = await letterheadApi.publish(orgId, folder, format, unit)
      setMessage({
        kind: 'info',
        text: res.created
          ? t('„{title}“ liegt jetzt in der Dokumentenablage.', { title: res.title })
          : t('„{title}“ hat eine neue Fassung bekommen.', { title: res.title }),
      })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Neutrale Vorlage')}</h2>
      <p className="muted small">
        {t(
          'Ohne persönliche Angaben: Name, Funktion und Kontakt sind Felder zum Ausfüllen in Word. So finden alle Vorstände dieselbe Grundvorlage.',
        )}
      </p>
      <SelectField
        label={t('Dateiformat')}
        value={format}
        onChange={(e) => setFormat(e.target.value as FileFormat)}
      >
        <option value="dotx">
          {t('Word-Vorlage (.dotx): öffnet jedes Mal ein neues Dokument')}
        </option>
        <option value="docx">{t('Word-Dokument (.docx): z. B. für Word im Browser')}</option>
      </SelectField>
      <div className="button-row">
        <button type="button" className="button" onClick={() => void download()}>
          {t('Herunterladen')}
        </button>
      </div>
      {withDocs && (
        <>
          <div className="grid-2">
            <SelectField
              label={t('In der Dokumentenablage ablegen')}
              value={folder}
              onChange={(e) => setFolder(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">{t('Ordner wählen …')}</option>
              {(folders.data ?? []).map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name} ({f.visibility_label})
                </option>
              ))}
            </SelectField>
            <div className="button-row">
              <button
                type="button"
                className="button"
                disabled={!folder || busy}
                onClick={() => void publish()}
              >
                {t('Ablegen')}
              </button>
            </div>
          </div>
          {folders.error && (
            <LoadError
              message={t(
                'Die Ordner konnten nicht geladen werden. Deine Eingaben bleiben erhalten. {error}',
                { error: folders.error },
              )}
              onRetry={() => void folders.reload()}
            />
          )}
          {folders.data?.length === 0 && (
            <p className="muted small">
              {t('Noch kein Ordner vorhanden.')}{' '}
              <Link to="/dokumente">{t('Dokumentenablage öffnen')}</Link>
            </p>
          )}
        </>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
    </div>
  )
}

/** Einstellungen › Briefbogen: die Einheit selbst und ihre Untereinheiten. */
const PROPOSAL_LABELS: Record<string, () => string> = {
  head_name: () => t('Name im Briefkopf'),
  tagline: () => t('Zusatzzeile im Kopf'),
  salutation: () => t('Anrede'),
  closing: () => t('Grußformel'),
}

/** Vorschläge eines KI-Assistenten für die Texte (Gesamtaudit 15.11., FF-12 a). */
function Proposals({
  orgId,
  state,
  editable,
  done,
}: {
  orgId: number
  state: LetterheadState
  editable: boolean
  done: () => void
}) {
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const items: LetterheadProposal[] = state.proposals ?? []
  if (items.length === 0) return null

  async function run(fn: () => Promise<unknown>) {
    setErr(null)
    setBusy(true)
    try {
      await fn()
      done()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card stack">
      <h2>{t('Vorschlag für die Texte des Briefbogens')}</h2>
      <p className="muted">
        {t(
          'Ein KI-Assistent hat neue Texte vorgeschlagen. Sie gelten erst, wenn du sie übernimmst; dann stehen sie auf allen neuen Rechnungen, Mahnungen und Spendenquittungen. Prüfe sie genau, besonders Bankangaben oder Aufforderungen.',
        )}
      </p>
      {err && <Alert kind="error">{err}</Alert>}
      {items.map((p) => (
        <div key={p.id} className="stack">
          <p className="muted small">
            {p.via} · {t('verfällt am {date}', { date: formatDay(p.expires_at) })}
          </p>
          <dl>
            {Object.entries(p.texts).map(([key, value]) => (
              <div key={key}>
                <dt>{PROPOSAL_LABELS[key]?.() ?? key}</dt>
                <dd>
                  <span className="muted">
                    {String((state.letterhead as unknown as Record<string, unknown>)[key] ?? '') ||
                      '–'}
                  </span>{' '}
                  → <strong>{value || '–'}</strong>
                </dd>
              </div>
            ))}
          </dl>
          {editable && (
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={() => void run(() => letterheadApi.applyProposal(orgId, p.id))}
              >
                {t('Übernehmen')}
              </button>
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => void run(() => letterheadApi.discardProposal(orgId, p.id))}
              >
                {t('Verwerfen')}
              </button>
            </div>
          )}
        </div>
      ))}
    </section>
  )
}

export function LetterheadSettingsPage() {
  const org = useActiveOrg()
  const { can } = useOrg()
  const editable = can(PERM.orgEdit)
  const [unitId, setUnitId] = useState<number | null>(null)
  const units = useLoad(
    () =>
      org.type === 'club' ? orgApi.departmentChoices(org.id) : Promise.resolve([] as Department[]),
    [org.id],
  )
  const state = useLoad(
    () => (unitId ? letterheadApi.unit(org.id, unitId) : letterheadApi.get(org.id)),
    [org.id, unitId],
  )
  const list = units.data ?? []
  const unitLabel = unitId ? (list.find((d) => d.id === unitId)?.name ?? org.name) : org.name

  return (
    <>
      {units.error && (
        <LoadError
          message={t(
            'Die {department_label_plural} konnten nicht geladen werden; ihre Briefbögen sind deshalb gerade nicht wählbar. {error}',
            { department_label_plural: org.department_label_plural, error: units.error },
          )}
          onRetry={() => void units.reload()}
        />
      )}
      {list.length > 0 && (
        <div className="card card-wide">
          <SelectField
            label={t('Briefbogen für')}
            value={unitId ?? ''}
            hint={t(
              '{department_label_plural} übernehmen standardmäßig den Briefbogen von {name}.',
              { department_label_plural: org.department_label_plural, name: org.name },
            )}
            onChange={(e) => setUnitId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">{org.name}</option>
            {list.map((d) => (
              <option key={d.id} value={d.id}>
                {unitName(d)}
              </option>
            ))}
          </SelectField>
        </div>
      )}
      {state.error && <Alert kind="error">{state.error}</Alert>}
      {!state.data && !state.error && <Loading />}
      {state.data && state.data.organization.id === (unitId ?? org.id) && (
        <>
          <Proposals
            orgId={org.id}
            state={state.data}
            editable={editable}
            done={() => void state.reload()}
          />
          <LetterheadEditor
            key={state.data.organization.id}
            state={state.data}
            editable={editable}
            save={(changes) =>
              unitId
                ? letterheadApi.updateUnit(org.id, unitId, changes)
                : letterheadApi.update(org.id, changes)
            }
            preview={() => letterheadApi.preview(org.id, unitId)}
            logoUploadUrl={letterheadApi.logoUrl(org.id, unitId)}
            reload={() => (unitId ? letterheadApi.unit(org.id, unitId) : letterheadApi.get(org.id))}
          />
          <NeutralCard orgId={org.id} unit={unitId} unitLabel={unitLabel} />
        </>
      )}
    </>
  )
}
