import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { ChangeEvent } from 'react'
import { api } from '../../api/client.ts'
import { orgApi, PERM } from '../../api/orgs.ts'
import { gradientCss } from '../../api/orgs.ts'
import type { ExtraColor, GradientSetting, ThemeSettings } from '../../api/orgs.ts'
import {
  Alert,
  Checkbox,
  Field,
  SaveStatus,
  SelectField,
  LoadError,
  Loading,
} from '../../components/ui.tsx'
import { errorMessage, useAutoSave, useForm, useLoad } from '../../components/forms.ts'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { contrastRatio, readableOn, readableOnPair } from '../../theme/contrast.ts'
import { buttonColors, linkColor, PAGE_BG, TEXT_COLOR } from '../../theme/theme.ts'
import { useImageCrop } from '../../components/ImageCrop.tsx'
import { RightsHint } from '../../components/RightsHint.tsx'
import { t } from '../../i18n/index.ts'
import { loadPlatform, usePlatform } from '../../theme/platform.ts'

export function AppearancePage() {
  const org = useActiveOrg()
  const { data, error, setData, reload } = useLoad(() => orgApi.theme(org.id), [org.id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading />
  return (
    <ThemeForm
      key={org.id}
      orgId={org.id}
      isPlatform={org.type === 'platform'}
      theme={data}
      onSaved={setData}
      reload={reload}
    />
  )
}

function ThemeForm({
  orgId,
  isPlatform,
  theme,
  onSaved,
  reload,
}: {
  orgId: number
  isPlatform: boolean
  theme: ThemeSettings
  onSaved: (tm: ThemeSettings) => void
  reload: () => Promise<void>
}) {
  const { can, refresh } = useOrg()
  const editable = can(PERM.themeEdit)
  const form = useForm({
    primary_color: theme.primary_color,
    accent_color: theme.accent_color,
    primary_color_name: theme.primary_color_name ?? '',
    accent_color_name: theme.accent_color_name ?? '',
    extra_colors: theme.extra_colors ?? [],
    primary_color_use: theme.primary_color_use ?? '',
    accent_color_use: theme.accent_color_use ?? '',
    gradients: theme.gradients ?? [],
  })
  const eff = theme.effective
  const primary = form.values.primary_color || eff.primary
  const accent = form.values.accent_color || eff.accent
  const buttonPreview = buttonColors(primary, readableOn(primary))

  const auto = useAutoSave(form, (changes) => orgApi.updateTheme(orgId, changes), {
    enabled: editable,
    onSaved: (saved) => {
      onSaved(saved as ThemeSettings)
      void refresh()
      // Farben der Instanz gelten auch für Anmeldeseite und Seiten ohne Einheit
      if (isPlatform) void loadPlatform(true)
    },
  })

  return (
    <div className="stack">
      <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
        <h2>{t('Farben')}</h2>
        {editable && <SaveStatus auto={auto} />}
        {isPlatform && (
          <p className="small">
            {t(
              'Farben und Logo der Instanz gelten für die Anmeldeseite, die öffentlichen Seiten und alle Einheiten ohne eigene Farben oder eigenes Logo. Den Namen der Instanz legst du unter Einstellungen › Organisation fest.',
            )}
          </p>
        )}
        <p className="muted small">
          {t(
            'Ohne eigene Farbe übernimmt die Organisation das Erscheinungsbild der übergeordneten Ebene',
          )}
          {eff.inherited_from.colors && !theme.primary_color
            ? t(' (derzeit von „{x0}“)', { x0: eff.inherited_from.colors })
            : ''}
          .
        </p>
        <fieldset disabled={!editable}>
          <ColorInput
            label={t('Hauptfarbe (Primärfarbe)')}
            hint={t('Kopfzeile, Schaltflächen, Links')}
            value={form.values.primary_color}
            inherited={eff.primary}
            error={form.errors.primary_color}
            onChange={(v) => form.set('primary_color', v)}
          />
          <div className="grid-2">
            <ColorName
              label={t('Name der Hauptfarbe')}
              value={form.values.primary_color_name}
              onChange={(v) => form.set('primary_color_name', v)}
            />
            <ColorUse
              label={t('Verwendung der Hauptfarbe')}
              value={form.values.primary_color_use}
              error={form.errors.primary_color_use}
              onChange={(v) => form.set('primary_color_use', v)}
            />
          </div>
          <ColorInput
            label={t('Zweitfarbe (Akzentfarbe)')}
            hint={t('Hervorhebungen')}
            value={form.values.accent_color}
            inherited={eff.accent}
            error={form.errors.accent_color}
            onChange={(v) => form.set('accent_color', v)}
          />
          <div className="grid-2">
            <ColorName
              label={t('Name der Zweitfarbe')}
              value={form.values.accent_color_name}
              onChange={(v) => form.set('accent_color_name', v)}
            />
            <ColorUse
              label={t('Verwendung der Zweitfarbe')}
              value={form.values.accent_color_use}
              error={form.errors.accent_color_use}
              onChange={(v) => form.set('accent_color_use', v)}
            />
          </div>
          <ExtraColors
            colors={form.values.extra_colors}
            error={form.errors.extra_colors}
            ownPrimary={Boolean(form.values.primary_color)}
            onChange={(v) => form.set('extra_colors', v)}
          />
          <Gradients
            gradients={form.values.gradients}
            palette={[
              { color: primary, name: form.values.primary_color_name },
              { color: accent, name: form.values.accent_color_name },
              ...form.values.extra_colors,
            ]}
            error={form.errors.gradients}
            ownPrimary={Boolean(form.values.primary_color)}
            onChange={(v) => form.set('gradients', v)}
          />
        </fieldset>

        <h3>{t('Vorschau')}</h3>
        <div className="theme-preview">
          <span
            className="preview-chip"
            style={{ background: buttonPreview.background, color: buttonPreview.foreground }}
          >
            {t('Schaltfläche')}
          </span>
          <span className="preview-chip" style={{ background: accent, color: readableOn(accent) }}>
            {t('Hinweis')}
          </span>
          {/* Dieselbe abgeleitete Linkfarbe wie in der App (UI-Audit NUI-04) */}
          <span style={{ color: linkColor(primary) }} className="preview-link">
            {t('Link auf weißem Grund')}
          </span>
          <span
            style={{ color: linkColor(primary), background: PAGE_BG }}
            className="preview-link preview-on-page"
          >
            {t('Link auf dem Seitenhintergrund')}
          </span>
        </div>
        <ContrastHints primary={primary} accent={accent} />
        <p className="muted small">
          {t('Das Design und seine Farbverwendung stellst du hier ein:')}{' '}
          <Link to="/webseite/gestaltung">{t('Webseite › Gestaltung')}</Link>.
        </p>
        <p className="muted small">
          {t('Alle Farben und Verläufe auf einen Blick, zum Weitergeben oder Drucken:')}{' '}
          <Link to="/einstellungen/erscheinungsbild/farbblatt">{t('Farbblatt ansehen')}</Link>.
        </p>
      </form>

      <div className="card card-wide">
        <h2>{t('Logo / Wappen')}</h2>
        {editable ? (
          <LogoUpload
            uploadUrl={orgApi.logoUrl(orgId)}
            logoUrl={theme.logo_url}
            onChange={async () => {
              await reload()
              await refresh()
              if (isPlatform) await loadPlatform(true)
            }}
          />
        ) : theme.logo_url ? (
          <img src={theme.logo_url} alt={t('Logo')} className="logo-preview" />
        ) : (
          <p className="muted">{t('Kein eigenes Logo.')}</p>
        )}
        {!theme.logo_url && eff.logo_url && (
          <p className="muted small">
            {t('Angezeigt wird das Logo von „{logo}“.', { logo: eff.inherited_from.logo })}
          </p>
        )}
        <h3>{t('Logo / Wappen für den Dunkelmodus')}</h3>
        <p className="muted small">
          {t(
            'Erscheint, wenn jemand die dunkle Darstellung nutzt (Anmeldung, Startseite, Termine, Mein Konto). Ohne eigenes Logo für den Dunkelmodus gilt das normale Logo.',
          )}
        </p>
        {editable ? (
          <LogoUpload
            dark
            uploadUrl={orgApi.logoDarkUrl(orgId)}
            logoUrl={theme.logo_dark_url ?? null}
            onChange={async () => {
              await reload()
              await refresh()
              if (isPlatform) await loadPlatform(true)
            }}
          />
        ) : theme.logo_dark_url ? (
          <img
            src={theme.logo_dark_url}
            alt={t('Logo für den Dunkelmodus')}
            className="logo-preview logo-preview-dark"
          />
        ) : (
          <p className="muted">{t('Kein eigenes Logo für den Dunkelmodus.')}</p>
        )}
      </div>
      {isPlatform && <PlatformIconCard editable={editable} />}
      {!isPlatform && (theme.addresses?.length ?? 0) > 0 && (
        <UnitIconCard
          orgId={orgId}
          addresses={theme.addresses ?? []}
          hasIcon={Boolean(theme.has_icon)}
          editable={editable}
          reload={reload}
        />
      )}
    </div>
  )
}

/** Symbol einer Einheit mit eigener Adresse (White Label W7). */
function UnitIconCard({
  orgId,
  addresses,
  hasIcon,
  editable,
  reload,
}: {
  orgId: number
  addresses: string[]
  hasIcon: boolean
  editable: boolean
  reload: () => Promise<void>
}) {
  const [version, setVersion] = useState(0)
  const shown = hasIcon ? `${orgApi.iconUrl(orgId)}?v=${version}` : null
  return (
    <div className="card card-wide">
      <h2>{t('Symbol')}</h2>
      <p className="small">
        {t(
          'Diese Einheit hat eine eigene Adresse ({x}). Dort erscheint das Symbol im Browser-Tab und auf dem Startbildschirm des Handys. Ohne eigenes Symbol nimmt HUBIplan das Logo bzw. Wappen, sonst das Symbol der Instanz.',
          { x: addresses.join(', ') },
        )}
      </p>
      {editable ? (
        <LogoUpload
          uploadUrl={orgApi.iconUrl(orgId)}
          logoUrl={shown}
          onChange={async () => {
            await reload()
            setVersion(Date.now())
          }}
        />
      ) : shown ? (
        <img src={shown} alt={t('Symbol')} className="logo-preview" />
      ) : (
        <p className="muted">{t('Kein eigenes Symbol.')}</p>
      )}
    </div>
  )
}

/** Symbol der Instanz für Browser-Tab und Handy (White Label W2). */
function PlatformIconCard({ editable }: { editable: boolean }) {
  const instance = usePlatform()
  // Nach dem Hochladen neu laden, am Zwischenspeicher des Browsers vorbei
  const [version, setVersion] = useState(0)
  const src = (name: string) => `/api/public/platform/icon-${name}.png?v=${version}`
  const shown = instance.icon ? src('512') : null
  return (
    <div className="card card-wide">
      <h2>{t('Symbol der Instanz')}</h2>
      <p className="small">
        {t(
          'Das Symbol erscheint im Browser-Tab und auf dem Startbildschirm des Handys. Am besten ein quadratisches Bild ohne Schrift, mindestens 512 × 512 Pixel. Ohne eigenes Symbol zeigt HUBIplan sein H-Zeichen in den Farben der Instanz.',
        )}
      </p>
      {editable ? (
        <LogoUpload
          uploadUrl="/api/platform/icon/"
          logoUrl={shown}
          onChange={async () => {
            await loadPlatform(true)
            setVersion(Date.now())
          }}
        />
      ) : (
        !shown && <p className="muted">{t('Kein eigenes Symbol.')}</p>
      )}
      {instance.icon && (
        <>
          <h3>{t('Vorschau')}</h3>
          <div className="icon-preview">
            <span className="icon-preview-tab">
              <img src={src('32')} alt="" width={16} height={16} />
              {t('Heller Browser-Tab')}
            </span>
            <span className="icon-preview-tab icon-preview-dark">
              <img src={src('32')} alt="" width={16} height={16} />
              {t('Dunkler Browser-Tab')}
            </span>
            <img
              src={src('maskable')}
              alt={t('Symbol auf dem Handy (rund ausgeschnitten)')}
              className="icon-preview-round"
              width={64}
              height={64}
            />
          </div>
          <p className="muted small">
            {t(
              'Wer HUBIplan schon auf dem Startbildschirm hat, sieht das neue Symbol erst, wenn das Handy es neu abholt. Auf dem iPhone muss die Seite dazu neu zum Startbildschirm hinzugefügt werden.',
            )}
          </p>
        </>
      )}
    </div>
  )
}

function ColorInput({
  label,
  hint,
  value,
  inherited,
  error,
  onChange,
}: {
  label: string
  hint: string
  value: string
  inherited: string
  error?: string
  onChange: (v: string) => void
}) {
  return (
    <div className={`field color-field${error ? ' field-invalid' : ''}`}>
      <span>{label}</span>
      <div className="color-row">
        <input
          type="color"
          aria-label={t('{label} wählen', { label })}
          value={value || inherited}
          onChange={(e) => onChange(e.target.value)}
        />
        <input
          aria-label={t('{label} als Hex-Wert', { label })}
          value={value}
          placeholder={t('{inherited} (geerbt)', { inherited })}
          onChange={(e) => onChange(e.target.value.trim())}
        />
        {value && (
          <button type="button" className="button button-ghost" onClick={() => onChange('')}>
            {t('Erben')}
          </button>
        )}
      </div>
      <small className={error ? 'field-error' : 'muted'}>{error ?? hint}</small>
    </div>
  )
}

function ColorName({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <Field
      label={label}
      value={value}
      maxLength={30}
      placeholder={t('z. B. Grün')}
      hint={t('Erscheint bei der Auswahl der Farben für die Webseite.')}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function ColorUse({
  label,
  value,
  error,
  onChange,
}: {
  label: string
  value: string
  error?: string
  onChange: (v: string) => void
}) {
  return (
    <Field
      label={label}
      value={value}
      maxLength={60}
      placeholder={t('z. B. Kopf und Schaltflächen')}
      hint={t('Erscheint im Farbblatt.')}
      error={error}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

const MAX_EXTRA = 4
const MAX_GRADIENTS = 2

/** Bis zu zwei benannte Verläufe aus der Palette (Webseite: Kopf, Fuß, Bänder, Zierlinien) */
function Gradients({
  gradients,
  palette,
  error,
  ownPrimary,
  onChange,
}: {
  gradients: GradientSetting[]
  palette: { color: string; name: string }[]
  error?: string
  ownPrimary: boolean
  onChange: (v: GradientSetting[]) => void
}) {
  const update = (i: number, patch: Partial<GradientSetting>) =>
    onChange(gradients.map((g, j) => (j === i ? { ...g, ...patch } : g)))
  const valid = (c?: string) => Boolean(c && /^#[0-9a-f]{6}$/i.test(c))
  const slotName = (i: number) => {
    const p = palette[i]
    const role =
      i === 0 ? t('Hauptfarbe') : i === 1 ? t('Zweitfarbe') : t('{x}. Farbe', { x: i + 1 })
    return p?.name ? `${role} (${p.name})` : role
  }
  return (
    <div className={`field color-group${error ? ' field-invalid' : ''}`}>
      <span>{t('Verläufe')}</span>
      <small className="muted">
        {t(
          'Für Kopf, Fuß, Farbbänder und Zierlinien der Webseite, z. B. von Blau nach Dunkelblau. Welche Stelle einen Verlauf bekommt, stellst du unter Webseite › Gestaltung ein.',
        )}
        {!ownPrimary && t(' Verläufe gelten nur zusammen mit einer eigenen Hauptfarbe.')}
      </small>
      <div className="color-list">
        {gradients.map((g, i) => {
          const a = palette[g.from]?.color
          const b = palette[g.to]?.color
          const ok = valid(a) && valid(b)
          const on = ok ? readableOnPair(a as string, b as string) : '#000000'
          const ratio = ok
            ? Math.min(contrastRatio(a as string, on), contrastRatio(b as string, on))
            : 0
          return (
            <div className="gradient-row" key={i}>
              <div className="gradient-row-head">
                <span
                  className="gradient-swatch"
                  aria-hidden="true"
                  style={
                    ok ? { background: gradientCss(a!, b!, g.direction), color: on } : undefined
                  }
                >
                  {g.name || t('Verlauf {x}', { x: i + 1 })}
                </span>
                <span className={`color-contrast small ${ok && ratio >= 4.5 ? 'ok' : 'bad'}`}>
                  {ok &&
                    `${ratio >= 4.5 ? '✓' : '✗'} ${t('Text darauf {x} : 1', { x: ratio.toFixed(1) })}`}
                </span>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => onChange(gradients.filter((_, j) => j !== i))}
                >
                  {t('Entfernen')}
                </button>
              </div>
              <div className="gradient-row-fields">
                <Field
                  label={t('Name')}
                  value={g.name}
                  maxLength={30}
                  placeholder={t('z. B. Blauverlauf')}
                  onChange={(e) => update(i, { name: e.target.value })}
                />
                <SelectField
                  label={t('von')}
                  value={String(g.from)}
                  onChange={(e) => update(i, { from: Number(e.target.value) })}
                >
                  {palette.map((_, j) => (
                    <option key={j} value={String(j)}>
                      {slotName(j)}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label={t('nach')}
                  value={String(g.to)}
                  onChange={(e) => update(i, { to: Number(e.target.value) })}
                >
                  {palette.map((_, j) => (
                    <option key={j} value={String(j)}>
                      {slotName(j)}
                    </option>
                  ))}
                </SelectField>
                <SelectField
                  label={t('Richtung')}
                  value={g.direction}
                  onChange={(e) =>
                    update(i, { direction: e.target.value === 'down' ? 'down' : 'right' })
                  }
                >
                  <option value="right">{t('von links nach rechts')}</option>
                  <option value="down">{t('von oben nach unten')}</option>
                </SelectField>
              </div>
            </div>
          )
        })}
      </div>
      {gradients.length < MAX_GRADIENTS && palette.length >= 2 && (
        <div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() =>
              onChange([...gradients, { name: '', from: 0, to: 1, direction: 'right' }])
            }
          >
            {t('Verlauf hinzufügen')}
          </button>
        </div>
      )}
      {error && <small className="field-error">{error}</small>}
    </div>
  )
}

/** Weitere Farben der Einheit (zusammen bis sechs); genutzt von den Webseiten-Designs */
function ExtraColors({
  colors,
  error,
  ownPrimary,
  onChange,
}: {
  colors: ExtraColor[]
  error?: string
  ownPrimary: boolean
  onChange: (v: ExtraColor[]) => void
}) {
  const update = (i: number, patch: Partial<ExtraColor>) =>
    onChange(colors.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const move = (i: number, d: number) => {
    const next = [...colors]
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    onChange(next)
  }
  return (
    <div className={`field color-group${error ? ' field-invalid' : ''}`}>
      <span>{t('Weitere Farben')}</span>
      <small className="muted">
        {t(
          'Für Einheiten mit drei oder mehr Vereinsfarben. Die Webseiten-Designs nutzen sie für Zierlinien, Farbbänder und Datumsfelder.',
        )}
        {!ownPrimary && t(' Weitere Farben gelten nur zusammen mit einer eigenen Hauptfarbe.')}
      </small>
      <div className="color-list">
        {colors.map((c, i) => {
          const valid = /^#[0-9a-f]{6}$/i.test(c.color)
          const ratio = valid ? contrastRatio(c.color, readableOn(c.color)) : 0
          return (
            <div className="color-row extra-color-row" key={i}>
              <input
                type="color"
                aria-label={t('{x}. Farbe wählen', { x: i + 3 })}
                value={valid ? c.color : '#000000'}
                onChange={(e) => update(i, { color: e.target.value })}
              />
              <input
                aria-label={t('{x}. Farbe als Hex-Wert', { x: i + 3 })}
                value={c.color}
                onChange={(e) => update(i, { color: e.target.value.trim() })}
              />
              <input
                aria-label={t('Name der {x}. Farbe', { x: i + 3 })}
                value={c.name}
                maxLength={30}
                placeholder={t('Name, z. B. Weinrot')}
                onChange={(e) => update(i, { name: e.target.value })}
              />
              <input
                aria-label={t('Verwendung der {x}. Farbe', { x: i + 3 })}
                value={c.use ?? ''}
                maxLength={60}
                placeholder={t('Verwendung, z. B. Fließtext')}
                onChange={(e) => update(i, { use: e.target.value })}
              />
              <span className={`color-contrast small ${valid && ratio >= 4.5 ? 'ok' : 'bad'}`}>
                {valid &&
                  `${ratio >= 4.5 ? '✓' : '✗'} ${t('Text darauf {x} : 1', { x: ratio.toFixed(1) })}`}
              </span>
              <div className="color-row-actions">
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x}. Farbe nach oben', { x: i + 3 })}
                  disabled={i === 0}
                  onClick={() => move(i, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{x}. Farbe nach unten', { x: i + 3 })}
                  disabled={i === colors.length - 1}
                  onClick={() => move(i, 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => onChange(colors.filter((_, j) => j !== i))}
                >
                  {t('Entfernen')}
                </button>
              </div>
            </div>
          )
        })}
      </div>
      {colors.length < MAX_EXTRA && (
        <div>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => onChange([...colors, { color: '#8b1e2d', name: '' }])}
          >
            {t('Farbe hinzufügen')}
          </button>
        </div>
      )}
      {error && <small className="field-error">{error}</small>}
    </div>
  )
}

function ContrastHints({ primary, accent }: { primary: string; accent: string }) {
  if (!/^#[0-9a-f]{6}$/i.test(primary) || !/^#[0-9a-f]{6}$/i.test(accent)) return null
  const checks = [
    {
      label: t('Text auf Primärfarbe'),
      ratio: contrastRatio(primary, readableOn(primary)),
      min: 4.5,
    },
    {
      label: t('Primärfarbe auf Weiß (Rahmen, Symbole)'),
      ratio: contrastRatio(primary, '#ffffff'),
      min: 3,
    },
    {
      label: t('Text auf Akzentfarbe'),
      ratio: contrastRatio(accent, readableOn(accent)),
      min: 4.5,
    },
  ]
  const link = linkColor(primary)
  return (
    <ul className="contrast-list">
      {checks.map((c) => (
        <li key={c.label} className={c.ratio >= c.min ? 'ok' : 'bad'}>
          {c.ratio >= c.min ? '✓' : '✗'} {c.label}
          {t(': {x} : 1 (mind. {min} : 1)', { x: c.ratio.toFixed(1), min: c.min })}
        </li>
      ))}
      <li className="ok">
        {t('✓ Links auf Weiß und auf dem Seitenhintergrund:')}{' '}
        {Math.min(contrastRatio(link, '#ffffff'), contrastRatio(link, PAGE_BG)).toFixed(1)}{' '}
        {t(': 1 (mind. 4.5 : 1)')}
        {t(', zum Fließtext: {x} : 1 (mind. 3 : 1)', {
          x: contrastRatio(link, TEXT_COLOR).toFixed(1),
        })}
        {link.toLowerCase() !== primary.toLowerCase() && (
          <>
            {' '}
            {t('– dafür wird automatisch ein angepasster Ton verwendet')}{' '}
            <span className="color-swatch" style={{ background: link }} aria-hidden="true" /> {link}
          </>
        )}
      </li>
    </ul>
  )
}

export function LogoUpload({
  uploadUrl,
  logoUrl,
  onChange,
  dark = false,
}: {
  uploadUrl: string
  logoUrl: string | null
  onChange: () => void | Promise<void>
  /** Logo für den Dunkelmodus: Vorschau auf dunklem Grund */
  dark?: boolean
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Wappen kommen oft mit weißem Hintergrund; der wird standardmäßig entfernt. Dunkle
  // Fassungen haben eher helle Ränder, die bleiben sollen
  const [removeBackground, setRemoveBackground] = useState(!dark)
  const crop = useImageCrop({
    title: dark ? t('Ausschnitt für das Logo im Dunkelmodus') : t('Ausschnitt für Logo/Wappen'),
    maxSide: 1024,
  })

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const chosen = e.target.files?.[0]
    e.target.value = ''
    if (!chosen) return
    const file = await crop.pick(chosen)
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      await orgApi.uploadLogo(uploadUrl, file, removeBackground)
      await onChange()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    try {
      await api.del(uploadUrl)
      await onChange()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="logo-upload-box">
      {logoUrl && (
        <img
          src={logoUrl}
          alt={dark ? t('Logo für den Dunkelmodus') : t('Logo')}
          className={`logo-preview ${dark ? 'logo-preview-dark' : 'logo-preview-checker'}`}
        />
      )}
      <div className="button-row">
        <label className="button button-ghost">
          {logoUrl ? t('Anderes Bild wählen') : t('Bild hochladen')}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="file-input"
            disabled={busy}
            onChange={upload}
          />
        </label>
        {crop.dialog}
        <RightsHint />
        {logoUrl && (
          <button type="button" className="button button-ghost" onClick={remove} disabled={busy}>
            {t('Entfernen')}
          </button>
        )}
      </div>
      <Checkbox
        label={t('Weißen Hintergrund entfernen')}
        hint={t('Weiß am Rand wird durchsichtig, Weiß im Wappen bleibt')}
        checked={removeBackground}
        onChange={setRemoveBackground}
        disabled={busy}
      />
      <p className="muted small">{t('PNG, JPG oder WebP, höchstens 2 MB.')}</p>
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
