// Zustand und Abläufe von WebsiteAdmin (WebsiteAdmin.tsx); die Darstellung steht dort.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { DRAFT_FIELDS, websiteApi } from '../../api/website.ts'
import type { DesignDraft, Website, WebsiteData, WebsiteSettings } from '../../api/website.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useAutoSave, useForm } from '../../components/forms.ts'
import { SaveStatus } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import type { PreviewFocus } from './styleTuningHelpers.ts'
import { useDesignHistory } from './designHistory.tsx'
import { t } from '../../i18n/index.ts'

export const SETTINGS: (keyof WebsiteSettings)[] = [
  'state',
  'maintenance_text',
  'blocks',
  'menu',
  'block_names',
  'menu_links',
  'menu_button',
  'menu_places',
  'home_sections',
  'design',
  'color_roles',
  'style',
  'layouts',
  'header_image',
  'header_image_narrow',
  'name_format',
  'name_formats',
  'show_vacant',
  'show_instrument',
  'show_titles',
  'show_address',
  'show_member_since',
  'missing_consent',
  'units_mode',
  'unit_ids',
  'include_unit_events',
  'include_parent_events',
  'include_parent_honors',
  'allow_indexing',
  'language',
  'contact_limit_per_hour',
  'notice_text',
  'notice_target',
  'notice_from',
  'notice_until',
  'notice_style',
  'notice_place',
  'notice_icon',
  'notice_button',
  'notice_date',
  'image_hosts',
]

export function pick(w: Website): WebsiteSettings {
  const values = Object.fromEntries(SETTINGS.map((k) => [k, w[k]])) as unknown as WebsiteSettings
  // Gestaltung: was im Entwurf steht, sonst der veröffentlichte Stand (G2)
  return { ...values, ...(w.draft ?? {}) }
}

/** Geänderte Felder der Gestaltung gehen in den Entwurf, alles andere wie bisher */
export function splitDraft(website: Website, changes: Partial<WebsiteSettings>) {
  if (website.draft === undefined) return changes
  const rest: Partial<WebsiteSettings> & { draft?: DesignDraft } = {}
  const draft: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(changes)) {
    if ((DRAFT_FIELDS as readonly string[]).includes(key)) draft[key] = value
    else (rest as Record<string, unknown>)[key] = value
  }
  if (Object.keys(draft).length > 0) rest.draft = draft as DesignDraft
  return rest
}

export type WebsiteAdminProps = {
  data: WebsiteData
  website: Website
  onChange: (data: WebsiteData) => void
  /** Neuer Stand von außen (Entwurf veröffentlicht, verworfen, Fassung zurückgeholt) */
  onReset: (data: WebsiteData) => void
  reload: () => void
}

export function useWebsiteAdmin({ data, website, onChange, reload }: WebsiteAdminProps) {
  const org = useActiveOrg()
  const form = useForm(pick(website))
  const { values: v, set, errors } = form
  const auto = useAutoSave(
    form,
    (changes) => websiteApi.save(org.id, splitDraft(website, changes)),
    {
      enabled: data.can_manage,
      onSaved: (saved) => onChange(saved as WebsiteData),
    },
  )
  const [message, setMessage] = useState<string | null>(null)
  // Punkt 5 (Ralf 14.11.): Stelle, die die Vorschau nach der letzten Änderung zeigt
  const [focus, setFocus] = useState<PreviewFocus>({})
  const navigate = useNavigate()
  // F6 (Ralf 16.11.2026): ein Verlauf für Design, Farben, Feinabstimmung und Bereiche
  const DESIGN_EMPTY: Record<string, unknown> = { style: {}, layouts: {}, color_roles: {} }
  const history = useDesignHistory(
    (key) => (v as unknown as Record<string, unknown>)[key] ?? DESIGN_EMPTY[key] ?? null,
    (key, value) => {
      setFocus({})
      ;(set as (k: string, x: unknown) => void)(key, value)
    },
  )

  async function remove() {
    const ok = await confirmDialog({
      final: true,
      title: t('Webseite entfernen?'),
      message: t(
        'Einstellungen, Domains und Vorschau-Links werden gelöscht. Die Daten in HUBIplan (Mitglieder, Termine, Einwilligungen) bleiben erhalten.',
      ),
      confirmLabel: t('Entfernen'),
    })
    if (!ok) return
    try {
      await websiteApi.remove(org.id)
      reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  const settings = (title: string, children: React.ReactNode) => (
    <form className="card card-wide" onSubmit={(e) => e.preventDefault()}>
      {data.can_manage && <SaveStatus auto={auto} />}
      <h2>{title}</h2>
      <fieldset disabled={!data.can_manage}>{children}</fieldset>
    </form>
  )

  return {
    org,
    form,
    v,
    set,
    errors,
    auto,
    message,
    setMessage,
    focus,
    setFocus,
    navigate,
    DESIGN_EMPTY,
    history,
    remove,
    settings,
  }
}

/** Alles, was die Teile der Seite brauchen: Angaben von außen und der Zustand des Hooks */
export type WebsiteAdminModel = WebsiteAdminProps & ReturnType<typeof useWebsiteAdmin>
