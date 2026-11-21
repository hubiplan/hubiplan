// Schießbuch des Vereins: gemeldete Termine bestätigen, Schießbuch je Mitglied mit Stand nach
// § 14 WaffG und Bestätigung der Schießtermine als PDF.
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import type { PickedMember } from '../../api/members.ts'
import { shootingApi } from '../../api/training.ts'
import type { ShootingEntry } from '../../api/training.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Field, LoadError, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { EntryForm } from './EntryForm.tsx'
import { EvaluationCard } from './Evaluation.tsx'

export function entryDetails(e: ShootingEntry) {
  return [
    e.weapon_class_label,
    e.caliber,
    e.place,
    e.competition ? t('Wettkampf') : '',
    e.external ? t('anderer Verein') : '',
    e.permit_required ? '' : t('erlaubnisfrei'),
  ]
    .filter(Boolean)
    .join(' · ')
}

export function ShootingLog({ orgId }: { orgId: number }) {
  const { data, error, reload } = useLoad(() => shootingApi.overview(orgId), [orgId])
  const [member, setMember] = useState<PickedMember | null>(null)
  const [actionError, setActionError] = useState('')
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const decide = async (id: number, confirm: boolean) => {
    setActionError('')
    try {
      await shootingApi.decide(orgId, id, confirm)
      await reload()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  return (
    <div className="stack">
      {data.reported.length > 0 && (
        <section className="card stack-sm">
          <h2>{t('Gemeldete Schießtermine')}</h2>
          {actionError && <p role="alert">{actionError}</p>}
          <ul className="plain-list training-entries">
            {data.reported.map((e) => (
              <li key={e.id}>
                <strong>{e.name}</strong>, {formatDate(e.date)}: {e.discipline}
                <span className="muted small"> · {entryDetails(e)}</span>
                {e.note && <span className="muted small"> · {e.note}</span>}
                {data.can_edit && (
                  <span className="button-row">
                    <button
                      type="button"
                      className="button button-secondary"
                      onClick={() => void decide(e.id, true)}
                    >
                      {t('Bestätigen')}
                    </button>
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => void decide(e.id, false)}
                    >
                      {t('Ablehnen')}
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="card stack-sm">
        <h2>{t('Schießbuch eines Mitglieds')}</h2>
        <MemberPicker orgId={orgId} value={member} onChange={setMember} label={t('Mitglied')} />
        {data.members.length > 0 && (
          <ul className="plain-list training-members">
            {data.members.map((m) => (
              <li key={m.membership}>
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setMember({ id: m.membership, first_name: m.name, last_name: '' })}
                >
                  {m.name}
                </button>
                <span className="muted small">
                  {' '}
                  {t('{n} Termine in 24 Monaten', { n: m.count_24 })}
                  {m.last ? ` · ${t('zuletzt {date}', { date: formatDate(m.last) })}` : ''}
                  {m.pending ? ` · ${t('{n} gemeldet', { n: m.pending })}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {member && (
        <MemberShooting
          key={member.id}
          orgId={orgId}
          memberId={member.id}
          onChanged={() => void reload()}
        />
      )}
    </div>
  )
}

function MemberShooting({
  orgId,
  memberId,
  onChanged,
}: {
  orgId: number
  memberId: number
  onChanged: () => void
}) {
  const { data, error, reload } = useLoad(
    () => shootingApi.member(orgId, memberId),
    [orgId, memberId],
  )
  const [waffe, setWaffe] = useState('')
  const [bis, setBis] = useState('')
  const [actionError, setActionError] = useState('')
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const pdf = async () => {
    setActionError('')
    try {
      const blob = await shootingApi.pdf(orgId, memberId, undefined, bis || undefined, waffe)
      saveBlob(blob, `schiessnachweis-${memberId}.pdf`)
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  const remove = async (e: ShootingEntry) => {
    const yes = await confirmDialog({
      title: t('Eintrag löschen?'),
      message: t('{date}: {discipline}', { date: formatDate(e.date), discipline: e.discipline }),
      confirmLabel: t('Löschen'),
      final: true,
    })
    if (!yes) return
    try {
      await shootingApi.remove(orgId, e.id)
      await reload()
      onChanged()
    } catch (err) {
      setActionError(errorMessage(err))
    }
  }
  return (
    <div className="stack">
      <h2>{data.name}</h2>
      <EvaluationCard evaluation={data.evaluation} />
      <section className="card stack-sm">
        <h3>{t('Bestätigung der Schießtermine (PDF)')}</h3>
        <p className="muted small">
          {t(
            'Liste der bestätigten Termine der letzten 24 Monate mit Stand nach § 14 WaffG, zum Unterschreiben durch den vertretungsberechtigten Vorstand. Anlage zum Antrag beim Verband.',
          )}
        </p>
        <div className="training-filter">
          <SelectField label={t('Waffe')} value={waffe} onChange={(e) => setWaffe(e.target.value)}>
            <option value="">{t('alle')}</option>
            <option value="short">{t('Kurzwaffe')}</option>
            <option value="long">{t('Langwaffe')}</option>
          </SelectField>
          <Field
            label={t('Stichtag (optional)')}
            type="date"
            value={bis}
            onChange={(e) => setBis(e.target.value)}
          />
          <button type="button" className="button button-secondary" onClick={pdf}>
            {t('PDF erstellen')}
          </button>
        </div>
      </section>
      {actionError && <p role="alert">{actionError}</p>}
      {data.can_edit && (
        <section className="card stack-sm">
          <h3>{t('Schießtermin eintragen')}</h3>
          <EntryForm
            disciplines={data.disciplines ?? []}
            submitLabel={t('Eintragen')}
            onSubmit={async (draft) => {
              await shootingApi.add(orgId, memberId, draft)
              await reload()
              onChanged()
            }}
          />
        </section>
      )}
      <section className="card stack-sm">
        <h3>{t('Einträge')}</h3>
        {data.entries.length === 0 ? (
          <p className="muted">{t('Noch keine Einträge.')}</p>
        ) : (
          <ul className="plain-list training-entries">
            {data.entries.map((e) => (
              <li key={e.id} className={e.status === 'rejected' ? 'muted' : undefined}>
                {formatDate(e.date)}: <strong>{e.discipline}</strong>
                <span className="muted small"> · {entryDetails(e)}</span>
                <span className="badge">{e.status_label}</span>
                <span className="muted small"> · {e.source_label}</span>
                {data.can_edit && !e.from_training && (
                  <button type="button" className="link-button" onClick={() => void remove(e)}>
                    {t('Löschen')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
