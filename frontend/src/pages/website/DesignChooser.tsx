// Webseite › Gestaltung › Design: eines der Standarddesigns wählen, Farben den Rollen zuordnen
// und ein Design in der Vorschau ansehen, ohne es zu übernehmen (konzepte/webseiten-designs.md).
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { websiteApi } from '../../api/website.ts'
import type { ColorRoles, RoleColors, WebsiteData } from '../../api/website.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, SelectField } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { contrastRatio } from '../../theme/contrast.ts'
import { DesignTransfer } from './DesignTransfer.tsx'

const NEUTRAL: Record<string, string> = { light: t('Weiß'), dark: t('Dunkel (fast Schwarz)') }

export function DesignChooser({
  data,
  design,
  colorRoles,
  onDesign,
  onColorRoles,
  onPackagesChanged,
}: {
  data: WebsiteData
  design: string
  colorRoles: ColorRoles
  onDesign: (key: string) => void
  onColorRoles: (next: ColorRoles) => void
  /** Designpakete eingespielt, freigegeben oder gelöscht: Stand neu laden */
  onPackagesChanged?: () => void
}) {
  const org = useActiveOrg()
  const [error, setError] = useState<string | null>(null)
  const [opened, setOpened] = useState<string | null>(null)
  const designs = data.designs ?? []
  const colors = data.website?.design_colors ?? {}
  const palette = data.palette ?? []
  const gradients = data.gradients ?? []
  const current = designs.find((d) => d.key === design) ?? designs[0]

  async function preview(key: string) {
    setError(null)
    setOpened(null)
    try {
      const result = await websiteApi.openPreview(org.id)
      if (!result.url) {
        setError(t('Für die Vorschau fehlt noch eine Domain.'))
        return
      }
      const url = `${result.url}&design=${encodeURIComponent(key)}`
      window.open(url, '_blank', 'noopener')
      setOpened(url)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const paletteName = (i: number) => {
    const p = palette[i]
    const role =
      i === 0 ? t('Hauptfarbe') : i === 1 ? t('Zweitfarbe') : t('{x}. Farbe', { x: i + 1 })
    return p
      ? t('{role}{x} {color}', { role, x: p.name ? ` (${p.name})` : '', color: p.color })
      : role
  }

  function setRole(role: string, value: string) {
    const mine = { ...(colorRoles[design] ?? {}) }
    if (value === '') delete mine[role]
    else mine[role] = /^\d$/.test(value) ? Number(value) : value
    const next = { ...colorRoles, [design]: mine }
    if (Object.keys(mine).length === 0) delete next[design]
    onColorRoles(next)
  }

  return (
    <>
      <p className="muted small">
        {t(
          'Das Design bestimmt, wie die Webseite aussieht: Kopf, Menü, Fuß und die Anordnung der Startseite. Inhalte und Bausteine (unter',
        )}{' '}
        <Link to="/webseite/aufbau">{t('Webseite › Menü und Bausteine')}</Link>
        {t(') bleiben bei jedem Design gleich. Die Farben legst du hier fest:')}{' '}
        <Link to="/einstellungen/erscheinungsbild">{t('Einstellungen › Erscheinungsbild')}</Link>.
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <div className="design-grid" role="radiogroup" aria-label={t('Design der Webseite')}>
        {designs.map((d) => (
          <div key={d.key} className={`design-card${d.key === design ? ' selected' : ''}`}>
            <label>
              <input
                type="radio"
                name="design"
                value={d.key}
                checked={d.key === design}
                onChange={() => onDesign(d.key)}
              />
              <Sketch design={d.sketch ?? d.key} colors={colors[d.key]} />
              <strong>{d.label}</strong>
              {d.package && <small className="muted">{t('Eigenes Design')}</small>}
              <small className="muted">{d.hint}</small>
            </label>
            <button
              type="button"
              className="button button-ghost"
              onClick={() => void preview(d.key)}
            >
              {t('Vorschau ansehen')}
            </button>
          </div>
        ))}
      </div>
      {opened && (
        <p className="muted small">
          {t('Kein neues Fenster?')}{' '}
          <a href={opened} target="_blank" rel="noopener noreferrer">
            {t('Vorschau hier öffnen')}
          </a>
          {t('. Die Vorschau übernimmt nichts; gewählt ist das markierte Design.')}
        </p>
      )}
      {current && (
        <details className="design-roles">
          <summary>{t('Farben für „{label}“ zuordnen', { label: current.label })}</summary>
          <p className="muted small">
            {t(
              'Welche Farbe das Design wo einsetzt. „Vorgabe“ nimmt die passende Farbe des Designs; fehlt eine weitere Farbe, nimmt es die Haupt- oder Zweitfarbe.',
            )}
          </p>
          <div className="grid-2">
            {current.roles
              .filter((r) => !r.common)
              .map((r) => (
                <RoleSelect
                  key={r.key}
                  role={r}
                  chosen={colorRoles[design]?.[r.key]}
                  swatch={colors[design]?.[r.key]}
                  palette={palette.map((_, i) => paletteName(i))}
                  gradients={r.gradient ? gradients : []}
                  onChange={(v) => setRole(r.key, v)}
                />
              ))}
          </div>
          <h4>{t('Text, Flächen und Hintergrund')}</h4>
          <p className="muted small">
            {t(
              'Gilt für die ganze Webseite. „Vorgabe“ nimmt die Farbe, die unter Einstellungen › Erscheinungsbild für diese Rolle angekreuzt ist, sonst die des Designs.',
            )}
          </p>
          <div className="grid-2">
            {current.roles
              .filter((r) => r.common)
              .map((r) => (
                <RoleSelect
                  key={r.key}
                  role={r}
                  chosen={colorRoles[design]?.[r.key]}
                  swatch={colors[design]?.[r.key]}
                  palette={palette.map((_, i) => paletteName(i))}
                  gradients={[]}
                  common
                  onChange={(v) => setRole(r.key, v)}
                />
              ))}
          </div>
          <ContrastWarnings colors={colors[design]} />
        </details>
      )}
      {data.website && (
        <DesignTransfer data={data} design={design} onChanged={() => onPackagesChanged?.()} />
      )}
    </>
  )
}

function RoleSelect({
  role,
  chosen,
  swatch,
  palette,
  gradients,
  common = false,
  onChange,
}: {
  role: { key: string; label: string }
  /** Text, Flächen, Hintergrund: Vorgabe sind die Farbrollen der Einheit */
  common?: boolean
  chosen: number | string | undefined
  swatch?: RoleColors[string]
  palette: string[]
  gradients: { name: string; colors: [string, string] }[]
  onChange: (value: string) => void
}) {
  const now = swatch?.gradient
    ? t('Jetzt: Verlauf {from} → {to}', { from: swatch.gradient.from, to: swatch.gradient.to })
    : swatch
      ? t('Jetzt: {swatch}', { swatch: swatch.color })
      : undefined
  return (
    <SelectField
      label={role.label}
      value={chosen === undefined ? '' : String(chosen)}
      hint={now}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">
        {common ? t('Vorgabe (Vereinsfarben oder Design)') : t('Vorgabe des Designs')}
      </option>
      {palette.map((label, i) => (
        <option key={i} value={String(i)}>
          {label}
        </option>
      ))}
      {Object.entries(NEUTRAL).map(([k, label]) => (
        <option key={k} value={k}>
          {label}
        </option>
      ))}
      {gradients.map((g, i) => (
        <option key={`g${i}`} value={`g${i}`}>
          {t('Verlauf: {name}', {
            name: g.name || t('{from} → {to}', { from: g.colors[0], to: g.colors[1] }),
          })}
        </option>
      ))}
    </SelectField>
  )
}

// Vorgaben der Webseite, wenn Text, Flächen und Hintergrund nicht gewählt sind (seite.css)
const SITE_TEXT = '#1d2421'
const SITE_MUTED = '#5a625e'
const SITE_SURFACE = '#ffffff'
const SITE_BACKGROUND = '#fbfaf7'

/** Warnt, wenn Fließ- oder Sekundärtext auf Flächen oder Hintergrund schlecht lesbar wird. */
export function ContrastWarnings({ colors }: { colors?: RoleColors }) {
  const pick = (role: string, fallback: string) => colors?.[role]?.color ?? fallback
  const text = pick('text', SITE_TEXT)
  const muted = pick('muted', SITE_MUTED)
  const surface = pick('surface', SITE_SURFACE)
  const background = pick('background', SITE_BACKGROUND)
  const checks = [
    { label: t('Fließtext auf Flächen'), a: text, b: surface },
    { label: t('Fließtext auf dem Hintergrund'), a: text, b: background },
    { label: t('Sekundärtext auf Flächen'), a: muted, b: surface },
    { label: t('Sekundärtext auf dem Hintergrund'), a: muted, b: background },
  ]
  const bad = checks
    .map((c) => ({ ...c, ratio: contrastRatio(c.a, c.b) }))
    .filter((c) => c.ratio < 4.5)
  if (bad.length === 0) return null
  return (
    <Alert kind="info">
      {t('Schlecht lesbar (mind. 4.5 : 1):')}{' '}
      {bad.map((c) => t('{label} {x} : 1', { label: c.label, x: c.ratio.toFixed(1) })).join(', ')}
    </Alert>
  )
}

/** Kleine Skizze des Aufbaus in den Farben der Einheit (keine echte Seite). */
export function Sketch({ design, colors }: { design: string; colors?: RoleColors }) {
  const c = (role: string, fallback: string) => colors?.[role]?.color ?? fallback
  const head = c('header', '#1f4e2c')
  const nav = c('nav', '#c9a227')
  const line = c('line', '#c9a227')
  const foot = c('footer', '#1d2421')
  const date = c('date', head)
  const grey = '#d9dcd8'
  const box = (x: number, y: number, w: number, h: number, fill = '#ffffff') => (
    <rect x={x} y={y} width={w} height={h} rx={2} fill={fill} stroke={grey} strokeWidth={0.6} />
  )
  const hero = (x: number, y: number, w: number, h: number) => (
    <rect x={x} y={y} width={w} height={h} rx={2} fill="#9fb3a4" />
  )
  const shield = (x: number, y: number, s: number) => (
    <path
      d={`M${x} ${y}h${s}v${s * 0.55}c0 ${s * 0.3}-${s * 0.25} ${s * 0.45}-${s / 2} ${s * 0.55}c-${s * 0.25}-${s * 0.1}-${s / 2}-${s * 0.25}-${s / 2}-${s * 0.55}z`}
      fill="#ffffff"
      stroke={line}
      strokeWidth={0.8}
    />
  )
  let body
  switch (design) {
    case 'festive':
      body = (
        <>
          <rect width="160" height="34" fill={head} />
          {shield(74, 4, 12)}
          <rect x="52" y="21" width="56" height="3" rx="1" fill="#ffffff" />
          <rect y="28" width="160" height="0.8" fill={line} />
          <rect y="33" width="160" height="0.8" fill={line} />
          {hero(0, 35, 160, 22)}
          <rect x="62" y="61" width="36" height="3" rx="1" fill={head} />
          <rect x="72" y="66" width="16" height="1" fill={line} />
          {box(28, 70, 50, 18)}
          <rect x="31" y="73" width="8" height="10" fill={date} />
          {box(82, 70, 50, 18)}
          <rect y="92" width="160" height="8" fill={foot} />
        </>
      )
      break
    case 'sidebar':
      body = (
        <>
          <rect width="38" height="100" fill={head} />
          {shield(13, 6, 12)}
          {[28, 35, 42, 49, 56].map((y, i) => (
            <rect
              key={y}
              x="6"
              y={y}
              width="26"
              height="4"
              rx="1"
              fill={i === 0 ? nav : '#ffffff'}
              opacity={i === 0 ? 1 : 0.6}
            />
          ))}
          {hero(44, 6, 110, 26)}
          {box(44, 38, 54, 20)}
          <rect x="47" y="41" width="8" height="10" fill={date} />
          {box(102, 38, 52, 20)}
          {box(44, 64, 110, 12)}
          <rect x="38" y="92" width="122" height="8" fill={foot} stroke={grey} strokeWidth={0.6} />
        </>
      )
      break
    case 'stage':
      body = (
        <>
          <rect width="160" height="10" fill={head} stroke={grey} strokeWidth={0.6} />
          {shield(4, 2, 6)}
          <rect x="96" y="4" width="56" height="2" rx="1" fill={nav} />
          {hero(0, 10, 160, 34)}
          <rect x="8" y="30" width="70" height="4" rx="1" fill="#ffffff" />
          <rect x="8" y="37" width="22" height="4" rx="2" fill={line} />
          <rect y="44" width="160" height="14" fill="#ffffff" />
          <rect x="30" y="49" width="100" height="2" fill={grey} />
          <rect y="58" width="160" height="17" fill={c('band', head)} />
          <rect x="30" y="62" width="9" height="9" fill={date} />
          <rect x="42" y="64" width="88" height="4" rx="1" fill="#ffffff" opacity={0.4} />
          <rect y="75" width="160" height="17" fill={c('band2', head)} />
          <rect y="92" width="160" height="8" fill={foot} />
        </>
      )
      break
    case 'newspaper':
      body = (
        <>
          <rect width="160" height="6" fill={head} />
          <rect y="6" width="160" height="18" fill="#ffffff" />
          {shield(8, 8, 12)}
          <rect x="24" y="11" width="60" height="4" rx="1" fill={head} />
          <rect y="24" width="160" height="7" fill={nav} />
          <rect x="8" y="25.5" width="14" height="5.5" fill="#fbfaf7" />
          {hero(8, 35, 90, 26)}
          <rect x="8" y="64" width="90" height="1" fill={line} />
          {box(8, 68, 90, 9)}
          {box(8, 80, 90, 9)}
          <rect x="104" y="35" width="48" height="2" fill={line} />
          {box(104, 37, 48, 26)}
          <rect x="107" y="41" width="7" height="7" fill={date} />
          {box(104, 66, 48, 22)}
          <rect y="92" width="160" height="8" fill={foot} />
        </>
      )
      break
    case 'classic-1':
      // Klassisch bis 2026-11 (z. B. als Designpaket gesichert): Menü rechts im Kopf
      body = (
        <>
          <rect width="160" height="16" fill={head} />
          {shield(6, 2, 10)}
          <rect x="20" y="6" width="40" height="3" rx="1" fill="#ffffff" />
          <rect x="92" y="6" width="60" height="2.5" rx="1" fill="#ffffff" opacity={0.7} />
          <rect x="92" y="10" width="10" height="1.2" fill={nav} />
          {hero(8, 21, 144, 26)}
          {box(8, 52, 70, 20)}
          <rect x="11" y="55" width="8" height="10" fill={date} />
          {box(82, 52, 70, 20)}
          {box(8, 76, 144, 10)}
          <rect y="92" width="160" height="8" fill={foot} />
        </>
      )
      break
    default:
      // Klassisch: heller Kopf mit farbiger Linie oben, Menü als Knöpfe
      body = (
        <>
          <rect width="160" height="2" fill={head} />
          <rect y="2" width="160" height="18" fill="#ffffff" stroke={grey} strokeWidth={0.6} />
          {shield(6, 4, 8)}
          <rect x="18" y="6" width="40" height="3" rx="1" fill={head} />
          <rect x="6" y="13" width="14" height="4" rx="2" fill={head} />
          {[24, 40, 56, 72].map((x) => (
            <rect
              key={x}
              x={x}
              y="14.3"
              width="11"
              height="1.6"
              rx="0.5"
              fill={head}
              opacity={0.7}
            />
          ))}
          {hero(8, 24, 144, 24)}
          {box(8, 52, 70, 20)}
          <rect x="11" y="55" width="8" height="10" fill={date} />
          {box(82, 52, 70, 20)}
          {box(8, 76, 144, 10)}
          <rect y="92" width="160" height="8" fill={foot} />
        </>
      )
  }
  return (
    <svg viewBox="0 0 160 100" className="design-sketch" aria-hidden="true">
      <rect width="160" height="100" fill="#fbfaf7" />
      {body}
    </svg>
  )
}
