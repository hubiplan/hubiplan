// Pinnwand: Beiträge zeigen und schreiben, für Verwaltung und Mitgliederbereich gleich.
// Kein Chat: Mitglieder lesen, schreiben darf nur, wer das Recht dazu hat.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { pinboardApi } from '../../api/pinboard.ts'
import type { Notice, NoticeDraft, NoticeList } from '../../api/pinboard.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Checkbox, EmptyState } from '../../components/ui.tsx'
import { t, tn } from '../../i18n/index.ts'
import { formatDay, formatDayTime } from '../../i18n/format.ts'
import './pinboard.css'

const EMPTY: NoticeDraft = {
  text: '',
  pinned: false,
  visible_until: '',
  push: false,
  photos: [],
  department: null,
}

/** Formular für einen neuen Beitrag */
export function NoticeForm({
  list,
  onSave,
  onCancel,
}: {
  list: NoticeList
  onSave: (draft: NoticeDraft) => Promise<boolean>
  onCancel?: () => void
}) {
  const targets = list.targets ?? []
  const [draft, setDraft] = useState<NoticeDraft>({
    ...EMPTY,
    department: targets.length ? targets[0].department : null,
  })
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof NoticeDraft>(key: K, value: NoticeDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const tooMany = draft.photos.length > list.max_photos
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (tooMany || !draft.text.trim()) return
    setBusy(true)
    try {
      if (await onSave(draft)) setDraft({ ...EMPTY, department: draft.department })
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="card stack pinboard-form" onSubmit={submit}>
      <h2>{t('Neuer Beitrag')}</h2>
      {targets.length > 1 && (
        <label className="field">
          <span>{t('An')}</span>
          <select
            value={draft.department ?? ''}
            onChange={(e) => set('department', e.target.value ? Number(e.target.value) : null)}
          >
            {targets.map((target) => (
              <option key={target.department ?? 0} value={target.department ?? ''}>
                {target.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="field">
        <span>{t('Text')}</span>
        <textarea
          rows={4}
          required
          maxLength={list.max_text}
          value={draft.text}
          placeholder={t('z. B. Der Bus fährt heute 10 Minuten später ab.')}
          onChange={(e) => set('text', e.target.value)}
        />
      </label>
      <label className="field">
        <span>{t('Fotos (optional, höchstens {n})', { n: list.max_photos })}</span>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          onChange={(e) => set('photos', Array.from(e.target.files ?? []))}
        />
      </label>
      {tooMany && (
        <Alert kind="error">{t('Bitte höchstens {n} Fotos wählen.', { n: list.max_photos })}</Alert>
      )}
      <div className="pinboard-options">
        <label className="field">
          <span>{t('Anzeigen bis (optional)')}</span>
          <input
            type="date"
            value={draft.visible_until}
            onChange={(e) => set('visible_until', e.target.value)}
          />
        </label>
      </div>
      <Checkbox
        label={t('Oben anheften')}
        checked={draft.pinned}
        onChange={(v) => set('pinned', v)}
      />
      <Checkbox
        label={t('Push an die App senden')}
        hint={t('nur an Mitglieder mit App und Benachrichtigungen, keine E-Mail')}
        checked={draft.push}
        onChange={(v) => set('push', v)}
      />
      <div className="button-row">
        <button className="button" type="submit" disabled={busy || tooMany}>
          {busy ? t('Wird gespeichert …') : t('Veröffentlichen')}
        </button>
        {onCancel && (
          <button className="button button-secondary" type="button" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </div>
    </form>
  )
}

/** Ein Beitrag mit Fotos; mit Recht auch ändern, anheften und löschen */
export function NoticeCard({
  notice,
  base,
  showUnit = true,
  onChanged,
}: {
  notice: Notice
  base: string
  showUnit?: boolean
  onChanged: (message: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(notice.text)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const run = async (action: () => Promise<unknown>, done: string) => {
    setBusy(true)
    setFailure(null)
    try {
      await action()
      setEditing(false)
      await onChanged(done)
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    const yes = await confirmDialog({
      final: true,
      title: t('Beitrag löschen?'),
      message: notice.text.slice(0, 120),
      confirmLabel: t('Löschen'),
    })
    if (yes) await run(() => pinboardApi.remove(base, notice.id), t('Beitrag gelöscht.'))
  }
  const classes = ['card', 'stack-sm', 'notice-card']
  if (notice.pinned) classes.push('notice-pinned')
  if (notice.expired) classes.push('notice-expired')
  return (
    <article className={classes.join(' ')}>
      <header className="notice-head">
        <span className="notice-from">{showUnit || !notice.unit ? notice.from : notice.unit}</span>
        {notice.pinned && <span className="badge badge-brand">{t('angeheftet')}</span>}
        {notice.new && <span className="badge badge-info">{t('neu')}</span>}
        {notice.expired && <span className="badge">{t('abgelaufen')}</span>}
      </header>
      {editing ? (
        <label className="field">
          <span className="sr-only">{t('Text')}</span>
          <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
      ) : (
        <p className="notice-text">{notice.text}</p>
      )}
      {notice.photos.length > 0 && (
        <div className="notice-photos">
          {notice.photos.map((p, i) => (
            <a key={p.id} href={p.url} target="_blank" rel="noopener">
              <img
                src={p.url}
                alt={t('Foto {n} von {m}', { n: i + 1, m: notice.photos.length })}
                loading="lazy"
                width={p.width || undefined}
                height={p.height || undefined}
              />
            </a>
          ))}
        </div>
      )}
      <p className="muted small">
        {[
          notice.author,
          formatDayTime(notice.created_at),
          notice.edited_at ? t('geändert') : '',
          notice.visible_until
            ? t('sichtbar bis {day}', { day: formatDay(notice.visible_until) })
            : '',
          notice.pushed ? t('per Push gemeldet') : '',
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {failure && <Alert kind="error">{failure}</Alert>}
      {notice.can_edit && (
        <div className="button-row">
          {editing ? (
            <>
              <button
                className="button"
                type="button"
                disabled={busy || !text.trim()}
                onClick={() =>
                  run(() => pinboardApi.update(base, notice, { text }), t('Beitrag gespeichert.'))
                }
              >
                {t('Speichern')}
              </button>
              <button
                className="button button-secondary"
                type="button"
                onClick={() => {
                  setText(notice.text)
                  setEditing(false)
                }}
              >
                {t('Abbrechen')}
              </button>
            </>
          ) : (
            <>
              <button
                className="button button-secondary"
                type="button"
                disabled={busy}
                onClick={() => setEditing(true)}
              >
                {t('Bearbeiten')}
              </button>
              <button
                className="button button-secondary"
                type="button"
                disabled={busy}
                onClick={() =>
                  run(
                    () => pinboardApi.update(base, notice, { pinned: !notice.pinned }),
                    notice.pinned ? t('Beitrag nicht mehr angeheftet.') : t('Beitrag angeheftet.'),
                  )
                }
              >
                {notice.pinned ? t('Nicht mehr anheften') : t('Anheften')}
              </button>
              <button
                className="button button-danger"
                type="button"
                disabled={busy}
                onClick={remove}
              >
                {t('Löschen')}
              </button>
            </>
          )}
        </div>
      )}
    </article>
  )
}

/** Liste samt Formular; „writable“: Formular anbieten */
export function PinboardList({
  base,
  list,
  writable,
  showUnit,
  reload,
  emptyText,
}: {
  base: string
  list: NoticeList
  writable: boolean
  showUnit?: boolean
  reload: () => Promise<unknown>
  emptyText: string
}) {
  const [notice, setNotice] = useState('')
  const [failure, setFailure] = useState<string | null>(null)
  const changed = async (message: string) => {
    await reload()
    setNotice(message)
  }
  const create = async (draft: NoticeDraft) => {
    setFailure(null)
    setNotice('')
    try {
      const made = await pinboardApi.create(base, draft)
      await reload()
      setNotice(
        made.push
          ? t('Beitrag veröffentlicht, Push geht an die App.')
          : t('Beitrag veröffentlicht.'),
      )
      return true
    } catch (err) {
      setFailure(errorMessage(err))
      return false
    }
  }
  return (
    <div className="stack pinboard">
      {writable && <NoticeForm list={list} onSave={create} />}
      {notice && <Alert kind="success">{notice}</Alert>}
      {failure && <Alert kind="error">{failure}</Alert>}
      {list.notices.length === 0 ? (
        <EmptyState title={t('Noch keine Beiträge')}>{emptyText}</EmptyState>
      ) : (
        <>
          <p className="muted small">{tn('{n} Beitrag', '{n} Beiträge', list.notices.length)}</p>
          {list.notices.map((n) => (
            <NoticeCard
              key={`${n.id}-${n.version}`}
              notice={n}
              base={base}
              showUnit={showUnit}
              onChanged={changed}
            />
          ))}
        </>
      )}
    </div>
  )
}
