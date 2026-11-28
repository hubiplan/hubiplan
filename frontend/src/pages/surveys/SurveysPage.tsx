// Umfragen und Meinungsbilder: anlegen, starten, Ergebnis, Export (Verein und Untereinheit).
// Konzept: konzepte/umfragen-meinungsbilder.md.
import { useRowSort } from '../../components/RowSort.tsx'
import { useState } from 'react'
import { PERM } from '../../api/orgs.ts'
import { surveyApi } from '../../api/surveys.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { useDetailParam } from '../../components/detailParam.ts'
import { useLoad } from '../../components/forms.ts'
import { Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { endText } from './SurveyParts.tsx'
import './surveys.css'
import { Why } from '../../learning/Aids.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { EmptyList } from '../../components/EmptyList.tsx'
import { SurveyEditor } from './SurveyEditor.tsx'
import { statusLabel } from './surveysHelpers.ts'
import { SurveyDetail } from './SurveyDetail.tsx'

export function SurveysPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const enabled = active ? active.modules.includes('surveys') : !!activeDept?.surveys_enabled
  if (!enabled || !permissions.includes(PERM.surveysView)) {
    return <NoAccessPage reason="right" />
  }
  const base = active ? `/api/orgs/${active.id}/surveys/` : `/api/depts/${activeDept!.id}/surveys/`
  return (
    <Surveys
      key={base}
      base={base}
      orgId={active?.id ?? activeDept!.id}
      canEdit={permissions.includes(PERM.surveysEdit)}
    />
  )
}

function Surveys({ base, orgId, canEdit }: { base: string; orgId: number; canEdit: boolean }) {
  const detail = useDetailParam('umfrage')
  const list = useLoad(() => surveyApi.list(base), [base])
  const [creating, setCreating] = useState(false)
  const sorting = useRowSort(list.data ?? [], {
    title: (s) => s.title,
    end: (s) => s.closes_at,
    answers: (s) => s.participants,
    status: (s) => s.status,
  })
  if (detail.value) {
    return (
      <SurveyDetail
        base={base}
        orgId={orgId}
        id={Number(detail.value)}
        onClose={async () => {
          detail.close()
          await list.reload()
        }}
        onOpen={async (id) => {
          await list.reload()
          detail.open(String(id))
        }}
      />
    )
  }
  const rows = sorting.rows
  return (
    <div className="surveys stack">
      <PageHeader
        primary={
          canEdit && !creating
            ? { label: t('Neue Umfrage'), onClick: () => setCreating(true) }
            : null
        }
      />
      <p className="muted">
        {t(
          'Umfragen sind Meinungsbilder, keine Beschlüsse: Termin finden, Essenswahl, wer fährt mit. Förmliche Abstimmungen gehören in die Versammlungen.',
        )}
      </p>
      <div className="aid-row">
        <Why k="survey_not_resolution" />
      </div>
      {creating && (
        <SurveyEditor
          base={base}
          survey={null}
          onDone={async (saved) => {
            setCreating(false)
            if (saved) {
              await list.reload()
              detail.open(String(saved.id))
            }
          }}
        />
      )}
      {list.error && <p role="alert">{list.error}</p>}
      {!list.data && !list.error && <Loading />}
      {list.data && rows.length === 0
        ? !creating && (
            <EmptyList
              title={t('Noch keine Umfrage.')}
              canAdd={canEdit}
              action={{ label: t('Neue Umfrage'), onClick: () => setCreating(true) }}
            />
          )
        : rows.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  {sorting.head('title', t('Umfrage'))}
                  {sorting.head('end', t('Ende'))}
                  {sorting.head('answers', t('Antworten'))}
                  {sorting.head('status', t('Stand'))}
                </tr>
              </thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => detail.open(String(s.id))}
                      >
                        {s.title}
                      </button>
                      {s.event_title && <span className="muted small"> · {s.event_title}</span>}
                    </td>
                    <td>{endText(s.closes_at)}</td>
                    <td>
                      {s.invited != null
                        ? t('{n} von {m}', { n: s.participants, m: s.invited })
                        : s.participants}
                    </td>
                    <td>
                      <span className="badge">{statusLabel(s.status)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
    </div>
  )
}
