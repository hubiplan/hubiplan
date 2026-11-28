// Webseite › Zustand: Prüfliste, Zustand und Grundeinstellungen, Vorschau und Löschen.
import type { HomeTarget, WebsiteSettings } from '../../api/website.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { Why } from '../../learning/Aids.tsx'
import { DraftBar } from './DesignPreview.tsx'
import { SiteLanguage } from './SiteLanguage.tsx'
import { TargetField } from './TargetField.tsx'
import { t } from '../../i18n/index.ts'
import { ImageHosts } from './ImageHosts.tsx'
import { TextEditor } from '../../components/texteditor/TextEditor.tsx'
import { PreviewCard } from './PreviewCard.tsx'

import type { WebsiteAdminModel } from './useWebsiteAdmin.tsx'
import { Link } from 'react-router-dom'
import { Term } from '../../learning/Aids.tsx'
import { type TermKey } from '../../learning/content.ts'
import { type Website } from '../../api/website.ts'

const STATE_TEXT: Record<string, string> = {
  off: t('Aus: Die Webseite ist nicht erreichbar.'),
  maintenance: t('Wartung: Besucher sehen nur eine Wartungsseite mit Impressum und Datenschutz.'),
  public: t('Öffentlich: Die Webseite ist für alle sichtbar.'),
}

/** Was vor dem Schalten auf „öffentlich“ erledigt sein muss. */
const CHECK_LINKS: Record<string, string> = {
  imprint: '/einstellungen/impressum',
  responsible: '/einstellungen/impressum?feld=verantwortlich',
  privacy: '/einstellungen/datenschutz',
  privacy_outdated: '/einstellungen/datenschutz',
  domain: '/webseite/domain',
}

/** Begriffe mit „?“ an den Punkten der Prüfliste */
const CHECK_TERMS: Partial<Record<string, TermKey>> = {
  imprint: 'imprint',
  responsible: 'responsible',
}

function ChecklistCard({ website }: { website: Website }) {
  const open = website.checks.filter((c) => !c.ok)
  return (
    <div className="card card-wide">
      <h2>{t('Prüfliste vor dem Veröffentlichen')}</h2>
      {open.length === 0 && <Alert kind="success">{t('Alles erledigt.')}</Alert>}
      <ul className="plain-list">
        {website.checks.map((c) => (
          <li key={c.key}>
            <span aria-hidden="true">{c.ok ? '✓' : c.blocking ? '✗' : '!'}</span>{' '}
            <strong>
              {CHECK_TERMS[c.key] ? <Term k={CHECK_TERMS[c.key]!}>{c.label}</Term> : c.label}
            </strong>
            {!c.ok && (
              <>
                {' '}
                <span className="muted small">
                  {c.blocking ? t('(nötig) ') : t('(Empfehlung) ')}
                  {c.hint}
                </span>
                {CHECK_LINKS[c.key] && (
                  <>
                    {' '}
                    <Link to={CHECK_LINKS[c.key]} className="small">
                      {t('Erledigen')}
                    </Link>
                  </>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      {open.some((c) => c.blocking) && (
        <p className="muted small">
          {t(
            'Solange ein nötiger Punkt offen ist, lässt sich die Webseite nicht auf „Öffentlich“ schalten.',
          )}
        </p>
      )}
    </div>
  )
}

export function WebsiteOverview({ m }: { m: WebsiteAdminModel }) {
  const {
    data,
    website,
    onReset,
    reload,
    v,
    set,
    errors,
    auto,
    message,
    history,
    remove,
    settings,
  } = m
  return (
    <>
      <ChecklistCard website={website} />
      {settings(
        t('Zustand'),
        <>
          <SelectField
            label={t('Zustand der Webseite')}
            value={v.state}
            error={errors.state}
            hint={STATE_TEXT[v.state]}
            onChange={(e) => set('state', e.target.value as WebsiteSettings['state'])}
          >
            <option value="off">{t('Aus')}</option>
            <option value="maintenance">{t('Wartung')}</option>
            <option value="public">{t('Öffentlich')}</option>
          </SelectField>
          {data.preview_only && (
            <Alert kind="info">
              {t(
                'Auf diesem Server sind alle Webseiten nur in der Vorschau sichtbar (Testserver).',
              )}
            </Alert>
          )}
          <TextEditor
            label={t('Hinweis auf der Wartungsseite')}
            value={v.maintenance_text}
            error={errors.maintenance_text}
            rows={3}
            onChange={(text) => set('maintenance_text', text)}
          />
          <p className="muted small">
            {t('Schlüssel der Webseite in der öffentlichen Schnittstelle:')}{' '}
            <code>{website.public_key}</code>
          </p>
        </>,
      )}
      {/* S4 (Ralf 14.11.): Grundeinstellungen stehen bei „Zustand“ */}
      <SiteLanguage
        value={v.language ?? 'de'}
        error={errors.language}
        render={(field) => settings(t('Sprache der Webseite'), field)}
        onChange={(lang) => set('language', lang)}
      />
      {/* F3 (Ralf 16.11.2026): Anrede ist Ton der Texte, keine Gestaltung; bleibt im Stil (Entwurf) */}
      {Array.isArray(data.style_catalog?.options.address) &&
        settings(
          t('Anrede'),
          <>
            <SelectField
              label={t('Anrede auf der Webseite')}
              value={String(v.style?.address ?? 'formal')}
              hint={t(
                'Gilt für Kontaktformular und Terminseite. Den Kasten neben dem Formular (z. B. „Du möchtest mitmachen?“) schreibst du unter Webseite › Texte › Einleitungen der Bereiche › Kontakt.',
              )}
              onChange={(e) => {
                const next = { ...(v.style ?? {}) }
                if (e.target.value === 'formal') delete next.address
                else next.address = e.target.value
                history.track('style', next)
              }}
            >
              <option value="formal">{t('Sie')}</option>
              <option value="informal">{t('du')}</option>
            </SelectField>
            <p className="muted small">
              {t('Wie die Gestaltung gilt sie erst nach „Veröffentlichen“.')}
            </p>
            <DraftBar website={website} auto={auto} canManage={data.can_manage} onReset={onReset} />
          </>,
        )}
      {settings(
        t('Suchmaschinen'),
        <>
          <Checkbox
            label={t('Suchmaschinen dürfen die Webseite aufnehmen')}
            checked={v.allow_indexing}
            onChange={(on) => set('allow_indexing', on)}
          />
          <Why k="web_indexing" />
        </>,
      )}
      {settings(
        t('Bilder für KI-Assistenten'),
        <ImageHosts
          value={v.image_hosts ?? []}
          error={errors.image_hosts}
          disabled={!data.can_manage}
          onChange={(next) => set('image_hosts', next)}
        />,
      )}
      {settings(
        t('Hinweisleiste'),
        <>
          <p className="muted small">
            {t(
              'Ein kurzer Hinweis oben auf allen Seiten, z. B. „Sommerfest 22.–25.8.: Programm“. Er erscheint nur im Zeitraum und verschwindet danach von selbst.',
            )}
          </p>
          <Field
            label={t('Text der Hinweisleiste')}
            value={v.notice_text ?? ''}
            maxLength={200}
            error={errors.notice_text}
            hint={t('leer = keine Hinweisleiste')}
            onChange={(e) => set('notice_text', e.target.value)}
          />
          <TargetField
            data={data}
            website={website}
            value={
              v.notice_target && Object.keys(v.notice_target).length > 0
                ? (v.notice_target as HomeTarget)
                : null
            }
            onChange={(target) => set('notice_target', target ?? {})}
          />
          {errors.notice_target && <Alert kind="error">{errors.notice_target}</Alert>}
          {v.notice_target && Object.keys(v.notice_target).length > 0 && (
            <Field
              label={t('Beschriftung des Knopfs')}
              value={v.notice_button ?? ''}
              maxLength={40}
              error={errors.notice_button}
              hint={t('leer = „Mehr erfahren“')}
              onChange={(e) => set('notice_button', e.target.value)}
            />
          )}
          <div className="grid-2">
            <SelectField
              label={t('Stil')}
              value={v.notice_style ?? 'accent'}
              error={errors.notice_style}
              onChange={(e) =>
                set('notice_style', e.target.value as WebsiteSettings['notice_style'])
              }
            >
              <option value="accent">{t('Akzentfarbe')}</option>
              <option value="alert">{t('Achtung (Signalfarbe)')}</option>
              <option value="festive">{t('Festlich (Akzentfarbe mit Muster)')}</option>
              <option value="quiet">{t('Schlicht in Kopffarbe')}</option>
            </SelectField>
            <SelectField
              label={t('Platz')}
              value={v.notice_place ?? 'below'}
              error={errors.notice_place}
              hint={
                v.notice_place === 'float' ? t('Besucher können den Kasten schließen.') : undefined
              }
              onChange={(e) =>
                set('notice_place', e.target.value as WebsiteSettings['notice_place'])
              }
            >
              <option value="top">{t('über dem Kopf')}</option>
              <option value="below">{t('unter dem Kopf')}</option>
              <option value="float">{t('schwebend unten')}</option>
            </SelectField>
            <SelectField
              label={t('Symbol')}
              value={v.notice_icon ?? 'auto'}
              error={errors.notice_icon}
              onChange={(e) => set('notice_icon', e.target.value as WebsiteSettings['notice_icon'])}
            >
              <option value="auto">{t('passend zum Stil')}</option>
              <option value="megaphone">{t('Lautsprecher')}</option>
              <option value="calendar">{t('Kalender')}</option>
              <option value="star">{t('Stern')}</option>
              <option value="info">{t('Info')}</option>
              <option value="alert">{t('Ausrufezeichen')}</option>
              <option value="none">{t('kein Symbol')}</option>
            </SelectField>
            <Field
              label={t('Countdown bis')}
              type="date"
              value={v.notice_date ?? ''}
              error={errors.notice_date}
              hint={t(
                'zeigt „noch 5 Tage“; leer = Datum des Termins, wenn das Ziel ein Termin ist',
              )}
              onChange={(e) => set('notice_date', e.target.value || null)}
            />
          </div>
          <div className="grid-2">
            <Field
              label={t('Zeigen ab')}
              type="date"
              value={v.notice_from ?? ''}
              error={errors.notice_from}
              hint={t('leer = sofort')}
              onChange={(e) => set('notice_from', e.target.value || null)}
            />
            <Field
              label={t('Zeigen bis')}
              type="date"
              value={v.notice_until ?? ''}
              error={errors.notice_until}
              hint={t('leer = ohne Ende')}
              onChange={(e) => set('notice_until', e.target.value || null)}
            />
          </div>
        </>,
      )}
      <PreviewCard data={data} website={website} onChange={reload} />
      {data.can_manage && (
        <div className="card card-wide">
          <h2>{t('Webseite entfernen')}</h2>
          {message && <Alert kind="error">{message}</Alert>}
          <button type="button" className="button button-danger" onClick={() => void remove()}>
            {t('Webseite entfernen')}
          </button>
        </div>
      )}
    </>
  )
}
