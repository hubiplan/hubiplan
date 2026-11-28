import { useState } from 'react'
import { Link } from 'react-router-dom'
import { orgApi, PERM } from '../../api/orgs.ts'
import { PALETTE_ROLES } from '../../api/orgs.ts'
import type { PaletteRole, PaletteRoles, ThemeSettings } from '../../api/orgs.ts'
import { Alert, Checkbox, Field } from '../../components/ui.tsx'
import { useForm } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { contrastRatio, readableOn } from '../../theme/contrast.ts'
import { appColors, buttonColors, linkColor, PAGE_BG, TEXT_COLOR } from '../../theme/theme.ts'
import { t } from '../../i18n/index.ts'
import { loadPlatform, usePlatform } from '../../theme/platform.ts'
import { LogoUpload } from './LogoUpload.tsx'
import { ExtraColors } from './ExtraColors.tsx'
import { roleLabel } from './appearanceHelpers.ts'
import { ColorRoles } from './ColorRoles.tsx'
import { Gradients } from './Gradients.tsx'

export function ThemeForm({
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
    palette_roles: theme.palette_roles ?? ({} as PaletteRoles),
    palette_roles_in_app: theme.palette_roles_in_app ?? false,
  })
  const eff = theme.effective
  const primary = form.values.primary_color || eff.primary
  const accent = form.values.accent_color || eff.accent
  const buttonPreview = buttonColors(primary, readableOn(primary))
  const roles = form.values.palette_roles
  // Jede Rolle hat höchstens eine Farbe: Ankreuzen bei einer Farbe nimmt sie der vorigen
  const toggleRole = (slot: number, role: PaletteRole, on: boolean) => {
    const next = { ...roles }
    if (on) next[role] = slot
    else if (next[role] === slot) delete next[role]
    form.set('palette_roles', next)
  }
  // Weitere Farben verschoben oder entfernt: Rollen und Verläufe zeigen weiter auf dieselbe Farbe
  const remapSlots = (map: (slot: number) => number | null) => {
    const next: PaletteRoles = {}
    for (const role of PALETTE_ROLES) {
      const slot = roles[role]
      const moved = slot === undefined ? null : map(slot)
      if (moved !== null) next[role] = moved
    }
    form.set('palette_roles', next)
    form.set(
      'gradients',
      form.values.gradients.flatMap((g) => {
        const from = map(g.from)
        const to = map(g.to)
        return from === null || to === null ? [] : [{ ...g, from, to }]
      }),
    )
  }
  const paletteColors = [{ color: primary }, { color: accent }, ...form.values.extra_colors]

  // Farben wirken nach außen (alle Mitglieder, Webseite, Briefe): Änderungen zeigt erst die
  // Vorschau, für alle gelten sie nach „Für alle übernehmen“ (UX-Audit 16.11. VW-22, F-7).
  const [applied, setApplied] = useState(form.values)
  const pending: Partial<typeof form.values> = {}
  for (const key of Object.keys(form.values) as (keyof typeof form.values)[]) {
    if (JSON.stringify(form.values[key]) !== JSON.stringify(applied[key]))
      Object.assign(pending, { [key]: form.values[key] })
  }
  const dirty = editable && Object.keys(pending).length > 0
  const discard = () => {
    form.setValues(applied)
    form.setErrors({})
    form.setMessage(null)
  }
  useDraftGuard(dirty)
  const apply = () =>
    form.submit(async () => {
      const values = form.values
      const saved = await orgApi.updateTheme(orgId, pending)
      setApplied(values)
      onSaved(saved)
      void refresh()
      // Farben der Instanz gelten auch für Anmeldeseite und Seiten ohne Einheit
      if (isPlatform) void loadPlatform(true)
    }, t('Übernommen. Die Farben gelten jetzt für alle.'))

  return (
    <div className="stack">
      <form
        className="card card-wide"
        onSubmit={(e) => {
          e.preventDefault()
          if (dirty) void apply()
        }}
      >
        <h2>{t('Farben')}</h2>
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
          <ColorRoles
            label={t('Hauptfarbe verwendet für')}
            slot={0}
            roles={roles}
            onToggle={toggleRole}
          />
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
          <ColorRoles
            label={t('Zweitfarbe verwendet für')}
            slot={1}
            roles={roles}
            onToggle={toggleRole}
          />
          <ExtraColors
            colors={form.values.extra_colors}
            error={form.errors.extra_colors}
            ownPrimary={Boolean(form.values.primary_color)}
            roles={roles}
            onToggleRole={toggleRole}
            onChange={(v, map) => {
              form.set('extra_colors', v)
              if (map) remapSlots(map)
            }}
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
          <AppRoles
            palette={paletteColors}
            roles={roles}
            enabled={form.values.palette_roles_in_app}
            onChange={(v) => form.set('palette_roles_in_app', v)}
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
        {editable && (
          <div className="stack" data-testid="farben-uebernehmen">
            <p className="small" role="status">
              {dirty
                ? t(
                    'Bisher siehst nur du die Änderungen in der Vorschau. Für alle gelten sie erst nach „Für alle übernehmen“.',
                  )
                : t(
                    'Änderungen an den Farben zeigt zuerst die Vorschau. Für alle gelten sie erst nach „Für alle übernehmen“.',
                  )}
            </p>
            {form.message && <Alert kind={form.message.kind}>{form.message.text}</Alert>}
            <div className="button-row">
              <button
                type="submit"
                className="button button-primary"
                disabled={!dirty || form.busy}
              >
                {t('Für alle übernehmen')}
              </button>
              {dirty && (
                <button type="button" className="button" disabled={form.busy} onClick={discard}>
                  {t('Änderungen verwerfen')}
                </button>
              )}
            </div>
          </div>
        )}
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

/** Farbrollen auch in der HUBIplan-Oberfläche (heller Modus), mit Kontrastschutz */
function AppRoles({
  palette,
  roles,
  enabled,
  onChange,
}: {
  palette: { color: string }[]
  roles: PaletteRoles
  enabled: boolean
  onChange: (v: boolean) => void
}) {
  const { dropped } = appColors(palette, roles)
  const any = PALETTE_ROLES.some((r) => roles[r] !== undefined)
  return (
    <div className="field">
      <span>{t('Farbrollen in HUBIplan')}</span>
      <small className="muted">
        {t(
          'Die angekreuzten Rollen gelten für die Webseite (Webseite › Gestaltung, dort lässt sich jede Rolle noch ändern). Auf Wunsch färben sie auch HUBIplan selbst, nur in der hellen Darstellung; der Dunkelmodus behält seine Farben. Ohne Rollen bleibt alles, wie es ist.',
        )}
      </small>
      <Checkbox
        label={t('Farbrollen auch in HUBIplan verwenden')}
        checked={enabled}
        onChange={onChange}
      />
      {enabled && !any && <p className="muted small">{t('Noch keine Rolle angekreuzt.')}</p>}
      {enabled && dropped.length > 0 && (
        <Alert kind="info">
          {t(
            'Zu wenig Kontrast (mind. 4.5 : 1), HUBIplan nimmt dort die eigene Farbe: {x}. Die Webseite nimmt die Farben trotzdem; Webseite › Gestaltung warnt dort.',
            { x: dropped.map(roleLabel).join(', ') },
          )}
        </Alert>
      )}
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
