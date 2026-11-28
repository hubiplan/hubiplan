import { useState } from 'react'
import { leaveTo } from '../../api/peering.ts'
import { socialApi } from '../../api/website.ts'
import type { SocialFeed, SocialKind } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { PostList } from './PostList.tsx'
import { hostOf } from './socialHelpers.ts'

const KIND_LABEL: Record<SocialKind, string> = {
  instagram: t('Instagram'),
  facebook: t('Facebook-Seite'),
}

function statusText(f: SocialFeed): string {
  if (f.status === 'ok') {
    const until = f.token_expires_at
      ? t(', Zugang bis {x}', { x: formatDate(f.token_expires_at) })
      : ''
    const last = f.last_sync_at
      ? t(', zuletzt abgerufen {x}', { x: formatDateTime(f.last_sync_at) })
      : ''
    return t('verbunden mit {x}{until}{last}', { x: f.account_name || t('dem Konto'), until, last })
  }
  return f.status_label
}

export function FeedCard({
  feed,
  canManage,
  onChanged,
}: {
  feed: SocialFeed
  canManage: boolean
  onChanged: () => void
}) {
  const org = useActiveOrg()
  const [open, setOpen] = useState(feed.status === 'new' || feed.status === 'choose')
  const [appId, setAppId] = useState(feed.app_id)
  const [configId, setConfigId] = useState(feed.config_id)
  const [viaFacebook, setViaFacebook] = useState(feed.via_facebook)
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [showPosts, setShowPosts] = useState(false)

  async function run(action: () => Promise<unknown>, done?: string) {
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      await action()
      if (done) setInfo(done)
      onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      if (
        appId !== feed.app_id ||
        configId !== feed.config_id ||
        viaFacebook !== feed.via_facebook ||
        secret
      ) {
        await socialApi.save(org.id, feed.id, {
          app_id: appId,
          config_id: configId,
          via_facebook: viaFacebook,
          ...(secret ? { app_secret: secret } : {}),
        })
      }
      const { url } = await socialApi.connect(org.id, feed.id)
      leaveTo.go(url)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  const title = `${KIND_LABEL[feed.kind]}${feed.department_name ? ` (${feed.department_name})` : ''}`
  const connected = feed.status === 'ok' || feed.status === 'error'
  return (
    <section className="social-feed" aria-label={title}>
      <h3>
        <button
          type="button"
          className="link-button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {title}
        </button>
      </h3>
      <p className="small">
        {statusText(feed)}
        {feed.post_count > 0 && t(' · {post_count} Beiträge', { post_count: feed.post_count })}
        {feed.pending_count > 0 &&
          t(' · {pending_count} warten auf Freigabe', { pending_count: feed.pending_count })}
      </p>
      {feed.last_error && (
        <Alert kind={feed.status === 'ok' ? 'info' : 'error'}>{feed.last_error}</Alert>
      )}
      {canManage && feed.comments_need_connect && connected && (
        <Alert kind="info">
          {t(
            'Kommentare sind eingeschaltet. Bitte den Kanal neu verbinden, damit Meta das Lesen der Kommentare erlaubt.',
          )}
        </Alert>
      )}
      {open && (
        <>
          {canManage && feed.status === 'choose' && (
            <SelectField
              label={
                feed.kind === 'instagram'
                  ? t('Welches Instagram-Konto?')
                  : t('Welche Facebook-Seite?')
              }
              value=""
              onChange={(e) =>
                e.target.value &&
                void run(() => socialApi.choosePage(org.id, feed.id, e.target.value))
              }
            >
              <option value="">
                {feed.kind === 'instagram' ? t('Konto') : t('Seite')} {t('wählen …')}
              </option>
              {feed.pages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </SelectField>
          )}
          {canManage && !connected && feed.status !== 'choose' && (
            <>
              <div className="grid-2">
                <Field
                  label={t('App-ID')}
                  inputMode="numeric"
                  value={appId}
                  onChange={(e) => setAppId(e.target.value.trim())}
                  hint={t('Aus eurer Meta-App (siehe Anleitung unten).')}
                />
                <Field
                  label={t('App-Geheimnis')}
                  type="password"
                  autoComplete="off"
                  value={secret}
                  placeholder={feed.has_secret ? t('gespeichert') : ''}
                  onChange={(e) => setSecret(e.target.value.trim())}
                  hint={t('Wird verschlüsselt gespeichert und nie wieder angezeigt.')}
                />
                {(feed.kind === 'facebook' || viaFacebook) && (
                  <Field
                    label={t('Konfigurations-ID')}
                    inputMode="numeric"
                    value={configId}
                    onChange={(e) => setConfigId(e.target.value.trim())}
                    hint={
                      feed.kind === 'instagram'
                        ? t(
                            'Aus „Facebook Login for Business“ › Konfigurationen. Leer: über die mit Instagram verknüpfte Facebook-Seite.',
                          )
                        : t('Nur nötig, wenn eure App mit „Facebook Login for Business“ arbeitet.')
                    }
                  />
                )}
                {feed.kind === 'instagram' && (
                  <Checkbox
                    label={t('Alter Weg „Instagram-Login“')}
                    checked={!viaFacebook}
                    onChange={(v) => setViaFacebook(!v)}
                    hint={t(
                      'Nur für ältere Meta-Apps, die „API-Einrichtung mit Instagram-Login“ noch anbieten.',
                    )}
                  />
                )}
              </div>
              <RedirectInfo
                feed={feed}
                busy={busy}
                onUseUnit={() =>
                  void run(
                    () => socialApi.save(org.id, feed.id, { use_unit_address: true }),
                    t('Der Kanal nutzt jetzt die Vereinsadresse.'),
                  )
                }
              />
              <div className="button-row">
                <button
                  type="button"
                  className="button"
                  disabled={busy || !appId || (!secret && !feed.has_secret)}
                  onClick={() => void connect()}
                >
                  {t('Mit')} {feed.kind === 'instagram' ? t('Instagram') : t('Facebook')}{' '}
                  {t('verbinden')}
                </button>
              </div>
            </>
          )}
          {canManage && (
            <div className="grid-2">
              <SelectField
                label={t('Künftig abgerufene Beiträge')}
                value={feed.mode}
                onChange={(e) =>
                  void run(() =>
                    socialApi.save(org.id, feed.id, { mode: e.target.value as SocialFeed['mode'] }),
                  )
                }
                hint={t(
                  'Gilt nur für neue Beiträge; wartende bleiben wartend. „Erst nach Freigabe“, wenn Fotos von Dritten dabei sein können.',
                )}
              >
                <option value="auto">{t('automatisch zeigen')}</option>
                <option value="approval">{t('erst nach Freigabe')}</option>
              </SelectField>
              <Field
                label={t('Beiträge halten')}
                type="number"
                min={1}
                max={50}
                defaultValue={feed.max_posts}
                onBlur={(e) =>
                  Number(e.target.value) !== feed.max_posts &&
                  void run(() =>
                    socialApi.save(org.id, feed.id, { max_posts: Number(e.target.value) }),
                  )
                }
                hint={t('Die neuesten; ältere fallen weg.')}
              />
              <Checkbox
                label={t('Link zum Beitrag zeigen')}
                checked={feed.show_link}
                onChange={(v) => void run(() => socialApi.save(org.id, feed.id, { show_link: v }))}
                hint={t('schlichter Textlink, kein Meta-Element')}
              />
              <Checkbox
                label={t('Hashtags am Ende weglassen')}
                checked={feed.strip_hashtags}
                onChange={(v) =>
                  void run(() => socialApi.save(org.id, feed.id, { strip_hashtags: v }))
                }
              />
              <Checkbox
                label={t('Likes und Kommentarzahl zeigen')}
                checked={feed.show_counts}
                onChange={(v) =>
                  void run(() => socialApi.save(org.id, feed.id, { show_counts: v }))
                }
                hint={
                  feed.kind === 'facebook'
                    ? t('Bei Facebook zählen alle Reaktionen, nicht nur „Gefällt mir“.')
                    : t('Fehlt, wenn das Konto Likes ausgeblendet hat.')
                }
              />
              <SelectField
                label={t('Kommentare zeigen')}
                value={feed.comments}
                onChange={(e) =>
                  void run(() =>
                    socialApi.save(org.id, feed.id, {
                      comments: e.target.value as SocialFeed['comments'],
                    }),
                  )
                }
                hint={t(
                  'Kommentare stammen von anderen Personen. Zeigt sie nur, wenn ihr das verantworten könnt; „erst nach Freigabe“ ist sicherer. Ausschalten löscht alle gespeicherten Kommentare. Nach dem Einschalten den Kanal neu verbinden.',
                )}
              >
                <option value="off">{t('nicht zeigen')}</option>
                <option value="approval">{t('erst nach Freigabe')}</option>
                <option value="auto">{t('automatisch zeigen')}</option>
              </SelectField>
            </div>
          )}
          <div className="button-row">
            {feed.post_count > 0 && (
              <button
                type="button"
                className="button button-ghost"
                aria-expanded={showPosts}
                onClick={() => setShowPosts(!showPosts)}
              >
                {showPosts ? t('Beiträge zuklappen') : t('Beiträge ansehen')}
              </button>
            )}
            {canManage && feed.pending_count > 0 && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  const n = feed.pending_count
                  const text =
                    n === 1 ? t('den wartenden Beitrag') : t('alle {n} wartenden Beiträge', { n })
                  if (
                    await confirmDialog({
                      message: t(
                        '{x}{x2} auf der Webseite zeigen? Prüfe vorher, ob alle Fotos gezeigt werden dürfen.',
                        { x: text[0].toUpperCase(), x2: text.slice(1) },
                      ),
                      confirmLabel: t('Auf der Webseite zeigen'),
                      danger: false,
                    })
                  )
                    void run(async () => {
                      const r = await socialApi.publishPending(org.id, feed.id)
                      setInfo(
                        r.published === 1
                          ? t('1 Beitrag freigegeben.')
                          : t('{published} Beiträge freigegeben.', { published: r.published }),
                      )
                    })
                }}
              >
                {feed.pending_count === 1
                  ? t('1 wartenden Beitrag veröffentlichen')
                  : t('{pending_count} wartende Beiträge veröffentlichen', {
                      pending_count: feed.pending_count,
                    })}
              </button>
            )}
            {canManage && connected && (
              <>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await socialApi.sync(org.id, feed.id)
                      setInfo(t('Der Abruf läuft im Hintergrund. Bitte später neu laden.'))
                    })
                  }
                >
                  {t('Jetzt abrufen')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => void connect()}
                >
                  {t('Neu verbinden')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={async () => {
                    if (
                      await confirmDialog({
                        final: true,
                        message: t(
                          'Verbindung trennen? Der Zugang und alle abgerufenen Beiträge mit Bildern werden gelöscht.',
                        ),
                        confirmLabel: t('Verbindung trennen'),
                      })
                    )
                      void run(() => socialApi.disconnect(org.id, feed.id), t('Getrennt.'))
                  }}
                >
                  {t('Trennen')}
                </button>
              </>
            )}
            {canManage && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={async () => {
                  if (
                    await confirmDialog({
                      final: true,
                      message: t('{title} mit allen Beiträgen löschen?', { title }),
                      confirmLabel: t('Löschen'),
                    })
                  )
                    void run(() => socialApi.remove(org.id, feed.id))
                }}
              >
                {t('Kanal löschen')}
              </button>
            )}
          </div>
          {info && <Alert kind="success">{info}</Alert>}
          {error && <Alert kind="error">{error}</Alert>}
          {showPosts && <PostList feed={feed.id} onChanged={onChanged} />}
        </>
      )}
    </section>
  )
}

function CopyCode({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <span className="button-row">
      <code className="break-all">{value}</code>
      <button
        type="button"
        className="button"
        onClick={() => {
          void navigator.clipboard?.writeText(value).then(() => setCopied(true))
        }}
      >
        {copied ? t('Kopiert') : t('Kopieren')}
      </button>
    </span>
  )
}

/** Weiterleitungs-URI des Kanals zum Kopieren (Issue #723). */
function RedirectInfo({
  feed,
  busy,
  onUseUnit,
}: {
  feed: SocialFeed
  busy: boolean
  onUseUnit: () => void
}) {
  const host = hostOf(feed.redirect_uri)
  const elsewhere = host !== '' && host !== window.location.host
  return (
    <div className="small">
      <p className="muted">{t('In der Meta-App als Weiterleitungs-URI (OAuth) eintragen:')}</p>
      <CopyCode value={feed.redirect_uri} />
      {host && (
        <p className="muted">
          {t('Als App-Domain:')} <code>{host.split(':')[0]}</code>
        </p>
      )}
      {elsewhere && (
        <p className="muted">
          {t(
            'Meta schickt nach dem Verbinden zu {adresse} zurück. Bitte dort anmelden und den Kanal von dort aus verbinden.',
            {
              adresse: `https://${host}`,
            },
          )}
        </p>
      )}
      {feed.unit_redirect_uri && (
        <div className="muted">
          <p>
            {t(
              'Dieser Kanal nutzt noch die frühere Adresse, die in eurer Meta-App eingetragen ist. Ihr könnt auf die Vereinsadresse umstellen:',
            )}{' '}
            <code className="break-all">{feed.unit_redirect_uri}</code>
          </p>
          <p>
            {t(
              'Danach die neue Adresse in der Meta-App als Weiterleitungs-URI und App-Domain eintragen und den Kanal neu verbinden.',
            )}
          </p>
          <div className="button-row">
            <button type="button" className="button" disabled={busy} onClick={onUseUnit}>
              {t('Vereinsadresse verwenden')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
