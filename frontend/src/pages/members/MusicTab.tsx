import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { InstrumentSelect, loadInstruments } from '../music/InstrumentSelect.tsx'

type Musician = { id: number; membership: number | null; active: boolean }
type Skill = {
  id: number
  musician: number
  instrument: string
  register: string
  primary: boolean
}

/**
 * Reiter „Musik“ der Mitgliedsakte: Instrumente des Mitglieds (keins, eins oder mehrere, eins
 * davon als Hauptinstrument). Wer Musik bearbeiten darf, trägt sie hier direkt ein; fehlt das
 * Musikerprofil, legt HUBIplan es dabei an (konzepte/instrumente.md).
 */
export function MusicTab({ orgId, memberId }: { orgId: number; memberId: number }) {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes('music.edit')
  const base = `/api/orgs/${orgId}/music/`
  const load = useLoad(async () => {
    const [musicians, instruments] = await Promise.all([
      api.get<Musician[]>(`${base}musicians/`),
      loadInstruments(orgId),
    ])
    const musician = musicians.find((m) => m.membership === memberId) ?? null
    const skills = musician
      ? (await api.get<Skill[]>(`${base}skills/`)).filter((s) => s.musician === musician.id)
      : []
    return { musician, skills, instruments }
  }, [orgId, memberId])
  const [adding, setAdding] = useState(false)
  const [instrument, setInstrument] = useState('')
  const [register, setRegister] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const data = load.data
  const act = async (fn: () => Promise<unknown>) => {
    setActionError('')
    setBusy(true)
    try {
      await fn()
      await load.reload()
      return true
    } catch (err) {
      setActionError(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  const add = async () => {
    if (!data) return
    const ok = await act(async () => {
      const musician =
        data.musician ??
        (await api.post<Musician>(`${base}musicians/`, { membership: memberId, active: true }))
      await api.post(`${base}skills/`, {
        musician: musician.id,
        instrument,
        register,
        // Das erste Instrument ist das Hauptinstrument
        primary: data.skills.length === 0,
      })
    })
    if (ok) {
      setAdding(false)
      setInstrument('')
      setRegister('')
    }
  }
  const makePrimary = (skill: Skill) =>
    act(async () => {
      for (const other of data?.skills ?? [])
        if (other.primary && other.id !== skill.id)
          await api.patch(`${base}skills/${other.id}/`, { primary: false })
      await api.patch(`${base}skills/${skill.id}/`, { primary: true })
    })
  const remove = async (skill: Skill) => {
    if (
      await confirmDialog({
        final: true,
        message: t('„{name}“ beim Mitglied entfernen?', { name: skill.instrument }),
        confirmLabel: t('Entfernen'),
      })
    )
      await act(() => api.del(`${base}skills/${skill.id}/`))
  }

  return (
    <section className="card card-wide stack" aria-labelledby="musik-titel">
      <h2 id="musik-titel">{t('Musikerprofil')}</h2>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      {actionError && <Alert kind="error">{actionError}</Alert>}
      {!data && !load.error && <Loading />}
      {data && !data.musician && <p className="muted">{t('Noch kein Musikerprofil angelegt.')}</p>}
      {data?.musician && <p>{data.musician.active ? t('Aktiv') : t('Nicht aktiv')}</p>}
      {data &&
        (data.skills.length === 0 ? (
          data.musician && <p className="muted">{t('Noch keine Instrumente eingetragen.')}</p>
        ) : (
          <ul className="plain-list">
            {[...data.skills]
              .sort((a, b) => Number(b.primary) - Number(a.primary))
              .map((s) => (
                <li key={s.id}>
                  <strong>{s.instrument}</strong>
                  {s.register && ` · ${s.register}`}
                  {s.primary && <span className="muted small">{t(' (Hauptinstrument)')}</span>}
                  {canEdit && (
                    <span className="music-record-actions">
                      {!s.primary && (
                        <button
                          className="button button-ghost"
                          disabled={busy}
                          onClick={() => makePrimary(s)}
                        >
                          {t('Als Hauptinstrument')}
                        </button>
                      )}
                      <button
                        className="button button-ghost"
                        disabled={busy}
                        onClick={() => remove(s)}
                      >
                        {t('Entfernen')}
                      </button>
                    </span>
                  )}
                </li>
              ))}
          </ul>
        ))}
      {data && canEdit && !adding && (
        <p>
          <button className="button" onClick={() => setAdding(true)}>
            {t('Instrument hinzufügen')}
          </button>
        </p>
      )}
      {data && canEdit && adding && (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            void add()
          }}
        >
          <div className="music-form-fields">
            <label>
              {t('Instrument')}
              <InstrumentSelect
                instruments={data.instruments}
                value={instrument}
                onChange={setInstrument}
              />
            </label>
            <label>
              {t('Register / Stimme')}
              <input
                maxLength={100}
                value={register}
                onChange={(e) => setRegister(e.target.value)}
              />
            </label>
          </div>
          <div className="actions">
            <button className="button button-primary" disabled={busy}>
              {t('Hinzufügen')}
            </button>
            <button
              className="button button-ghost"
              type="button"
              onClick={() => {
                setAdding(false)
                setInstrument('')
                setRegister('')
              }}
            >
              {t('Abbrechen')}
            </button>
          </div>
        </form>
      )}
      <p>
        <Link to={`/musik/musiker?mitglied=${memberId}`}>{t('Im Musikbereich öffnen')}</Link>
      </p>
    </section>
  )
}
