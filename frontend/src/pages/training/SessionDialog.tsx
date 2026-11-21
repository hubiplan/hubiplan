// Ein Training: Angaben, Anwesenheitsliste und Einchecken per QR-Code.
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { trainingApi } from '../../api/training.ts'
import type {
  CheckinCode,
  SessionDetail,
  SessionDraft,
  TrainingOptions,
  WeaponClass,
} from '../../api/training.ts'
import { Modal } from '../../components/Modal.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Checkbox, Field, Loading, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

export type SessionForm = SessionDraft

function today() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function emptyForm(initial?: Partial<SessionForm>): SessionForm {
  return {
    date: today(),
    starts_at: '',
    ends_at: '',
    title: t('Übungsabend'),
    kind: 'practice',
    location: '',
    leader: '',
    note: '',
    shooting: false,
    discipline: '',
    weapon_class: '',
    caliber: '',
    permit_required: true,
    event: null,
    ...initial,
  }
}

function fromDetail(d: SessionDetail): SessionForm {
  return {
    date: d.date,
    starts_at: d.starts_at ?? '',
    ends_at: d.ends_at ?? '',
    title: d.title,
    kind: d.kind,
    location: d.location,
    leader: d.leader,
    note: d.note,
    shooting: d.shooting,
    discipline: d.discipline,
    weapon_class: d.weapon_class,
    caliber: d.caliber,
    permit_required: d.permit_required,
    version: d.version,
  }
}

/** Adresse im QR-Code: öffnet den Mitgliederbereich; die App liest Training und Code. */
export function trainingCheckinLink(code: CheckinCode) {
  const params = new URLSearchParams({ v: String(code.club), c: code.code })
  return `${window.location.origin}/mein-bereich/training/da/${code.session}?${params}`
}

export function SessionDialog({
  base,
  id,
  initial,
  options,
  onClose,
  onCreated,
}: {
  base: string
  id: number | null
  initial?: Partial<SessionForm>
  options: TrainingOptions
  onClose: () => void
  onCreated: (id: number) => void
}) {
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [form, setForm] = useState<SessionForm>(() => emptyForm(initial))
  const [editing, setEditing] = useState(id === null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (id === null) return
    let stopped = false
    trainingApi
      .get(base, id)
      .then((d) => {
        if (stopped) return
        setDetail(d)
        setForm(fromDetail(d))
      })
      .catch((err) => !stopped && setError(errorMessage(err)))
    return () => {
      stopped = true
    }
  }, [base, id])

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (id === null) {
        const created = await trainingApi.create(base, form)
        onCreated(created.id)
      } else {
        const next = await trainingApi.update(base, id, form)
        setDetail(next)
        setForm(fromDetail(next))
        setEditing(false)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    if (!detail) return
    const yes = await confirmDialog({
      title: t('Training löschen?'),
      message: t(
        'Die Anwesenheit und die Einträge im Schießbuch aus diesem Training werden mit gelöscht.',
      ),
      confirmLabel: t('Löschen'),
      final: true,
    })
    if (!yes) return
    try {
      await trainingApi.remove(base, detail.id)
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  const title = id === null ? t('Neues Training') : (detail?.title ?? t('Training'))
  const set = <K extends keyof SessionForm>(key: K, value: SessionForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }))
  const pickDiscipline = (name: string) => {
    const known = options.disciplines.find((d) => d.name === name)
    setForm((f) => ({
      ...f,
      discipline: name,
      ...(known
        ? {
            weapon_class: known.weapon_class,
            caliber: f.caliber || known.caliber,
            permit_required: known.permit_required,
          }
        : {}),
    }))
  }
  return (
    <Modal title={title} onClose={onClose} guard={editing}>
      {error && <p role="alert">{error}</p>}
      {id !== null && !detail && !error && <Loading />}
      {editing ? (
        <form className="stack" onSubmit={save}>
          <div className="grid-2">
            <Field
              label={t('Bezeichnung')}
              value={form.title}
              required
              maxLength={200}
              onChange={(e) => set('title', e.target.value)}
            />
            <SelectField
              label={t('Art')}
              value={form.kind}
              onChange={(e) => set('kind', e.target.value as SessionForm['kind'])}
            >
              {options.kinds.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </SelectField>
            <Field
              label={t('Datum')}
              type="date"
              value={form.date}
              required
              onChange={(e) => set('date', e.target.value)}
            />
            <div className="grid-2">
              <Field
                label={t('Beginn')}
                type="time"
                value={form.starts_at}
                onChange={(e) => set('starts_at', e.target.value)}
              />
              <Field
                label={t('Ende')}
                type="time"
                value={form.ends_at}
                onChange={(e) => set('ends_at', e.target.value)}
              />
            </div>
            <Field
              label={t('Ort (optional)')}
              value={form.location}
              maxLength={200}
              onChange={(e) => set('location', e.target.value)}
            />
            <Field
              label={t('Leitung (optional)')}
              value={form.leader}
              maxLength={200}
              hint={t('Übungsleiter oder Trainerin, auch Gäste')}
              onChange={(e) => set('leader', e.target.value)}
            />
          </div>
          <Field
            label={t('Notiz (optional)')}
            value={form.note}
            maxLength={300}
            onChange={(e) => set('note', e.target.value)}
          />
          {options.shooting_enabled && (
            <fieldset className="stack-sm training-shooting">
              <legend>{t('Schießbuch')}</legend>
              <Checkbox
                label={t('Schießtermin: Anwesende bekommen einen Eintrag im Schießbuch')}
                checked={form.shooting}
                onChange={(v) => set('shooting', v)}
              />
              {form.shooting && (
                <div className="grid-2">
                  <Field
                    label={t('Disziplin')}
                    value={form.discipline}
                    required
                    maxLength={100}
                    suggestions={options.disciplines.map((d) => ({
                      value: d.name,
                      detail: d.caliber,
                    }))}
                    onChange={(e) => pickDiscipline(e.target.value)}
                  />
                  <SelectField
                    label={t('Waffe')}
                    value={form.weapon_class}
                    required
                    onChange={(e) => set('weapon_class', e.target.value as WeaponClass)}
                  >
                    <option value="">{t('bitte wählen')}</option>
                    <option value="short">{t('Kurzwaffe')}</option>
                    <option value="long">{t('Langwaffe')}</option>
                  </SelectField>
                  <Field
                    label={t('Kaliber (optional)')}
                    value={form.caliber}
                    maxLength={40}
                    onChange={(e) => set('caliber', e.target.value)}
                  />
                  <Checkbox
                    label={t('erlaubnispflichtige Waffe')}
                    hint={t('Luftdruckwaffen zählen nicht für § 14 WaffG')}
                    checked={form.permit_required}
                    onChange={(v) => set('permit_required', v)}
                  />
                </div>
              )}
            </fieldset>
          )}
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={busy}>
              {id === null ? t('Anlegen') : t('Speichern')}
            </button>
            {id !== null && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => {
                  if (detail) setForm(fromDetail(detail))
                  setEditing(false)
                }}
              >
                {t('Abbrechen')}
              </button>
            )}
          </div>
        </form>
      ) : (
        detail && (
          <SessionView
            base={base}
            detail={detail}
            setDetail={setDetail}
            onEdit={() => setEditing(true)}
            onRemove={remove}
          />
        )
      )}
    </Modal>
  )
}

function SessionView({
  base,
  detail,
  setDetail,
  onEdit,
  onRemove,
}: {
  base: string
  detail: SessionDetail
  setDetail: (d: SessionDetail) => void
  onEdit: () => void
  onRemove: () => void
}) {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | 'all' | null>(null)
  const [filter, setFilter] = useState('')
  const toggle = async (membership: number, present: boolean) => {
    setBusy(membership)
    setError('')
    try {
      setDetail(await trainingApi.setPresent(base, detail.id, membership, present))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }
  const present = detail.attendance.filter((r) => r.present).length
  const q = filter.trim().toLocaleLowerCase()
  const rows = q
    ? detail.attendance.filter((r) => r.name.toLocaleLowerCase().includes(q))
    : detail.attendance
  return (
    <div className="stack">
      <p className="muted">
        {[
          detail.kind_label,
          detail.starts_at
            ? `${detail.starts_at}${detail.ends_at ? `–${detail.ends_at}` : ''}`
            : '',
          detail.location,
          detail.leader ? t('Leitung: {name}', { name: detail.leader }) : '',
          detail.shooting
            ? `${detail.discipline} (${detail.weapon_class === 'short' ? t('Kurzwaffe') : t('Langwaffe')})`
            : '',
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {detail.note && <p>{detail.note}</p>}
      {detail.can_edit && (
        <div className="button-row">
          <button type="button" className="button button-secondary" onClick={onEdit}>
            {t('Bearbeiten')}
          </button>
          <button type="button" className="button button-danger" onClick={onRemove}>
            {t('Löschen')}
          </button>
        </div>
      )}
      {detail.can_edit && <CheckinCard base={base} detail={detail} setDetail={setDetail} />}
      <h3>{t('Anwesenheit: {n} von {total}', { n: present, total: detail.attendance.length })}</h3>
      {error && <p role="alert">{error}</p>}
      {detail.attendance.length > 12 && (
        <Field
          label={t('Name suchen')}
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      )}
      <ul className="plain-list training-attendance">
        {rows.map((r) => (
          <li key={r.membership}>
            <Checkbox
              label={r.name}
              hint={
                r.source === 'code' ? t('per QR-Code') : r.shooting ? t('im Schießbuch') : undefined
              }
              checked={r.present}
              disabled={!detail.can_edit}
              busy={busy === r.membership}
              onChange={(v) => void toggle(r.membership, v)}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}

function CheckinCard({
  base,
  detail,
  setDetail,
}: {
  base: string
  detail: SessionDetail
  setDetail: (d: SessionDetail) => void
}) {
  const [code, setCode] = useState<CheckinCode | null>(null)
  const [big, setBig] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!detail.checkin_open) return
    let stopped = false
    const timer = { id: 0 }
    const load = async () => {
      try {
        const next = await trainingApi.code(base, detail.id)
        if (stopped) return
        setCode(next)
        timer.id = window.setTimeout(load, Math.min(5, next.refresh_in) * 1000)
      } catch (err) {
        if (stopped) return
        setError(errorMessage(err))
        timer.id = window.setTimeout(load, 15000)
      }
    }
    void load()
    return () => {
      stopped = true
      window.clearTimeout(timer.id)
    }
  }, [base, detail.id, detail.checkin_open])
  const shown = detail.checkin_open ? code : null
  const switchTo = async (open: boolean) => {
    setError('')
    try {
      setDetail(await trainingApi.checkin(base, detail.id, open))
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  if (!detail.checkin_possible && !detail.checkin_open) return null
  const link = shown ? trainingCheckinLink(shown) : ''
  // Neu Eingecheckte erscheinen beim nächsten Laden der Liste
  const fresh = shown && shown.count !== detail.attendance.filter((r) => r.present).length
  return (
    <section className="card stack-sm">
      <h3>{t('Einchecken per QR-Code')}</h3>
      <p className="muted small">
        {t(
          'Mitglieder scannen den Code mit der HUBIplan-App oder der Handykamera. Der Code wechselt alle 30 Sekunden.',
        )}
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button
          type="button"
          className={detail.checkin_open ? 'button button-ghost' : 'button'}
          onClick={() => void switchTo(!detail.checkin_open)}
        >
          {detail.checkin_open ? t('Einchecken schließen') : t('Einchecken öffnen')}
        </button>
        {link && (
          <button type="button" className="button button-ghost" onClick={() => setBig(true)}>
            {t('Code groß zeigen')}
          </button>
        )}
        {fresh && (
          <button
            type="button"
            className="button button-ghost"
            onClick={async () => setDetail(await trainingApi.get(base, detail.id))}
          >
            {t('Liste aktualisieren ({n} da)', { n: shown.count })}
          </button>
        )}
      </div>
      {link && (
        <div className="live-code">
          <QRCodeSVG value={link} size={200} marginSize={2} title={t('QR-Code zum Einchecken')} />
          <p className="muted small">
            {t('Neuer Code in {n} Sekunden.', { n: shown!.refresh_in })}
          </p>
        </div>
      )}
      {big && link && (
        <div
          className="live-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t('QR-Code zum Einchecken')}
        >
          <QRCodeSVG value={link} size={520} marginSize={2} title={t('QR-Code zum Einchecken')} />
          <p>{t('Mit der HUBIplan-App oder der Handykamera scannen.')}</p>
          <button type="button" className="button" onClick={() => setBig(false)} autoFocus>
            {t('Schließen')}
          </button>
        </div>
      )}
    </section>
  )
}
