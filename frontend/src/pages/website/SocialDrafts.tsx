// Webseite › Social Media: Entwürfe für Beiträge, die ein KI-Assistent vorbereitet hat
// (KI-Schnittstelle W3, docs/mcp.md). HUBIplan postet nichts selbst: Text kopieren,
// Bilder speichern und im eigenen Konto veröffentlichen.
import { useState } from 'react'
import { socialApi } from '../../api/website.ts'
import type { SocialDraft } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function SocialDrafts() {
  const org = useActiveOrg()
  const { data, reload } = useLoad(() => socialApi.drafts(org.id), [org.id])
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState<number | null>(null)
  if (!data || data.drafts.length === 0) return null

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function copy(d: SocialDraft) {
    try {
      await navigator.clipboard.writeText(d.text)
      setCopied(d.id)
    } catch {
      setError(t('Kopieren hat nicht geklappt. Bitte den Text von Hand markieren.'))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Entwürfe für Beiträge')}</h2>
      <p className="muted small">
        {t(
          'Vorschläge eines KI-Assistenten. HUBIplan veröffentlicht sie nicht selbst: Text kopieren, Bilder speichern und im eigenen Instagram- oder Facebook-Konto posten, danach als erledigt markieren.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {data.drafts.map((d) => (
        <div key={d.id} className={`social-draft${d.done_at ? ' muted' : ''}`}>
          <p className="muted small">
            {[
              d.channel_label,
              formatDateTime(d.created_at),
              d.created_by,
              d.via,
              d.done_at ? t('erledigt') : '',
            ]
              .filter(Boolean)
              .join(' · ')}
          </p>
          <p className="social-draft-text">{d.text}</p>
          {d.images.length > 0 && (
            <div className="social-draft-images">
              {d.images.map((img) => (
                <a key={img.id} href={img.url} target="_blank" rel="noopener" download>
                  <img src={img.small_url} alt={img.alt_text} loading="lazy" />
                </a>
              ))}
            </div>
          )}
          {data.can_manage && (
            <div className="button-row">
              <button type="button" className="button" onClick={() => void copy(d)}>
                {copied === d.id ? t('Kopiert') : t('Text kopieren')}
              </button>
              {!d.done_at && (
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void run(() => socialApi.setDraft(org.id, d.id, { done: true }))}
                >
                  {t('Als erledigt markieren')}
                </button>
              )}
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  void (async () => {
                    const ok = await confirmDialog({
                      title: t('Entwurf löschen?'),
                      confirmLabel: t('Löschen'),
                      danger: true,
                    })
                    if (ok) await run(() => socialApi.removeDraft(org.id, d.id))
                  })()
                }
              >
                {t('Löschen')}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
