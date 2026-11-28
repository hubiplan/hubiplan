import { EditAt, EditSlot, editKey } from '../../components/EditInPlace.tsx'
import { Fragment, useState } from 'react'
import { meetingApi } from '../../api/meetings.ts'
import type { MeetingBase, MeetingKind } from '../../api/meetings.ts'
import { ApiError } from '../../api/client.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { SaveStatus } from '../../components/ui.tsx'
import './meetings.css'

function baseLabel(base: MeetingBase) {
  return {
    general: t('Mitgliederversammlung'),
    board: t('Vorstandssitzung'),
    committee: t('Gremium oder Ausschuss'),
  }[base]
}

const BASES: MeetingBase[] = ['general', 'board', 'committee']

export function KindsCard({
  base,
  canEdit,
  kinds,
  error,
  reload,
}: {
  base: string
  canEdit: boolean
  kinds: MeetingKind[] | null
  error: string | null
  reload: () => Promise<void>
}) {
  const [editing, setEditing] = useState<MeetingKind | 'new' | null>(null)
  const [message, setMessage] = useState('')
  return (
    <section className="card">
      <h2>{t('Arten und Fristen')}</h2>
      <div className="aid-row">
        <Why k="meeting_invite" />
        <Why k="meeting_quorum" />
        <Why k="meeting_proxies" />
        <Why k="meeting_motions" />
      </div>
      <p className="muted small">
        {t(
          'Die Art legt die Voreinstellungen fest, zum Beispiel die Einladungsfrist aus der Satzung. HUBIplan warnt, wenn eine Einladung zu spät hinausgeht.',
        )}
      </p>
      {error && <p role="alert">{error}</p>}
      {message && <p role="alert">{message}</p>}
      <table className="table">
        <thead>
          <tr>
            <th>{t('Name')}</th>
            <th>{t('Grundtyp')}</th>
            <th className="num">{t('Frist (Tage)')}</th>
            <th>{t('Protokoll sehen')}</th>
            {canEdit && <th className="actions">{t('Aktionen')}</th>}
          </tr>
        </thead>
        <tbody>
          {(kinds ?? []).map((k) => (
            <Fragment key={k.id}>
              <tr key={k.id}>
                <td>
                  {k.name}
                  {!k.active && <span className="badge">{t('abgeschaltet')}</span>}
                </td>
                <td>{baseLabel(k.base)}</td>
                <td className="num">{k.invite_days}</td>
                <td>
                  {k.minutes_for === 'voters'
                    ? t('auch alle Stimmberechtigten')
                    : t('nur Rollen mit Leserecht')}
                </td>
                {canEdit && (
                  <td className="actions">
                    <div className="button-row">
                      <button className="button button-ghost" onClick={() => setEditing(k)}>
                        {t('Bearbeiten')}
                      </button>
                      {!k.used && (
                        <button
                          className="button button-ghost"
                          onClick={async () => {
                            setMessage('')
                            const yes = await confirmDialog({
                              final: true,
                              title: t('Art „{name}“ löschen?', { name: k.name }),
                              confirmLabel: t('Löschen'),
                            })
                            if (!yes) return
                            try {
                              await meetingApi.removeKind(base, k.id)
                              await reload()
                            } catch (err) {
                              setMessage(errorMessage(err))
                            }
                          }}
                        >
                          {t('Löschen')}
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
              <EditSlot id={editKey('meeting-kind', k.id)} colSpan={canEdit ? 5 : 4} />
            </Fragment>
          ))}
        </tbody>
      </table>
      {canEdit && !editing && (
        <div className="button-row">
          <button className="button" onClick={() => setEditing('new')}>
            {t('Art hinzufügen')}
          </button>
        </div>
      )}
      {editing && (
        <EditAt at={editing === 'new' ? null : editKey('meeting-kind', editing.id)}>
          <KindForm
            key={editing === 'new' ? 'new' : editing.id}
            base={base}
            kind={editing === 'new' ? null : editing}
            onDone={async (saved) => {
              setEditing(null)
              if (saved) await reload()
            }}
          />
        </EditAt>
      )}
    </section>
  )
}

function KindForm({
  base,
  kind,
  onDone,
}: {
  base: string
  kind: MeetingKind | null
  onDone: (saved: boolean) => void
}) {
  const initial = {
    name: kind?.name ?? '',
    base: kind?.base ?? ('general' as MeetingBase),
    invite_days: String(kind?.invite_days ?? 14),
    invite_form: kind?.invite_form ?? 'mail',
    minutes_for: kind?.minutes_for ?? 'board',
    quorum_percent: kind?.quorum_percent ? String(kind.quorum_percent) : '',
    proxies_allowed: kind?.proxies_allowed ?? false,
    motion_days: kind ? (kind.motion_days === null ? '' : String(kind.motion_days)) : '7',
    online_voting: kind?.online_voting ?? false,
    remote_allowed: kind?.remote_allowed ?? false,
    active: kind?.active ?? true,
  }
  const f = useForm(initial)
  const form = f.values
  const setForm = f.setValues
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const toInput = (values: Partial<typeof initial>) => {
    const data: Record<string, unknown> = { ...values }
    if ('invite_days' in values) data.invite_days = Number(values.invite_days)
    if ('quorum_percent' in values)
      data.quorum_percent = values.quorum_percent ? Number(values.quorum_percent) : null
    if ('motion_days' in values)
      data.motion_days = values.motion_days === '' ? null : Number(values.motion_days)
    return data
  }
  // Bestehende Arten speichern automatisch, neue erst mit „Anlegen“
  const auto = useAutoSave(
    f,
    async (changes) => {
      if (changes.invite_days === '')
        throw new ApiError(400, { invite_days: t('Bitte eine Frist angeben.') })
      await meetingApi.updateKind(base, kind!.id, toInput(changes))
    },
    { enabled: !!kind },
  )
  useDraftGuard(!kind && JSON.stringify(form) !== JSON.stringify(initial))
  return (
    <form
      className="stack kind-form"
      onSubmit={async (e) => {
        e.preventDefault()
        if (kind) return
        setBusy(true)
        setError('')
        try {
          await meetingApi.createKind(base, toInput(form))
          onDone(true)
        } catch (err) {
          setError(errorMessage(err))
          setBusy(false)
        }
      }}
    >
      <h3>{kind ? t('Art bearbeiten') : t('Neue Art')}</h3>
      {kind && <SaveStatus auto={auto} />}
      <label className="field">
        <span>{t('Name')}</span>
        <input
          value={form.name}
          maxLength={100}
          required
          onChange={(e) => setForm((v) => ({ ...v, name: e.target.value }))}
        />
      </label>
      <label className="field">
        <span>{t('Grundtyp')}</span>
        <select
          value={form.base}
          onChange={(e) => setForm((v) => ({ ...v, base: e.target.value as MeetingBase }))}
        >
          {BASES.map((b) => (
            <option key={b} value={b}>
              {baseLabel(b)}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>{t('Einladungsfrist in Tagen')}</span>
        <input
          type="number"
          min={0}
          max={365}
          required
          value={form.invite_days}
          onChange={(e) => setForm((v) => ({ ...v, invite_days: e.target.value }))}
        />
      </label>
      <label className="field">
        <span>{t('Einladung')}</span>
        <select
          value={form.invite_form}
          onChange={(e) =>
            setForm((v) => ({ ...v, invite_form: e.target.value as MeetingKind['invite_form'] }))
          }
        >
          <option value="mail">{t('E-Mail, sonst Brief')}</option>
          <option value="letter">{t('Brief an alle')}</option>
        </select>
      </label>
      <label className="field">
        <span>{t('Beschlussfähig ab (Prozent der Stimmberechtigten, leer: immer)')}</span>
        <input
          type="number"
          min={1}
          max={100}
          value={form.quorum_percent}
          onChange={(e) => setForm((v) => ({ ...v, quorum_percent: e.target.value }))}
        />
      </label>
      <label className="field">
        <span>{t('Protokoll sehen')}</span>
        <select
          value={form.minutes_for}
          onChange={(e) =>
            setForm((v) => ({ ...v, minutes_for: e.target.value as MeetingKind['minutes_for'] }))
          }
        >
          <option value="board">{t('nur Rollen mit Leserecht')}</option>
          <option value="voters">{t('auch alle Stimmberechtigten')}</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.proxies_allowed}
          onChange={(e) => setForm((v) => ({ ...v, proxies_allowed: e.target.checked }))}
        />
        {t('Vertretung mit Vollmacht erlaubt')}
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.online_voting}
          onChange={(e) => setForm((v) => ({ ...v, online_voting: e.target.checked }))}
        />
        {t('Online-Abstimmung am Handy erlaubt')}
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.remote_allowed}
          onChange={(e) => setForm((v) => ({ ...v, remote_allowed: e.target.checked }))}
        />
        {t('Teilnahme aus der Ferne erlaubt (hybride Versammlung)')}
      </label>
      {form.remote_allowed && (
        <p className="muted small">
          {t(
            'Teilnahme und Abstimmung aus der Ferne braucht eine Grundlage in der Satzung oder einen Beschluss der Mitgliederversammlung (§ 32 Abs. 2 BGB). Bitte vorher prüfen.',
          )}
        </p>
      )}
      <label className="field">
        <span>{t('Anträge von Mitgliedern bis Tage vorher (leer: keine Anträge)')}</span>
        <input
          type="number"
          min={0}
          max={90}
          value={form.motion_days}
          onChange={(e) => setForm((v) => ({ ...v, motion_days: e.target.value }))}
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={form.active}
          onChange={(e) => setForm((v) => ({ ...v, active: e.target.checked }))}
        />
        {t('Für neue Versammlungen wählbar')}
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        {kind ? (
          <button
            type="button"
            className="button"
            onClick={async () => {
              // Schließt erst, wenn alles gespeichert ist
              if (await auto.flush()) onDone(true)
            }}
          >
            {t('Schließen')}
          </button>
        ) : (
          <>
            <button className="button button-primary" disabled={busy}>
              {t('Anlegen')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => onDone(false)}>
              {t('Abbrechen')}
            </button>
          </>
        )}
      </div>
    </form>
  )
}
