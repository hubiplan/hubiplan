// Mitglieder › Einrichtung › Qualifikationen: Arten des Vereins frei pflegen (z. B. Erste Hilfe,
// Übungsleiter, Standaufsicht, Einsicht ins Führungszeugnis) mit üblicher Gültigkeit und
// Vorlauf der Erinnerung. Eingetragen wird in der Mitgliedsakte.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { PERM } from '../../api/orgs.ts'
import { qualificationApi } from '../../api/qualifications.ts'
import type { QualificationType } from '../../api/qualifications.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { DeleteIcon, EditIcon, IconButton, RestoreIcon } from '../../components/icons.tsx'
import { Alert, Checkbox, Field, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

type Draft = Pick<
  QualificationType,
  'name' | 'description' | 'validity_months' | 'remind_days' | 'inspection_only'
>

/** Vorschläge zum schnellen Anlegen; Gültigkeit und Vorlauf lassen sich danach ändern. */
function suggestions(): Draft[] {
  return [
    {
      name: t('Erste Hilfe'),
      description: '',
      validity_months: 24,
      remind_days: 60,
      inspection_only: false,
    },
    {
      name: t('Jugendleiter (Juleica)'),
      description: '',
      validity_months: 36,
      remind_days: 90,
      inspection_only: false,
    },
    {
      name: t('Übungsleiter'),
      description: '',
      validity_months: 48,
      remind_days: 90,
      inspection_only: false,
    },
    {
      name: t('Standaufsicht'),
      description: '',
      validity_months: null,
      remind_days: 60,
      inspection_only: false,
    },
    {
      name: t('Einsicht erweitertes Führungszeugnis'),
      description: '',
      validity_months: 60,
      remind_days: 90,
      inspection_only: true,
    },
  ]
}

const EMPTY: Draft = {
  name: '',
  description: '',
  validity_months: null,
  remind_days: 60,
  inspection_only: false,
}

function TypeForm({
  initial,
  onSave,
  onCancel,
}: {
  initial: Draft
  onSave: (data: Draft) => Promise<boolean>
  onCancel: () => void
}) {
  const [draft, setDraft] = useState<Draft>(initial)
  const [busy, setBusy] = useState(false)
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))
  const number = (v: string) => (v === '' ? null : Number(v))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await onSave(draft)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack" onSubmit={(e) => void submit(e)}>
      <Field
        label={t('Bezeichnung')}
        value={draft.name}
        maxLength={100}
        required
        onChange={(e) => set({ name: e.target.value })}
      />
      <Field
        label={t('Beschreibung (optional)')}
        value={draft.description}
        maxLength={300}
        onChange={(e) => set({ description: e.target.value })}
      />
      <Field
        label={t('Übliche Gültigkeit in Monaten')}
        hint={t('Schlägt beim Eintragen das Ablaufdatum vor. Leer: unbefristet.')}
        type="number"
        min={1}
        max={600}
        value={draft.validity_months ?? ''}
        onChange={(e) => set({ validity_months: number(e.target.value) })}
      />
      <Field
        label={t('Erinnerung Tage vor dem Ablauf')}
        hint={t('Das Mitglied bekommt dann eine E-Mail. Leer: keine Erinnerung.')}
        type="number"
        min={0}
        max={365}
        value={draft.remind_days ?? ''}
        onChange={(e) => set({ remind_days: number(e.target.value) })}
      />
      <Checkbox
        label={t('Nur Einsichtsvermerk (z. B. Führungszeugnis)')}
        hint={t(
          'Festgehalten wird nur, dass und wann der Nachweis eingesehen wurde, ohne Bemerkung und ohne Dokument.',
        )}
        checked={draft.inspection_only}
        onChange={(v) => set({ inspection_only: v })}
      />
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

function details(k: QualificationType): string {
  return [
    k.validity_months ? t('gültig {n} Monate', { n: k.validity_months }) : t('unbefristet'),
    k.remind_days != null
      ? t('Erinnerung {n} Tage vorher', { n: k.remind_days })
      : t('keine Erinnerung'),
    k.inspection_only ? t('nur Einsichtsvermerk') : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

export function QualificationTypesPage() {
  const org = useActiveOrg()
  const editable = org.permissions.includes(PERM.orgEdit)
  const { data, error, reload } = useLoad(() => qualificationApi.types(org.id), [org.id])
  const [editing, setEditing] = useState<QualificationType | 'new' | null>(null)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />

  async function run(action: () => Promise<unknown>, success: string) {
    setMessage(null)
    try {
      await action()
      setMessage({ kind: 'success', text: success })
      await reload()
      return true
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
      return false
    }
  }

  async function remove(k: QualificationType) {
    const ok = await confirmDialog({
      title: t('„{name}“ löschen?', { name: k.name }),
      message: t('Die Qualifikation ist bei keinem Mitglied eingetragen.'),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    setMessage(null)
    try {
      await qualificationApi.deleteType(org.id, k.id)
      setMessage({ kind: 'success', text: t('„{name}“ wurde gelöscht.', { name: k.name }) })
      await reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  const names = new Set(data.map((k) => k.name.toLowerCase()))
  const open = suggestions().filter((s) => !names.has(s.name.toLowerCase()))
  const active = data.filter((k) => !k.is_archived)
  const archived = data.filter((k) => k.is_archived)

  return (
    <div className="stack">
      <p className="muted">
        {t(
          'Lege fest, welche Nachweise ihr festhaltet, etwa Erste Hilfe, Übungsleiter oder Standaufsicht. Eingetragen wird in der Mitgliedsakte; vor dem Ablauf kommt eine Erinnerung, und bei Helferdiensten lässt sich eine Qualifikation voraussetzen.',
        )}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <div className="card">
        {active.length === 0 ? (
          <p className="muted">{t('Noch keine Qualifikationen angelegt.')}</p>
        ) : (
          <ul className="item-list">
            {active.map((k) => (
              <li key={k.id} className="item-row">
                <span className="item-row-info">
                  <strong>{k.name}</strong>
                  <span className="muted small"> · {details(k)}</span>
                  {k.description && <div className="muted small">{k.description}</div>}
                </span>
                {editable && (
                  <span className="button-row">
                    <IconButton
                      label={t('{name} bearbeiten', { name: k.name })}
                      icon={<EditIcon />}
                      onClick={() => setEditing(k)}
                    />
                    {k.in_use ? (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() =>
                          void run(
                            () => qualificationApi.archiveType(org.id, k.id),
                            t('„{name}“ wurde archiviert.', { name: k.name }),
                          )
                        }
                      >
                        {t('archivieren')}
                      </button>
                    ) : (
                      <IconButton
                        label={t('{name} löschen', { name: k.name })}
                        icon={<DeleteIcon />}
                        danger
                        onClick={() => void remove(k)}
                      />
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {archived.length > 0 && (
          <details>
            <summary>{t('Archiviert ({n})', { n: archived.length })}</summary>
            <ul className="item-list">
              {archived.map((k) => (
                <li key={k.id} className="item-row">
                  <span className="item-row-info">{k.name}</span>
                  {editable && (
                    <span className="button-row">
                      <IconButton
                        label={t('{name} wiederherstellen', { name: k.name })}
                        icon={<RestoreIcon />}
                        onClick={() =>
                          void run(
                            () => qualificationApi.restoreType(org.id, k.id),
                            t('„{name}“ ist wieder aktiv.', { name: k.name }),
                          )
                        }
                      />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
      {editable && editing && (
        <TypeForm
          key={editing === 'new' ? 'new' : editing.id}
          initial={editing === 'new' ? EMPTY : editing}
          onCancel={() => setEditing(null)}
          onSave={async (draft) => {
            const ok = await run(
              () =>
                editing === 'new'
                  ? qualificationApi.createType(org.id, draft)
                  : qualificationApi.updateType(org.id, editing.id, draft),
              t('„{name}“ wurde gespeichert.', { name: draft.name }),
            )
            if (ok) setEditing(null)
            return ok
          }}
        />
      )}
      {editable && !editing && (
        <div className="button-row">
          <button type="button" className="button" onClick={() => setEditing('new')}>
            {t('Qualifikation anlegen')}
          </button>
        </div>
      )}
      {editable && open.length > 0 && (
        <div className="card stack">
          <h2>{t('Vorschläge')}</h2>
          <p className="muted small">
            {t('Mit einem Klick anlegen; Gültigkeit und Erinnerung lassen sich danach ändern.')}
          </p>
          <div className="button-row">
            {open.map((s) => (
              <button
                key={s.name}
                type="button"
                className="button button-ghost"
                onClick={() =>
                  void run(
                    () => qualificationApi.createType(org.id, s),
                    t('„{name}“ wurde angelegt.', { name: s.name }),
                  )
                }
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
