import { EquipmentPage } from '../music/EquipmentPage.tsx'
import { Link, Route, Routes, useSearchParams } from 'react-router-dom'
import { materialApi } from '../../api/materials.ts'
import type { StockKind } from '../../api/materials.ts'
import { useLoad, whenLabel } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading } from '../../components/ui.tsx'
import './materials.css'
import { PageNav } from '../../components/ListControls.tsx'
import { NoAccessPage } from '../NoticePages.tsx'
import { ItemForm } from './ItemForm.tsx'
import { MaterialDetail } from './MaterialDetail.tsx'
import {
  conditionLabel,
  location,
  facilityTypeLabel,
  stockRoot,
  type Stock,
} from './materialsHelpers.ts'

export function MaterialsPage({ kind = 'material' }: { kind?: StockKind }) {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const has = (module: 'material' | 'infrastructure') =>
    active
      ? active.modules.includes(module)
      : module === 'material'
        ? !!activeDept?.material_enabled
        : !!activeDept?.infrastructure_enabled
  const area = kind === 'facility' ? 'infrastructure' : 'material'
  if (!has(area) || !permissions.includes(`${area}.view`)) return <NoAccessPage reason="right" />
  const prefix = active ? `/api/orgs/${active.id}/` : `/api/depts/${activeDept!.id}/`
  const stock: Stock = {
    kind,
    root: stockRoot(kind),
    base: `${prefix}${kind === 'facility' ? 'facilities' : 'materials'}/`,
    prefix,
    infrastructure: has('infrastructure'),
    materialView: has('material') && permissions.includes('material.view'),
  }
  const base = stock.base
  const editable = permissions.includes(`${area}.edit`)
  return (
    <div className="materials" key={base}>
      <Routes>
        <Route
          index
          element={
            <MaterialList
              stock={stock}
              base={base}
              editable={editable}
              canExport={permissions.some((p) => ['export.lists', 'export.full'].includes(p))}
            />
          }
        />
        <Route
          path="neu"
          element={
            editable ? (
              <ItemForm stock={stock} base={base} />
            ) : (
              <NoAccessPage reason="right" embedded />
            )
          }
        />
        {kind === 'material' && active && (
          // Instrumente und Uniformen: Musikausstattung als Ansicht des Materials (N-05)
          <Route path="musik" element={<EquipmentPage />} />
        )}
        <Route
          path=":id"
          element={<MaterialDetail stock={stock} base={base} editable={editable} />}
        />
      </Routes>
    </div>
  )
}

function MaterialList({
  stock,
  base,
  editable,
  canExport,
}: {
  stock: Stock
  base: string
  editable: boolean
  canExport: boolean
}) {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const { data, error, loading } = useLoad(() => materialApi.list(base, query), [base, query])
  const filter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    if (key !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }
  return (
    <>
      <PageHeader
        primary={
          editable
            ? {
                label:
                  stock.kind === 'facility' ? t('Raum oder Anlage anlegen') : t('Material anlegen'),
                to: 'neu',
              }
            : null
        }
      />
      <div className="card material-filters">
        <label>
          {t('Suchen')}
          <input
            type="search"
            value={params.get('q') ?? ''}
            onChange={(e) => filter('q', e.target.value)}
          />
        </label>
        <label>
          {t('Zustand')}
          <select
            value={params.get('condition') ?? ''}
            onChange={(e) => filter('condition', e.target.value)}
          >
            <option value="">{t('Alle')}</option>
            {['ready', 'limited', 'defective', 'retired'].map((v) => (
              <option key={v} value={v}>
                {conditionLabel(v, stock.kind)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.get('archived') === '1'}
            onChange={(e) => filter('archived', e.target.checked ? '1' : '')}
          />{' '}
          {stock.kind === 'facility' ? t('Aufgegebene anzeigen') : t('Ausgesonderte anzeigen')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.get('trash') === '1'}
            onChange={(e) => filter('trash', e.target.checked ? '1' : '')}
          />{' '}
          {t('Papierkorb')}
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.get('review') === '1'}
            onChange={(e) => filter('review', e.target.checked ? '1' : '')}
          />{' '}
          {t('Nur Prüfhinweise')}
        </label>
        {canExport && (
          <a className="button button-ghost" href={`${base}?${query}&export=1`}>
            {t('Als CSV exportieren')}
          </a>
        )}
        {!!query && (
          <button className="button button-ghost" type="button" onClick={() => setParams({})}>
            {t('Filter zurücksetzen')}
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {loading && <Loading />}
      {!loading && data?.count === 0 && (
        <p>
          {stock.kind === 'facility'
            ? t('Keine Räume und Anlagen gefunden.')
            : t('Kein Material gefunden.')}
        </p>
      )}
      <div className="material-grid">
        {data?.items.map((item) => (
          <article className="card" key={item.id}>
            {item.photo_url && !item.deleted_at && (
              <img
                className="material-thumbnail"
                src={item.photo_url}
                alt={item.title}
                loading="lazy"
              />
            )}
            <p className="muted">{item.inventory_number}</p>
            <h2>
              <Link to={`${item.id}${item.deleted_at ? '?trash=1' : ''}`}>{item.title}</Link>
            </h2>
            <p>{item.description}</p>
            {item.facility_type && <p>{facilityTypeLabel(item.facility_type)}</p>}
            <p>{location(item)}</p>
            <p>{conditionLabel(item.condition, stock.kind)}</p>
            {item.next_use && (
              <p>
                {item.next_use.title} · {whenLabel(item.next_use.starts_at, item.next_use.all_day)}
              </p>
            )}
          </article>
        ))}
      </div>
      {data && data.count > 50 && (
        <PageNav
          prevDisabled={data.page <= 1}
          nextDisabled={data.page * 50 >= data.count}
          onPrev={() => filter('page', String(data.page - 1))}
          onNext={() => filter('page', String(data.page + 1))}
        >
          {data.page} / {Math.ceil(data.count / 50)}
        </PageNav>
      )}
    </>
  )
}
