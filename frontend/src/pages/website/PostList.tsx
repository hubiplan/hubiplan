import { useState } from 'react'
import { socialApi } from '../../api/website.ts'
import type { SocialPost } from '../../api/website.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function PostList({ feed, onChanged }: { feed: number; onChanged: () => void }) {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => socialApi.posts(org.id, feed), [org.id, feed])
  const [saveError, setSaveError] = useState<string | null>(null)
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  async function setCommentState(id: number, state: SocialPost['comments'][number]['state']) {
    setSaveError(null)
    try {
      await socialApi.setComment(org.id, id, state)
      void reload()
    } catch (err) {
      setSaveError(errorMessage(err))
    }
  }
  async function setState(post: SocialPost, state: SocialPost['state']) {
    setSaveError(null)
    try {
      await socialApi.setPost(org.id, post.id, { state })
      void reload()
      onChanged()
    } catch (err) {
      setSaveError(errorMessage(err))
    }
  }
  return (
    <>
      {saveError && <Alert kind="error">{saveError}</Alert>}
      <ul className="plain-list social-posts">
        {data.map((p) => (
          <li key={p.id} className={p.state === 'hidden' ? 'muted' : undefined}>
            <PostImages post={p} onSaved={() => void reload()} />
            <div>
              <p className="small">
                {formatDateTime(p.published_at)} · {p.state_label}
                {p.media_type === 'video' && t(' · Video (nur Vorschaubild)')}
                {p.like_count !== null && <> · {t('{n} Likes', { n: p.like_count })}</>}
                {p.comment_count !== null && <> · {t('{n} Kommentare', { n: p.comment_count })}</>}
              </p>
              <p className="pre-line">{p.text || <em>{t('ohne Text')}</em>}</p>
              {p.comments.length > 0 && (
                <ul className="plain-list social-comments" aria-label={t('Kommentare')}>
                  {p.comments.map((k) => (
                    <li key={k.id} className={k.state === 'hidden' ? 'muted' : undefined}>
                      <p className="small">
                        <strong>{k.author || t('unbekannt')}</strong> ·{' '}
                        {formatDateTime(k.published_at)}
                        {k.state === 'pending' && <> · {t('wartet auf Freigabe')}</>}
                        {k.state === 'hidden' && <> · {t('ausgeblendet')}</>}
                      </p>
                      <p className="pre-line">{k.text}</p>
                      <div className="button-row">
                        {k.state !== 'visible' && (
                          <button
                            type="button"
                            className="button"
                            onClick={() => void setCommentState(k.id, 'visible')}
                          >
                            {k.state === 'pending'
                              ? t('Kommentar freigeben')
                              : t('Kommentar wieder zeigen')}
                          </button>
                        )}
                        {k.state !== 'hidden' && (
                          <button
                            type="button"
                            className="button button-ghost"
                            onClick={() => void setCommentState(k.id, 'hidden')}
                          >
                            {t('Kommentar ausblenden')}
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              <div className="button-row">
                {p.state !== 'visible' && (
                  <button
                    type="button"
                    className="button"
                    onClick={() => void setState(p, 'visible')}
                  >
                    {p.state === 'pending' ? t('Freigeben') : t('Wieder zeigen')}
                  </button>
                )}
                {p.state !== 'hidden' && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => void setState(p, 'hidden')}
                  >
                    {t('Ausblenden')}
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

/**
 * Alle Bilder eines Beitrags mit Anzahl, Vergrößerung und Alternativtext (UX-Audit 31.10. N08):
 * vor der Freigabe muss jedes Foto prüfbar sein, nicht nur die ersten vier.
 */
function PostImages({ post, onSaved }: { post: SocialPost; onSaved: () => void }) {
  const org = useActiveOrg()
  const [large, setLarge] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  if (post.images.length === 0) return <div className="social-post-images" />
  const shown = post.images.find((i) => i.id === large)
  async function saveAlt(id: number, text: string) {
    setError(null)
    setSaved(false)
    try {
      await socialApi.setPost(org.id, post.id, { alt_texts: { [String(id)]: text } })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <div className="social-post-images">
      <p className="small">
        {post.images.length === 1 ? t('1 Bild') : t('{n} Bilder', { n: post.images.length })}
        {post.images.some((i) => i.is_video) && t(' (Video: nur Vorschaubild)')}
      </p>
      <div className="social-post-thumbs">
        {post.images.map((i, n) => (
          <button
            key={i.id}
            type="button"
            className="link-button"
            aria-pressed={large === i.id}
            aria-label={
              large === i.id
                ? t('Bild {x} von {n} verkleinern', { x: n + 1, n: post.images.length })
                : t('Bild {x} von {n} vergrößern', { x: n + 1, n: post.images.length })
            }
            onClick={() => setLarge(large === i.id ? null : i.id)}
          >
            <img src={i.small_url} alt={i.alt_text} width={80} height={60} />
          </button>
        ))}
      </div>
      {shown && (
        <figure className="social-post-large">
          <img src={shown.url} alt={shown.alt_text} />
          <figcaption>
            <Field
              key={shown.id}
              label={t('Alternativtext Bild {x}', { x: post.images.indexOf(shown) + 1 })}
              defaultValue={shown.alt_text}
              maxLength={300}
              hint={t(
                'Kurz beschreiben, was zu sehen ist; wird beim Verlassen des Felds gespeichert.',
              )}
              onBlur={(e) =>
                e.target.value !== shown.alt_text && void saveAlt(shown.id, e.target.value)
              }
            />
            {saved && (
              <p className="small" role="status">
                {t('Gespeichert.')}
              </p>
            )}
            {error && <Alert kind="error">{error}</Alert>}
          </figcaption>
        </figure>
      )}
    </div>
  )
}
