import { useState } from 'react'
import 'prosemirror-view/style/prosemirror.css'
import type { LinkTarget } from '../../api/website.ts'
import { Modal } from '../Modal.tsx'
import { Alert, Field, SelectField } from '../ui.tsx'
import { PAGE_PREFIX, normalizeHref } from './markdown.ts'
import { t } from '../../i18n/index.ts'

export function LinkDialog({
  current,
  targets,
  onCancel,
  onApply,
}: {
  current: string
  targets: LinkTarget[]
  onCancel: () => void
  /** null: Link entfernen */
  onApply: (href: string | null) => void
}) {
  const isPage = current.startsWith(PAGE_PREFIX)
  const [kind, setKind] = useState<'page' | 'url'>(
    isPage || (!current && targets.length > 0) ? 'page' : 'url',
  )
  const [page, setPage] = useState(isPage ? current : '')
  const [url, setUrl] = useState(isPage ? '' : current)
  const [error, setError] = useState<string | null>(null)
  const pageOptions =
    isPage && !targets.some((tm) => tm.href === current)
      ? [
          ...targets,
          { href: current, label: t('{x} (unbekannt)', { x: current.slice(PAGE_PREFIX.length) }) },
        ]
      : targets

  function submit() {
    if (kind === 'page') {
      if (!page) {
        setError(t('Bitte eine Seite wählen.'))
        return
      }
      onApply(page)
      return
    }
    const href = normalizeHref(url)
    if (!href) {
      setError(t('Bitte eine Adresse wie https://www.beispiel.de oder name@beispiel.de angeben.'))
      return
    }
    onApply(href)
  }

  return (
    <Modal title={current ? t('Link ändern') : t('Link einfügen')} onClose={onCancel}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          e.stopPropagation()
          submit()
        }}
      >
        {targets.length > 0 && (
          <fieldset className="texteditor-linkkind">
            <legend>{t('Ziel')}</legend>
            <label>
              <input
                type="radio"
                name="ziel"
                checked={kind === 'page'}
                onChange={() => setKind('page')}
              />{' '}
              {t('Seite unserer Webseite')}
            </label>
            <label>
              <input
                type="radio"
                name="ziel"
                checked={kind === 'url'}
                onChange={() => setKind('url')}
              />{' '}
              {t('andere Adresse oder E-Mail')}
            </label>
          </fieldset>
        )}
        {kind === 'page' && targets.length > 0 ? (
          <SelectField label={t('Seite')} value={page} onChange={(e) => setPage(e.target.value)}>
            <option value="">{t('Seite wählen …')}</option>
            {pageOptions.map((tm) => (
              <option key={tm.href} value={tm.href}>
                {tm.label}
              </option>
            ))}
          </SelectField>
        ) : (
          <Field
            label={t('Adresse (https://… oder E-Mail)')}
            value={url}
            autoFocus
            onChange={(e) => setUrl(e.target.value)}
          />
        )}
        {error && <Alert kind="error">{error}</Alert>}
        <div className="button-row">
          <button type="submit" className="button button-primary">
            {current ? t('Übernehmen') : t('Einfügen')}
          </button>
          {current && (
            <button type="button" className="button button-ghost" onClick={() => onApply(null)}>
              {t('Link entfernen')}
            </button>
          )}
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        </div>
      </form>
    </Modal>
  )
}
