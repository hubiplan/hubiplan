import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { RecordPager } from '../../components/liste/RecordPager.tsx'
import { isMinor, memberApi } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { SuggestCorrection } from './FederationMembersPage.tsx'
import { FieldsTab } from './FieldsTab.tsx'
import { PhotoSection } from './PhotoSection.tsx'
import { ContactPersons } from './ContactPersons.tsx'
import { MemberHouseholds } from './MemberHouseholds.tsx'
import { PublicationSection } from './PublicationSection.tsx'
import { AuditUndo } from '../../components/AuditUndo.tsx'
import { firstOfSet } from '../../components/undo.ts'
import { CardPanel } from '../../components/CardPanel.tsx'
import { cardApi, cardBase } from '../../api/cards.ts'
import { t } from '../../i18n/index.ts'
import { CompetitionsTab } from '../competitions/MemberTab.tsx'
import { FeesTab } from './FeesTab.tsx'
import { MusicTab } from './MusicTab.tsx'
import { AtAGlance } from './AtAGlance.tsx'
import { MemberHeader } from './MemberHeader.tsx'
import { RolesTab } from './RolesTab.tsx'
import { MembershipTab } from './MembershipTab.tsx'
import { MasterData } from './MasterData.tsx'
import { MemberFileSection } from './MemberFileSection.tsx'

type Tab =
  | 'stammdaten'
  | 'mitgliedschaft'
  | 'beitraege'
  | 'rollen'
  | 'wettbewerbe'
  | 'musik'
  | 'foto'
  | 'zusatzfelder'
  | 'verlauf'

/** Reiter in Arbeitsreihenfolge (Konzept Mitgliedsakte S-03) */
const TABS: { id: Tab; label: string }[] = [
  { id: 'stammdaten', label: t('Stammdaten') },
  { id: 'mitgliedschaft', label: t('Mitgliedschaft') },
  { id: 'beitraege', label: t('Beiträge') },
  { id: 'rollen', label: t('Rollen und Konto') },
  { id: 'wettbewerbe', label: t('Wettbewerbe') },
  { id: 'musik', label: t('Musik') },
  { id: 'foto', label: t('Foto & Webseite') },
  { id: 'zusatzfelder', label: t('Zusatzfelder') },
  { id: 'verlauf', label: t('Verlauf') },
]

export function MemberFilePage() {
  const org = useActiveOrg()
  const id = Number(useParams().id)
  const { data, error, setData, reload } = useLoad(() => memberApi.detail(org.id, id), [org.id, id])
  // Bereich steht in der Adresse: Zurück, Neuladen und Links öffnen ihn wieder (NMF-07)
  const [params] = useSearchParams()
  const navigate = useNavigate()
  // Reiter nur mit freigeschaltetem Modul (Menüprüfung 2, N-08); Musik zusätzlich mit Leserecht
  const tabs = TABS.filter(
    (tmx) =>
      (tmx.id !== 'wettbewerbe' || org.modules.includes('competitions')) &&
      (tmx.id !== 'beitraege' || org.modules.includes('billing')) &&
      (tmx.id !== 'musik' ||
        (org.modules.includes('music') && org.permissions.includes('music.view'))),
  )
  const tab: Tab = tabs.find((tmx) => tmx.id === params.get('bereich'))?.id ?? 'stammdaten'
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const tabLink = (to: Tab) => (to === 'stammdaten' ? '.' : `?bereich=${to}`)

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />

  return (
    <section>
      <RecordPager
        list={`mitglieder.${org.id}`}
        current={data.id}
        path={(id) => `/mitglieder/${id}`}
        label={{ prev: t('Vorheriges Mitglied'), next: t('Nächstes Mitglied') }}
      />
      <MemberHeader org={org} member={data} canEdit={canEdit} tabs={tabs.map((tmx) => tmx.id)} />
      <AtAGlance org={org} member={data} tabs={tabs.map((tmx) => tmx.id)} />
      <nav className="tabs member-tabs" aria-label={t('Bereiche der Mitgliedsakte')}>
        {tabs.map((tmx) => (
          <Link
            key={tmx.id}
            to={tabLink(tmx.id)}
            className={`tab${tab === tmx.id ? ' active' : ''}`}
            aria-current={tab === tmx.id ? 'page' : undefined}
          >
            {tmx.label}
          </Link>
        ))}
      </nav>
      {/* Handy: alle Bereiche als Auswahlliste statt seitlich wischbarer Reiter */}
      <label className="member-tabs-select">
        <span>{t('Bereich')}</span>
        <select value={tab} onChange={(ev) => void navigate(tabLink(ev.target.value as Tab))}>
          {tabs.map((tmx) => (
            <option key={tmx.id} value={tmx.id}>
              {tmx.label}
            </option>
          ))}
        </select>
      </label>
      {tab === 'stammdaten' && (
        <div className="stack">
          <MasterData
            key={data.id}
            org={org}
            member={data}
            canEdit={canEdit && !data.managed_by}
            onSaved={setData}
          />
          {(data.kind === 'organization' ||
            (data.contact_persons ?? []).length > 0 ||
            isMinor(data.birth_date)) && (
            <ContactPersons
              key={`ansprechpartner-${data.id}`}
              orgId={org.id}
              memberId={data.id}
              contacts={data.contact_persons ?? []}
              canEdit={canEdit}
              guardians={data.kind !== 'organization'}
              onChange={() => void reload()}
            />
          )}
          {(data.households ?? []).length > 0 && (
            <MemberHouseholds households={data.households ?? []} />
          )}
          {(data.contact_for ?? []).length > 0 && (
            <p className="muted">
              {t('Ansprechpartner für:')}{' '}
              {(data.contact_for ?? []).map((c, i) => (
                <span key={c.member_id}>
                  {i > 0 && ', '}
                  <Link to={`/mitglieder/${c.member_id}`}>{c.name}</Link>
                </span>
              ))}
            </p>
          )}
          {data.managed_by && (
            <SuggestCorrection
              orgId={org.id}
              member={data}
              owner={data.managed_by.name}
              intro={`Stammdaten und Kontakt pflegt ${data.managed_by.name} auf einer eigenen HUBIplan-Instanz (Verbund). Mitgliedschaft, Mitgliedsart und Beitrag bleiben hier. Hier lässt sich eine Korrektur vorschlagen.`}
            />
          )}
        </div>
      )}
      {tab === 'mitgliedschaft' && (
        <MembershipTab
          org={org}
          member={data}
          canEdit={canEdit}
          reload={reload}
          setData={setData}
        />
      )}
      {tab === 'beitraege' && (
        <FeesTab org={org} member={data} canEdit={canEdit} onSaved={setData} />
      )}
      {tab === 'rollen' && <RolesTab org={org} member={data} canEdit={canEdit} reload={reload} />}
      {tab === 'wettbewerbe' && <CompetitionsTab org={org.id} membership={data.id} />}
      {tab === 'musik' && <MusicTab orgId={org.id} memberId={data.id} />}
      {tab === 'foto' && (
        <div className="stack">
          <PhotoSection
            key={`foto-${data.id}`}
            orgId={org.id}
            memberId={data.id}
            initial={{
              photo: data.photo,
              photo_consent_at: data.photo_consent_at,
              photo_consent_source: data.photo_consent_source,
            }}
            canManage={org.permissions.includes(PERM.photosManage)}
            hasEmail={!!data.contact?.email}
            organization={data.kind === 'organization'}
            onChange={() => void reload()}
          />
          {org.modules.includes('website') && (
            <PublicationSection
              key={`veroeffentlichung-${data.id}`}
              orgId={org.id}
              memberId={data.id}
              canEdit={canEdit}
            />
          )}
          {org.permissions.includes(PERM.cardsView) && (
            <CardPanel
              key={`ausweis-${data.id}`}
              base={cardBase.org(org.id, data.id)}
              pdfUrl={cardApi.orgPdfUrl(org.id, { mitglied: data.id })}
              canEdit={org.permissions.includes(PERM.cardsManage)}
            />
          )}
        </div>
      )}
      {tab === 'zusatzfelder' && <FieldsTab orgId={org.id} memberId={data.id} canEdit={canEdit} />}
      {tab === 'verlauf' && <HistoryTab orgId={org.id} memberId={data.id} />}
    </section>
  )
}

function HistoryTab({ orgId, memberId }: { orgId: number; memberId: number }) {
  const { data, error } = useLoad(() => memberApi.history(orgId, memberId), [orgId, memberId])
  const first = firstOfSet(data ?? [])
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <MemberFileSection title={t('Verlauf')}>
      {data.length === 0 ? (
        <p className="muted">{t('Noch keine Einträge.')}</p>
      ) : (
        <ul className="audit-list">
          {data.map((entry) => (
            <li key={entry.id}>
              <div>
                <strong>{entry.object_type}</strong> {entry.action_label}
              </div>
              <div className="muted small">
                {formatDateTime(entry.timestamp)} · {entry.user_email || t('System')}
                {entry.via ? t(' · über {via}', { via: entry.via }) : ''}
              </div>
              {Object.keys(entry.changes).length > 0 && (
                <ul className="changes small">
                  {Object.entries(entry.changes).map(([field, [before, after]]) => (
                    <li key={field}>
                      {field}: {String(before ?? '–')} → {String(after ?? '–')}
                    </li>
                  ))}
                </ul>
              )}
              <AuditUndo entry={entry} orgId={orgId} showAction={first.has(entry.id)} />
            </li>
          ))}
        </ul>
      )}
    </MemberFileSection>
  )
}
