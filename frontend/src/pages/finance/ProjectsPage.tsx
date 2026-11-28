// Finanzen › Veranstaltungen: Einnahmen und Ausgaben einer Veranstaltung bündeln,
// Termine verknüpfen und das Ergebnis auswerten; Reihen über mehrere Jahre vergleichen.
import { useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { euro, financeApi } from '../../api/finance.ts'
import type { ProjectSeries } from '../../api/finance.ts'
import { PERM } from '../../api/orgs.ts'
import { promptDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { Why } from '../../learning/Aids.tsx'
import { t } from '../../i18n/index.ts'
import { ProjectDetail } from './ProjectDetail.tsx'
import { STATUS, period } from './projectsHelpers.ts'
import { ProjectForm } from './ProjectForm.tsx'
import { ProjectResult } from './ProjectResult.tsx'

/** Routen unter /finanzen/veranstaltungen */
export function ProjectsArea() {
  return (
    <Routes>
      <Route index element={<ProjectList />} />
      <Route path="reihen" element={<SeriesPage />} />
      <Route path=":id" element={<ProjectDetail />} />
      <Route path="*" element={<Navigate to="/finanzen/veranstaltungen" replace />} />
    </Routes>
  )
}

function ProjectList() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.financeEdit)
  const navigate = useNavigate()
  const [status, setStatus] = useState('')
  const [reihe, setReihe] = useState('')
  const [creating, setCreating] = useState(false)
  const list = useLoad(
    () => financeApi.projects(org.id, { status, reihe }),
    [org.id, status, reihe],
  )
  const series = useLoad(() => financeApi.series(org.id), [org.id])

  if (list.error) return <Alert kind="error">{list.error}</Alert>
  return (
    <div className="stack">
      <Why k="project_series" />
      {canEdit && !creating && (
        <div className="button-row">
          <button type="button" className="button button-primary" onClick={() => setCreating(true)}>
            {t('Neue Veranstaltung')}
          </button>
        </div>
      )}
      {creating && (
        <ProjectForm
          project={null}
          series={series.data ?? []}
          onSeriesAdded={() => void series.reload()}
          onSaved={(p) => navigate(`/finanzen/veranstaltungen/${p.id}`)}
          onClose={() => setCreating(false)}
        />
      )}
      <div className="card card-wide filters">
        <select aria-label={t('Status')} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t('alle Status')}</option>
          {STATUS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        {(series.data?.length ?? 0) > 0 && (
          <select aria-label={t('Reihe')} value={reihe} onChange={(e) => setReihe(e.target.value)}>
            <option value="">{t('alle Reihen')}</option>
            {series.data!.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        )}
      </div>
      <div className="card card-wide">
        {!list.data ? (
          <Loading />
        ) : list.data.length === 0 ? (
          <div className="empty-state">
            <p>{t('Noch keine Veranstaltung.')}</p>
            <p className="muted small">
              {t(
                'Lege zum Beispiel das Sommerfest als Veranstaltung an und ordne ihm im Kassenbuch Einnahmen und Ausgaben zu. Die Buchungen bleiben ganz normal im Kassenbuch.',
              )}
            </p>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Veranstaltung')}</th>
                  <th>{t('Zeitraum')}</th>
                  <th className="num">{t('Einnahmen')}</th>
                  <th className="num">{t('Ausgaben')}</th>
                  <th className="num">{t('Ergebnis')}</th>
                </tr>
              </thead>
              <tbody>
                {list.data.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/finanzen/veranstaltungen/${p.id}`}>{p.name}</Link>
                      <div className="muted small">
                        {[p.status_label, p.series_name, p.department_name]
                          .filter(Boolean)
                          .join(' · ')}
                      </div>
                    </td>
                    <td>{period(p.starts_on, p.ends_on)}</td>
                    <td className="num">{euro(p.income)}</td>
                    <td className="num">{euro(p.expense)}</td>
                    <td className="num">
                      <strong>
                        <ProjectResult value={p.result} />
                      </strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

/** Reihen: anlegen, umbenennen, löschen und die Jahre vergleichen. */
function SeriesPage() {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.financeEdit)
  const list = useLoad(() => financeApi.series(org.id), [org.id])
  const [selected, setSelected] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const current = selected ?? list.data?.[0]?.id ?? null
  const comparison = useLoad(
    () => (current ? financeApi.seriesComparison(org.id, current) : Promise.resolve(null)),
    [org.id, current],
  )

  async function create() {
    const name = await promptDialog({
      title: t('Neue Reihe'),
      message: t('z. B. „Sommerfest“ – danach die Veranstaltungen der einzelnen Jahre zuordnen.'),
      label: t('Name'),
      confirmLabel: t('Anlegen'),
      danger: false,
    })
    if (!name?.trim()) return
    try {
      const s = await financeApi.createSeries(org.id, name.trim())
      await list.reload()
      setSelected(s.id)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function rename(s: ProjectSeries) {
    const name = await promptDialog({
      title: t('Reihe umbenennen'),
      label: t('Name'),
      defaultValue: s.name,
      confirmLabel: t('Speichern'),
      danger: false,
    })
    if (!name?.trim() || name.trim() === s.name) return
    try {
      await financeApi.updateSeries(org.id, s.id, name.trim())
      await list.reload()
      void comparison.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  // Ohne Rückfrage: rückgängig zu machen, Veranstaltungen und Buchungen bleiben (VW-23)
  async function remove(s: ProjectSeries) {
    try {
      await financeApi.deleteSeries(org.id, s.id)
      setSelected(null)
      await list.reload()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (list.error) return <Alert kind="error">{list.error}</Alert>
  if (!list.data) return <Loading />
  const sel = list.data.find((s) => s.id === current) ?? null
  const c = comparison.data
  return (
    <div className="stack">
      {error && <Alert kind="error">{error}</Alert>}
      <div className="card card-wide filters">
        {list.data.length > 0 && (
          <select
            aria-label={t('Reihe')}
            value={current ?? ''}
            onChange={(e) => setSelected(Number(e.target.value))}
          >
            {list.data.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.project_count})
              </option>
            ))}
          </select>
        )}
        {sel && (
          <>
            <a
              className="button button-ghost"
              href={financeApi.seriesReportUrl(org.id, sel.id, 'pdf')}
              target="_blank"
              rel="noreferrer"
            >
              PDF
            </a>
            <a
              className="button button-ghost"
              href={financeApi.seriesReportUrl(org.id, sel.id, 'xlsx')}
            >
              {t('Excel')}
            </a>
          </>
        )}
        {canEdit && sel && (
          <>
            <button type="button" className="button button-ghost" onClick={() => void rename(sel)}>
              {t('Umbenennen')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => void remove(sel)}>
              {t('Löschen')}
            </button>
          </>
        )}
        {canEdit && (
          <button
            type="button"
            className="button button-primary push-right"
            onClick={() => void create()}
          >
            {t('Neue Reihe')}
          </button>
        )}
      </div>
      {list.data.length === 0 ? (
        <div className="card empty-state">
          <p>{t('Noch keine Reihe.')}</p>
          <p className="muted small">
            {t(
              'Mit einer Reihe vergleichst du wiederkehrende Veranstaltungen, z. B. das Sommerfest über mehrere Jahre.',
            )}
          </p>
        </div>
      ) : !c ? (
        <Loading />
      ) : c.projects.length === 0 ? (
        <div className="card empty-state">
          <p>{t('Zu dieser Reihe gehört noch keine Veranstaltung.')}</p>
          <p className="muted small">{t('Wähle die Reihe beim Bearbeiten einer Veranstaltung.')}</p>
        </div>
      ) : (
        <div className="card card-wide">
          <h2>
            {t('Vergleich')} {c.name}
          </h2>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Kategorie (Saldo)')}</th>
                  {c.projects.map((p) => (
                    <th key={p.id} className="num">
                      <Link to={`/finanzen/veranstaltungen/${p.id}`}>{p.name}</Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {c.categories.map((cat) => (
                  <tr key={cat.id ?? 0}>
                    <td>{cat.name}</td>
                    {cat.values.map((v, i) => (
                      <td key={c.projects[i].id} className="num">
                        <ProjectResult value={v.result} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th>{t('Einnahmen')}</th>
                  {c.projects.map((p) => (
                    <th key={p.id} className="num">
                      {euro(p.income)}
                    </th>
                  ))}
                </tr>
                <tr>
                  <th>{t('Ausgaben')}</th>
                  {c.projects.map((p) => (
                    <th key={p.id} className="num">
                      {euro(p.expense)}
                    </th>
                  ))}
                </tr>
                <tr>
                  <th>{t('Ergebnis')}</th>
                  {c.projects.map((p) => (
                    <th key={p.id} className="num">
                      <ProjectResult value={p.result} />
                    </th>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
