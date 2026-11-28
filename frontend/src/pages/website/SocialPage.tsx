// Webseite › Social Media: Instagram-Profikonto und Facebook-Seite verbinden.
// HUBIplan holt die eigenen Beiträge serverseitig ab und speichert Text und Bilder
// selbst; Besucher der Webseite haben keinen Kontakt zu Meta. Jede Einheit nutzt
// ihre eigene Meta-App (App-ID und App-Geheimnis von developers.facebook.com).
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { socialApi } from '../../api/website.ts'
import type { SocialFeed, SocialKind } from '../../api/website.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, LoadError, SelectField, Loading } from '../../components/ui.tsx'
import { SocialLinksPanel } from '../../components/SocialLinksPanel.tsx'
import { SocialDrafts } from './SocialDrafts.tsx'
import { PERM } from '../../api/orgs.ts'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { FeedCard } from './FeedCard.tsx'
import { hostOf } from './socialHelpers.ts'

export function SocialPage() {
  const org = useActiveOrg()
  const [params, setParams] = useSearchParams()
  const { data, error, reload } = useLoad(() => socialApi.list(org.id), [org.id])
  const [adding, setAdding] = useState(false)

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />

  const back = params.get('verbunden') ? 'ok' : params.get('fehler')
  return (
    <>
      {back && (
        <Alert kind={back === 'ok' ? 'success' : 'error'}>
          {back === 'ok'
            ? t('Verbunden, die Beiträge wurden abgerufen.')
            : t('Nicht verbunden: {back}', { back })}{' '}
          <button type="button" className="link-button" onClick={() => setParams({})}>
            {t('Ausblenden')}
          </button>
        </Alert>
      )}
      {/* Kanäle (Profil-Links im Kopf der Webseite) und Beiträge an einer Stelle (Menüprüfung M-06) */}
      {(org.type === 'club' || org.type === 'federation') && (
        <SocialLinksPanel orgId={org.id} editable={org.permissions.includes(PERM.orgEdit)} />
      )}
      <div className="card card-wide">
        <h2>{t('Instagram und Facebook')}</h2>
        <p className="muted small">
          {t(
            'HUBIplan holt die Beiträge eurer eigenen Kanäle alle 30 Minuten ab und speichert Text und Fotos selbst. Die Webseite zeigt sie unter „Aktuelles“ und, wenn ihr wollt, auf der Startseite. Besucher haben dabei keinen Kontakt zu Instagram oder Facebook, es gibt keine Cookies und kein Tracking. Was ihr dort löscht, verschwindet auch hier.',
          )}
        </p>
        <Why k="web_social" />
        {data.feeds.length === 0 && <p className="muted">{t('Noch kein Kanal angelegt.')}</p>}
        {data.feeds.map((f) => (
          <FeedCard
            key={f.id}
            feed={f}
            canManage={data.can_manage}
            onChanged={() => void reload()}
          />
        ))}
        {data.can_manage &&
          (adding ? (
            <NewFeed
              units={data.units}
              existing={data.feeds}
              onDone={() => {
                setAdding(false)
                void reload()
              }}
            />
          ) : (
            <div className="button-row">
              <button type="button" className="button" onClick={() => setAdding(true)}>
                {t('Kanal hinzufügen')}
              </button>
            </div>
          ))}
      </div>
      <SocialDrafts />
      {data.can_manage && <SetupGuide redirectUri={data.redirect_uri} />}
    </>
  )
}

function NewFeed({
  units,
  existing,
  onDone,
}: {
  units: { id: number; name: string }[]
  existing: SocialFeed[]
  onDone: () => void
}) {
  const org = useActiveOrg()
  const [kind, setKind] = useState<SocialKind>('instagram')
  const [department, setDepartment] = useState<number | null>(null)
  // Beim Anlegen ausdrücklich wählen, „erst nach Freigabe“ vorausgewählt (UX-Audit 31.10. F10)
  const [mode, setMode] = useState<SocialFeed['mode']>('approval')
  const [error, setError] = useState<string | null>(null)
  const taken = existing.some((f) => f.kind === kind && f.department === department)
  async function create() {
    setError(null)
    try {
      await socialApi.create(org.id, { kind, department, mode })
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    }
  }
  return (
    <div className="social-feed">
      <div className="grid-2">
        <SelectField
          label={t('Netzwerk')}
          value={kind}
          onChange={(e) => setKind(e.target.value as SocialKind)}
        >
          <option value="instagram">{t('Instagram (Profikonto)')}</option>
          <option value="facebook">{t('Facebook-Seite')}</option>
        </SelectField>
        {units.length > 0 && (
          <SelectField
            label={t('Kanal von')}
            value={department ?? ''}
            onChange={(e) => setDepartment(e.target.value ? Number(e.target.value) : null)}
            hint={t('Kanäle einer Untereinheit erscheinen auf ihrer Seite.')}
          >
            <option value="">{org.name}</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </SelectField>
        )}
        <SelectField
          label={t('Abgerufene Beiträge')}
          value={mode}
          onChange={(e) => setMode(e.target.value as SocialFeed['mode'])}
          hint={t(
            '„Erst nach Freigabe“, wenn Fotos von Dritten dabei sein können. Später änderbar.',
          )}
        >
          <option value="approval">{t('erst nach Freigabe zeigen')}</option>
          <option value="auto">{t('automatisch zeigen')}</option>
        </SelectField>
      </div>
      {taken && <Alert kind="info">{t('Diesen Kanal gibt es hier schon.')}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <div className="button-row">
        <button type="button" className="button" disabled={taken} onClick={() => void create()}>
          {t('Anlegen')}
        </button>
        <button type="button" className="button button-ghost" onClick={onDone}>
          {t('Abbrechen')}
        </button>
      </div>
    </div>
  )
}

function SetupGuide({ redirectUri }: { redirectUri: string }) {
  return (
    <details className="card card-wide">
      <summary>
        <strong>{t('Anleitung: eigene Meta-App anlegen (einmalig, etwa 20 Minuten)')}</strong>
      </summary>
      <p className="muted small">
        {t(
          'Meta gibt Beiträge nur an eine registrierte „App“ heraus. Das ist keine Handy-App, sondern ein Eintrag bei Meta, der erlaubt, die Beiträge eurer eigenen Kanäle zu lesen. Weil ihr die App selbst anlegt, bleiben Zugang und Daten bei euch, und Meta muss nichts prüfen.',
        )}
      </p>
      <ol>
        <li>
          {t('Instagram: Konto auf')} <strong>{t('Profikonto')}</strong>{' '}
          {t(
            'umstellen (in der Instagram-App unter Einstellungen › Kontoart, „Business“ oder „Creator“). Private Konten gehen nicht. Facebook: Es geht nur eine',
          )}{' '}
          <strong>{t('Seite')}</strong>
          {t(', kein privates Profil.')}
        </li>
        <li>
          {t('Auf')} <strong>developers.facebook.com</strong>{' '}
          {t(
            'mit einem Facebook-Konto des Vorstands anmelden und ein Entwicklerkonto anlegen. Am besten die App im Business-Portfolio des Vereins anlegen und zwei Personen als Admins eintragen, damit sie bei einem Vorstandswechsel nicht verloren geht.',
          )}
        </li>
        <li>
          {t('„App erstellen“, Anwendungsfall')} <strong>{t('„Instagram API“')}</strong>{' '}
          {t('(Instagram) bzw.')} <strong>{t('„Alles auf deiner Seite verwalten“')}</strong>{' '}
          {t(
            '(Facebook). Die App bleibt im Entwicklungsmodus; Veröffentlichung, App-Prüfung und Unternehmensverifizierung sind nicht nötig.',
          )}
        </li>
        <li>
          {t('Instagram: Unter „API-Einrichtung mit Facebook-Login“ bzw. „Unified Login“ eine')}{' '}
          <strong>{t('Konfiguration')}</strong> {t('anlegen: Zugriffstoken')}{' '}
          <strong>{t('„Nutzerzugriffstoken“')}</strong>
          {t(
            '(Ablauf „läuft nie ab“, falls angeboten; „Systemnutzer“ funktioniert im Entwicklungsmodus nicht), Assets nur',
          )}{' '}
          <strong>{t('Instagram-Konten')}</strong>{' '}
          {t('(keine Werbekonten), Berechtigungen nur die Pflicht-Berechtigungen (')}
          <code>instagram_basic</code> {t('und die nicht abwählbaren). Die angezeigte')}{' '}
          <strong>{t('Konfigurations-ID')}</strong>{' '}
          {t(
            'oben eintragen. Wer sich anmeldet, muss Admin der App sein und das Instagram-Konto im Business-Portfolio verwalten. Alternativ ohne Konfiguration: Konfigurations-ID leer lassen, Anwendungsfall „Alles auf deiner Seite verwalten“ hinzufügen; HUBIplan findet das Instagram-Konto dann über die damit verknüpfte Facebook-Seite.',
          )}
        </li>
        <li>{t('Facebook: Wer die Seite verwaltet, muss Admin der App sein.')}</li>
        <li>
          {t('Als')} <strong>{t('Weiterleitungs-URI')}</strong> {t('(OAuth) eintragen:')}{' '}
          <code className="break-all">{redirectUri}</code> {t('und als')}{' '}
          <strong>{t('App-Domain')}</strong> <code>{hostOf(redirectUri).split(':')[0]}</code>
          {t('. Die genaue Adresse steht auch beim Kanal zum Kopieren.')}
        </li>
        <li>{t('Als Datenschutz-URL die Datenschutzhinweise eurer Webseite eintragen.')}</li>
        <li>
          <strong>{t('App-ID')}</strong> {t('und')} <strong>{t('App-Geheimcode')}</strong>{' '}
          {t(
            'aus App-Einstellungen › Allgemein oben eintragen und auf „verbinden“ klicken. Nur beim alten Weg „Instagram-Login“ gelten stattdessen „Instagram-App-ID“ und „Instagram-App-Geheimcode“.',
          )}
        </li>
      </ol>
      <p className="muted small">
        {t(
          'Rechte: Zeigt nur Fotos, die ihr auch auf der Webseite zeigen dürft. Hat ein Fotograf ein Bild nur für Instagram freigegeben oder sind Personen zu sehen, die nur „Social Media“ zugestimmt haben, wählt „erst nach Freigabe“ oder blendet den Beitrag aus. Videos zeigt die Webseite nur als Vorschaubild mit Link, weil Musik aus Instagram nur dort lizenziert ist. HUBIplan speichert Texte und Bilder der Beiträge und zeigt sie auf eurer Webseite; die Bilder werden dabei neu gespeichert, eingebettete Angaben wie der Name des Fotografen gehen verloren. Muss ein Fotograf genannt werden, gehört sein Name in den Beitragstext. Die Verbindung zu Instagram oder Facebook gibt euch keine Rechte an fremden Bildern.',
        )}
      </p>
    </details>
  )
}
