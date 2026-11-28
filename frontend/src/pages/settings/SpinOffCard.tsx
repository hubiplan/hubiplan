import { useState } from 'react'
import { PERM } from '../../api/orgs.ts'
import { transferApi } from '../../api/datatransfer.ts'
import { peeringApi } from '../../api/peering.ts'
import type { SpinOff, SpinOffExitCandidate } from '../../api/peering.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { useDepartmentChoices } from '../../components/masterData.ts'

export function SpinOffCard({ onChange }: { onChange: () => void }) {
  const org = useActiveOrg()
  const canExport = org.permissions.includes(PERM.dataExport)
  const { data, reload } = useLoad(() => peeringApi.spinOffs(org.id), [org.id])
  const units = useDepartmentChoices(org.id)
  const [unit, setUnit] = useState('')
  const [way, setWay] = useState<'keep' | 'move'>('keep')
  const [cutoff, setCutoff] = useState('')
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [withFiles, setWithFiles] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!data) return null
  const candidates = (units.data ?? []).filter(
    (u) =>
      !u.is_remote &&
      u.is_active &&
      !(units.data ?? []).some((c) => c.parent_unit === u.id) &&
      !data.spin_offs.some(
        (s) => s.unit.id === u.id && (s.state === 'prepared' || s.state === 'requested'),
      ),
  )
  const items = data.checklist[way]
  const ready = unit && cutoff && items.every((i) => checked[i.key])

  async function prepare() {
    const ok = await confirmDialog({
      title: t('Ausgliederung vorbereiten?'),
      message:
        t('Es entstehen ein Export der Untereinheit mit ihren Mitgliedern und ein Kopplungscode ') +
        t(
          '(30 Tage gültig). Gib die Datei nur an die Plattformverwaltung der neuen Instanz weiter.',
        ),
      confirmLabel: t('Vorbereiten'),
      danger: false,
    })
    if (!ok) return
    setErr(null)
    setBusy(true)
    try {
      await peeringApi.prepareSpinOff(org.id, {
        unit: Number(unit),
        way,
        cutoff,
        checklist: checked,
        with_files: withFiles,
      })
      setUnit('')
      setChecked({})
      await reload()
      onChange()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  async function cancel(id: number) {
    setErr(null)
    try {
      await peeringApi.cancelSpinOff(org.id, id)
      await reload()
    } catch (e) {
      setErr(errorMessage(e))
    }
  }

  return (
    <div className="card card-wide">
      <h3>{t('Untereinheit auf eigene Instanz ausgliedern')}</h3>
      <p className="muted small">
        {t(
          'Für eine Untereinheit, die künftig eine eigene HUBIplan-Instanz betreibt. Sie bekommt einen Export ihrer Daten mit einem Kopplungscode. Die neue Instanz liest ihn ein und koppelt sich damit unter den Verein. Nach deiner Bestätigung ist die Untereinheit hier nur noch zu sehen.',
        )}
      </p>
      {data.spin_offs.length > 0 && (
        <ul className="plain-list">
          {data.spin_offs.map((s) => (
            <li key={s.id}>
              <strong>{s.unit.name}</strong>
              {t(': {way_label}, Stichtag {x} ·', {
                way_label: s.way_label,
                x: formatDate(s.cutoff),
              })}{' '}
              {s.state_label}
              {s.state === 'prepared' && s.export_job?.has_file && canExport && (
                <>
                  {' · '}
                  <a href={transferApi.downloadUrl({ org: org.id }, s.export_job.id)}>
                    {t('Export herunterladen')}
                  </a>
                </>
              )}
              {s.state === 'prepared' && s.export_job && !s.export_job.has_file && (
                <> {t('· Export läuft noch')}</>
              )}
              {s.state === 'prepared' && (
                <>
                  {' '}
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => void cancel(s.id)}
                  >
                    {t('Abbrechen')}
                  </button>
                </>
              )}
              {s.state === 'requested' && (
                <>
                  {' '}
                  {t(
                    '· Die Anfrage steht unten bei den Kopplungen und wartet auf deine Bestätigung.',
                  )}
                </>
              )}
              {s.exited_at && (
                <>
                  {' '}
                  {t('· Sammelaustritt: {exited_count} Mitglieder zum', {
                    exited_count: s.exited_count,
                  })}{' '}
                  {formatDate(s.cutoff)}
                </>
              )}
              {s.state === 'done' && s.way === 'move' && !s.exited_at && (
                <CollectiveExit spin={s} onDone={() => void reload()} />
              )}
            </li>
          ))}
        </ul>
      )}
      {!canExport ? (
        <Alert kind="info">
          {t('Ausgliedern darf nur, wer den vollständigen Export erstellen darf.')}
        </Alert>
      ) : (
        <>
          <SelectField
            label={t('Untereinheit')}
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            hint={t('Nur Untereinheiten ohne eigene Untereinheiten.')}
          >
            <option value="">{t('bitte wählen')}</option>
            {candidates.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
          <fieldset>
            <legend className="small">{t('Was wird aus den Mitgliedern?')}</legend>
            <label className="checkbox">
              <input
                type="radio"
                name="spin-way"
                checked={way === 'keep'}
                onChange={() => {
                  setWay('keep')
                  setChecked({})
                }}
              />
              <span>
                {t(
                  'Sie bleiben Mitglieder des Vereins (empfohlen). Die Untereinheit pflegt sie auf ihrer Instanz, der Verein sieht sie weiter.',
                )}
              </span>
            </label>
            <label className="checkbox">
              <input
                type="radio"
                name="spin-way"
                checked={way === 'move'}
                onChange={() => {
                  setWay('move')
                  setChecked({})
                }}
              />
              <span>
                {t(
                  'Sie werden Mitglieder der Untereinheit. Beim Verein treten sie zum Stichtag mit Grund „Wechsel“ aus.',
                )}
              </span>
            </label>
          </fieldset>
          <Field
            label={t('Stichtag')}
            type="date"
            value={cutoff}
            onChange={(e) => setCutoff(e.target.value)}
          />
          <fieldset>
            <legend className="small">{t('Vorher erledigt')}</legend>
            {items.map((i) => (
              <Checkbox
                key={i.key}
                label={i.label}
                checked={!!checked[i.key]}
                onChange={(on) => setChecked({ ...checked, [i.key]: on })}
              />
            ))}
          </fieldset>
          <Checkbox
            label={t('Mit Dateien (Fotos, Belege, Satzung)')}
            checked={withFiles}
            onChange={setWithFiles}
          />
          {err && <Alert kind="error">{err}</Alert>}
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={!ready || busy}
              onClick={() => void prepare()}
            >
              {t('Ausgliederung vorbereiten')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

/** Weg B: Mitglieder der ausgegliederten Untereinheit treten zum Stichtag aus (Wechsel). */
function CollectiveExit({ spin, onDone }: { spin: SpinOff; onDone: () => void }) {
  const org = useActiveOrg()
  const [members, setMembers] = useState<SpinOffExitCandidate[] | null>(null)
  const [keep, setKeep] = useState<Record<number, boolean>>({})
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!org.permissions.includes(PERM.membersEdit)) return null

  async function load() {
    setErr(null)
    try {
      const data = await peeringApi.spinOffExitPreview(org.id, spin.id)
      setMembers(data.members)
      // Wer zugleich in einer anderen Untereinheit ist, bleibt vorerst Mitglied
      setKeep(Object.fromEntries(data.members.map((m) => [m.id, m.also_in.length > 0])))
    } catch (e) {
      setErr(errorMessage(e))
    }
  }

  async function run() {
    if (!members) return
    const leaving = members.filter((m) => !keep[m.id]).length
    const ok = await confirmDialog({
      final: false,
      title: t('Sammelaustritt ausführen?'),
      message:
        t('{leaving} Mitglieder treten zum {x} mit Grund „Wechsel“ aus. ', {
          leaving,
          x: formatDate(spin.cutoff),
        }) + t('Die Zeiträume bleiben, danach gilt die Löschfrist wie bei jedem Austritt.'),
      confirmLabel: t('Austritt erfassen'),
    })
    if (!ok) return
    setBusy(true)
    setErr(null)
    try {
      await peeringApi.spinOffExit(
        org.id,
        spin.id,
        members.filter((m) => keep[m.id]).map((m) => m.id),
      )
      onDone()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="subcard">
      {!members ? (
        <button type="button" className="button" onClick={() => void load()}>
          {t('Sammelaustritt vorbereiten')}
        </button>
      ) : (
        <>
          <p className="small">
            {t('Austritt zum {x} mit Grund „Wechsel“. Häkchen heißt: bleibt Vereinsmitglied.', {
              x: formatDate(spin.cutoff),
            })}
          </p>
          {members.length === 0 && <p className="muted small">{t('Niemand mehr zugeordnet.')}</p>}
          {members.map((m) => (
            <Checkbox
              key={m.id}
              label={t('{name} bleibt{x}', {
                name: m.name,
                x: m.also_in.length ? t(' (auch in {x0})', { x0: m.also_in.join(', ') }) : '',
              })}
              checked={!!keep[m.id]}
              onChange={(on) => setKeep({ ...keep, [m.id]: on })}
            />
          ))}
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() => void run()}
            >
              {t('Sammelaustritt ausführen')}
            </button>
          </div>
        </>
      )}
      {err && <Alert kind="error">{err}</Alert>}
    </div>
  )
}
