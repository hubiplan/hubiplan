// Webseite der Einheit: Einrichtung, Zustand, Domains, Vorschau, Einwilligungen.
import { api, requestBlob } from './client.ts'
import type { CropArea } from '../components/ImageCrop.tsx'
import type { PaletteColor } from './orgs.ts'

export type WebsiteState = 'off' | 'maintenance' | 'public'

export interface WebsiteSettings {
  state: WebsiteState
  maintenance_text: string
  blocks: Record<string, boolean>
  /** Anordnung des Menüs (Reihenfolge, Unterpunkte) */
  menu?: MenuNode[]
  /** Eigene Namen der Bausteine für Menü und Überschrift; fehlt = Standardname */
  block_names?: Record<string, string>
  /** Bausteine der Startseite in ihrer Reihenfolge */
  home_sections: HomeSection[]
  /** Standarddesign der Webseite (classic, festive, sidebar, stage, newspaper) */
  design: string
  /** Eigene Farbzuordnung je Design: Rolle → Palettenplatz oder „light“/„dark“ */
  color_roles: ColorRoles
  name_format: 'full' | 'initial'
  show_vacant: boolean
  missing_consent: 'omit' | 'nn'
  units_mode: 'all' | 'selected' | 'none'
  unit_ids: number[]
  include_unit_events: boolean
  include_parent_events: boolean
  /** weitergegebene Würden der Einheiten darüber (nur eigene Träger) */
  include_parent_honors: boolean
  allow_indexing: boolean
  /** Sprache der festen Texte auf der Webseite (de, en); Vereinsdaten bleiben, wie sie sind */
  language?: string
  contact_limit_per_hour: number
}

export type ColorRoles = Record<string, Record<string, number | string>>
/** Farben je Rolle eines Designs */
export type RoleColors = Record<string, { color: string; on_color: string }>

export interface DesignInfo {
  key: string
  label: string
  hint: string
  roles: { key: string; label: string; default: number | string }[]
  /** Eingespieltes Designpaket statt Standarddesign (fehlt bei älteren Ständen) */
  package?: boolean
  /** Skizze wie dieses Standarddesign */
  sketch?: string
}

/** Eingespieltes Designpaket (nur für Plattformverwalter) */
export interface DesignPackage {
  key: string
  label: string
  label_en: string
  hint: string
  /** für diese Webseite freigegeben */
  released: boolean
  /** diese Webseite nutzt es gerade */
  in_use: boolean
  released_count: number
  templates: string[]
  created_at: string
  updated_at: string
}

/** Ergebnis der Prüfung eines Pakets vor dem Einspielen */
export interface DesignPackageCheck {
  key: string
  label: string
  label_en: string
  hint: string
  sketch: string
  roles: string[]
  templates: string[]
  css_bytes: number
  warnings: string[]
  exists: boolean
  source: string
}

export interface DesignImportOptions {
  key: string
  label: string
  label_en: string
  check?: boolean
  replace?: boolean
}

/** Punkt im Menübaum (höchstens zwei Ebenen) */
export interface MenuNode {
  key: string
  children: MenuNode[]
}

/** Möglicher Menüpunkt: Baustein, eigene Textseite, Würde oder Überschrift */
export interface MenuItem {
  key: string
  /** Name im Menü (eigener Name oder Standard) */
  label: string
  /** Standardname (fehlt bei älteren Ständen) */
  default_label?: string
  /** Lässt sich unter „Bausteine“ umbenennen */
  renamable?: boolean
  hint: string
  /** Baustein, der den Punkt ein- und ausschaltet */
  toggle: string | null
  /** Überschrift ohne eigene Seite (z. B. „Geschichte“) */
  heading: boolean
  /** Standard-Oberpunkt */
  parent: string | null
}

export interface HomeSection {
  key: string
  on: boolean
}

export interface WebsiteDomain {
  id: number
  hostname: string
  is_primary: boolean
}

export interface PreviewLink {
  id: number
  label: string
  expires_at: string
  revoked_at: string | null
  is_active: boolean
  created_at: string
  created_by: string
  token?: string
  url?: string | null
}

export interface WebsiteCheck {
  key: string
  label: string
  ok: boolean
  blocking: boolean
  hint: string
}

export interface WebsitePrivacy {
  privacy_mode: 'text' | 'link'
  privacy_text: string
  privacy_url: string
}

export interface Website extends WebsiteSettings, WebsitePrivacy {
  privacy_generated_at: string | null
  privacy_published_text: string
  privacy_published_at: string | null
  checks: WebsiteCheck[]
  public_key: string
  effective_state: WebsiteState
  url: string | null
  /** Mögliche Menüpunkte in Standardreihenfolge (fehlt bei älteren Ständen) */
  menu_items?: MenuItem[]
  /** Farben je Rolle für jedes Design (Skizzen) */
  design_colors?: Record<string, RoleColors>
  domains: WebsiteDomain[]
  preview_links: PreviewLink[]
}

export interface WebsiteData {
  module_enabled: boolean
  can_manage: boolean
  can_edit_content: boolean
  preview_only: boolean
  block_labels: Record<string, string>
  /** Kurze Erklärung je Baustein (fehlt bei älteren Ständen) */
  block_hints?: Record<string, string>
  /** Bausteine der Startseite: Name, Erklärung, nötiger Bereich der Webseite */
  home_labels?: Record<string, string>
  home_hints?: Record<string, string>
  home_needs_block?: Record<string, string>
  units: { id: number; name: string }[]
  /** Standarddesigns zur Auswahl (fehlt bei älteren Ständen) */
  designs?: DesignInfo[]
  /** Farben der Einheit: Haupt-, Zweit- und weitere Farben */
  palette?: PaletteColor[]
  /** Darf Designpakete einspielen und freigeben (Plattformverwalter) */
  can_import_designs?: boolean
  website: Website | null
}

export interface ConsentCategory {
  category: string
  label: string
  kind: 'consent' | 'objection'
  active: boolean
  published: boolean
  since: string | null
  source: string
  history: { since: string; source: string; ended_at: string | null; ended_source: string }[]
}

const base = (org: number) => `/api/orgs/${org}/website/`

export const websiteApi = {
  get: (org: number) => api.get<WebsiteData>(base(org)),
  setup: (org: number) => api.post<WebsiteData>(base(org)),
  save: (org: number, data: Partial<WebsiteSettings & WebsitePrivacy>) =>
    api.put<WebsiteData>(base(org), data),
  generatePrivacy: (org: number) => api.post<WebsiteData>(`${base(org)}privacy/generate/`),
  publishPrivacy: (org: number) => api.post<WebsiteData>(`${base(org)}privacy/publish/`),
  remove: (org: number) => api.del(base(org)),
  addDomain: (org: number, hostname: string, isPrimary = false) =>
    api.post<WebsiteDomain>(`${base(org)}domains/`, { hostname, is_primary: isPrimary }),
  makePrimary: (org: number, id: number) =>
    api.put<WebsiteDomain>(`${base(org)}domains/${id}/`, {}),
  removeDomain: (org: number, id: number) => api.del(`${base(org)}domains/${id}/`),
  addPreviewLink: (org: number, label: string, days: number) =>
    api.post<PreviewLink>(`${base(org)}preview-links/`, { label, days }),
  revokePreviewLink: (org: number, id: number) => api.del(`${base(org)}preview-links/${id}/`),
  designPackages: (org: number) => api.get<DesignPackage[]>(`${base(org)}design-packages/`),
  importDesign: (org: number, file: File, options: DesignImportOptions) => {
    const form = new FormData()
    form.append('file', file)
    if (options.key) form.append('key', options.key)
    if (options.label) form.append('label', options.label)
    if (options.label_en) form.append('label_en', options.label_en)
    if (options.check) form.append('check', '1')
    if (options.replace) form.append('replace', '1')
    return api.post<{ ok: boolean; package: DesignPackageCheck | DesignPackage }>(
      `${base(org)}design-packages/`,
      form,
    )
  },
  releaseDesign: (org: number, key: string, released: boolean) =>
    api.patch<DesignPackage>(`${base(org)}design-packages/${key}/`, { released }),
  removeDesign: (org: number, key: string) => api.del(`${base(org)}design-packages/${key}/`),
  exportDesign: (org: number, key: string) =>
    requestBlob('GET', `${base(org)}design-packages/${key}/export/`),
  openPreview: (org: number) =>
    api.post<{ token: string; url: string | null }>(`${base(org)}preview/`),
  consents: (org: number, membership: number) =>
    api.get<{ categories: ConsentCategory[] }>(
      `/api/orgs/${org}/members/${membership}/publication/`,
    ),
  setConsent: (
    org: number,
    membership: number,
    data: { category: string; active: boolean; source?: 'board' | 'paper'; on?: string },
  ) =>
    api.put<{ categories: ConsentCategory[] }>(
      `/api/orgs/${org}/members/${membership}/publication/`,
      data,
    ),
}

export type TextKind = 'greeting' | 'page' | 'unit'

/** Seite der eigenen Webseite, verlinkt als seite:<ziel> */
export interface LinkTarget {
  href: string
  label: string
}

export interface WebsiteImage {
  id: number
  key: string
  caption: string
  alt_text: string
  /** bewusst ohne Beschreibung (reiner Schmuck) */
  decorative?: boolean
  width: number
  height: number
  url: string
  small_url: string
  markdown: string
  uploaded_at: string
  /** ganzes Original (zum neuen Zuschneiden) */
  original_url?: string
  /** gehört zu einer Untereinheit (leer: Verein allgemein) */
  department?: number | null
  department_name?: string | null
  /** zuletzt gewählter Ausschnitt (leer: ganzes Bild) */
  crop?: Partial<CropArea>
  version?: number
  updated_at?: string
  /** steht in einem Text (Entwurf oder veröffentlicht) */
  used?: boolean
}

/** Bild mit den Stellen, an denen es verwendet wird */
export interface WebsiteImageDetail extends WebsiteImage {
  usage: { text: number; label: string; places: string[] }[]
}

/** Neues Bild: ``file`` ist der Ausschnitt, ``original`` die ganze Datei */
export interface ImageUpload {
  file: File
  original?: File | null
  crop?: CropArea | null
  caption?: string
  alt_text?: string
  decorative?: boolean
  department?: number | null
}

function imageForm(data: ImageUpload): FormData {
  const form = new FormData()
  form.append('file', data.file)
  if (data.original && data.crop) {
    form.append('original', data.original)
    form.append('crop', JSON.stringify(data.crop))
  }
  if (data.caption) form.append('caption', data.caption)
  if (data.alt_text) form.append('alt_text', data.alt_text)
  if (data.decorative) form.append('decorative', 'true')
  if (data.department) form.append('department', String(data.department))
  return form
}

export interface WebsiteTextSummary {
  id: number
  kind: TextKind
  kind_label: string
  department: number | null
  department_name: string | null
  slug: string
  menu_position: number
  show_in_menu: boolean
  title: string
  is_published: boolean
  has_changes: boolean
  published_at: string | null
  updated_at: string
}

export interface WebsiteText extends WebsiteTextSummary {
  body: string
  image: number | null
  image_data: WebsiteImage | null
  /** Bilderkarussell der Begrüßung (IDs in Reihenfolge) */
  gallery: number[]
  /** Sekunden bis zum nächsten Bild im Karussell */
  gallery_interval: number
  /** Karussell beginnt mit einem zufälligen Bild statt mit dem ersten */
  gallery_random: boolean
  /** Bildunterschriften unter Bild und Karussell auf der Webseite zeigen */
  show_captions?: boolean
  /** Zeitleiste der Chronik (nur Textseite „geschichte“) */
  timeline: TimelineEntry[]
  has_timeline: boolean
  timeline_newest_first?: boolean
  published_title: string
  published_body: string
  revisions: { id: number; title: string; published_at: string; published_by: string }[]
}

export interface TextDraft {
  kind?: TextKind
  department?: number | null
  slug?: string
  menu_position?: number
  show_in_menu?: boolean
  title?: string
  body?: string
  image?: number | null
  gallery?: number[]
  gallery_interval?: number
  gallery_random?: boolean
  show_captions?: boolean
  timeline?: TimelineEntry[]
  timeline_newest_first?: boolean
}

/** Eintrag der Zeitleiste: ein Jahr oder ein Zeitraum (`until`), kurz gehalten.
 * Ein Kapitel ist eine Zwischenüberschrift; die Ereignisse ab seinem Jahr stehen darunter. */
export interface TimelineEntry {
  kind: 'event' | 'chapter'
  year: number | null
  until: number | null
  title: string
  text: string
  /** bis zu sechs Bilder (Ralf 02.11.) */
  images: number[]
  /** auto = abwechselnd links/rechts, below = groß unter dem Text (Ralf 02.11.) */
  image_position: ImagePosition
}

export type ImagePosition = 'auto' | 'left' | 'right' | 'below'

export const contentApi = {
  texts: (org: number) =>
    api.get<{
      texts: WebsiteTextSummary[]
      units: { id: number; name: string }[]
      /** Seiten der eigenen Webseite für den Link-Dialog */
      link_targets?: LinkTarget[]
    }>(`${base(org)}texts/`),
  text: (org: number, id: number) => api.get<WebsiteText>(`${base(org)}texts/${id}/`),
  create: (org: number, data: TextDraft) => api.post<WebsiteText>(`${base(org)}texts/`, data),
  save: (org: number, id: number, data: TextDraft) =>
    api.put<WebsiteText>(`${base(org)}texts/${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}texts/${id}/`),
  /** Reihenfolge der eigenen Seiten im Menü */
  reorderPages: (org: number, ids: number[]) => api.post(`${base(org)}texts/reorder/`, { ids }),
  publish: (org: number, id: number) => api.post<WebsiteText>(`${base(org)}texts/${id}/publish/`),
  unpublish: (org: number, id: number) =>
    api.delWith<WebsiteText>(`${base(org)}texts/${id}/publish/`, {}),
  restore: (org: number, id: number, rev: number) =>
    api.post<WebsiteText>(`${base(org)}texts/${id}/revisions/${rev}/restore/`),
  /** Excel/CSV lesen; gespeichert wird nichts, die Einträge kommen in den Entwurf */
  importTimeline: (org: number, id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ entries: TimelineEntry[]; errors: { line: number; message: string }[] }>(
      `${base(org)}texts/${id}/timeline-import/`,
      form,
    )
  },
  images: (org: number) => api.get<WebsiteImage[]>(`${base(org)}images/`),
  upload: (org: number, data: ImageUpload) =>
    api.post<WebsiteImage>(`${base(org)}images/`, imageForm(data)),
  image: (org: number, id: number) => api.get<WebsiteImageDetail>(`${base(org)}images/${id}/`),
  saveImage: (
    org: number,
    id: number,
    data: {
      caption?: string
      alt_text?: string
      decorative?: boolean
      department?: number | null
    },
  ) => api.put<WebsiteImage>(`${base(org)}images/${id}/`, data),
  /** Neuer Ausschnitt aus dem Original */
  cropImage: (org: number, id: number, file: File, crop: CropArea) => {
    const form = new FormData()
    form.append('file', file)
    form.append('crop', JSON.stringify(crop))
    return api.post<WebsiteImage>(`${base(org)}images/${id}/crop/`, form)
  },
  /** Neue Datei für dasselbe Bild; Stellen und Angaben bleiben */
  replaceImage: (org: number, id: number, data: ImageUpload) =>
    api.post<WebsiteImage>(`${base(org)}images/${id}/replace/`, imageForm(data)),
  /** Zweites Bild aus demselben Original */
  copyImage: (org: number, id: number, file: File, crop: CropArea) => {
    const form = new FormData()
    form.append('file', file)
    form.append('crop', JSON.stringify(crop))
    return api.post<WebsiteImage>(`${base(org)}images/${id}/copy/`, form)
  },
  /** Ohne `confirmed` lehnt der Server ein verwendetes Bild mit 409 und den Stellen ab. */
  removeImage: (org: number, id: number, confirmed = false) =>
    api.del(`${base(org)}images/${id}/${confirmed ? '?trotzdem=1' : ''}`),
}

export interface HeldMessage {
  id: number
  recipient_name: string
  sender_name: string
  sender_email: string
  subject: string
  body: string
  reason: string
  created_at: string
}

export const heldApi = {
  list: (org: number) => api.get<HeldMessage[]>(`${base(org)}held/`),
  release: (org: number, id: number) => api.post(`${base(org)}held/${id}/`),
  discard: (org: number, id: number) => api.del(`${base(org)}held/${id}/`),
}

// --- Social-Media-Beiträge (Instagram/Facebook, eigene Meta-App der Einheit) ---

export type SocialKind = 'instagram' | 'facebook'

export interface SocialFeed {
  id: number
  kind: SocialKind
  kind_label: string
  department: number | null
  department_name: string | null
  mode: 'auto' | 'approval'
  max_posts: number
  show_link: boolean
  strip_hashtags: boolean
  is_active: boolean
  app_id: string
  config_id: string
  via_facebook: boolean
  has_secret: boolean
  status: 'new' | 'choose' | 'ok' | 'error' | 'expired'
  status_label: string
  account_name: string
  token_expires_at: string | null
  last_sync_at: string | null
  last_error: string
  connected_at: string | null
  pages: { id: string; name: string }[]
  post_count: number
  pending_count: number
}

export interface SocialFeedDraft {
  kind?: SocialKind
  department?: number | null
  mode?: 'auto' | 'approval'
  max_posts?: number
  show_link?: boolean
  strip_hashtags?: boolean
  is_active?: boolean
  app_id?: string
  config_id?: string
  via_facebook?: boolean
  app_secret?: string
}

export interface SocialPost {
  id: number
  feed: number
  media_type: 'image' | 'album' | 'video' | 'text'
  text: string
  permalink: string
  published_at: string
  state: 'visible' | 'pending' | 'hidden'
  state_label: string
  images: {
    id: number
    url: string
    small_url: string
    alt_text: string
    is_video: boolean
    width: number
    height: number
  }[]
}

export const socialApi = {
  list: (org: number) =>
    api.get<{
      feeds: SocialFeed[]
      redirect_uri: string
      units: { id: number; name: string }[]
      can_manage: boolean
    }>(`${base(org)}social/`),
  create: (org: number, data: SocialFeedDraft) => api.post<SocialFeed>(`${base(org)}social/`, data),
  save: (org: number, id: number, data: SocialFeedDraft) =>
    api.put<SocialFeed>(`${base(org)}social/${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}social/${id}/`),
  connect: (org: number, id: number) =>
    api.post<{ url: string }>(`${base(org)}social/${id}/connect/`),
  disconnect: (org: number, id: number) =>
    api.delWith<SocialFeed>(`${base(org)}social/${id}/connect/`, {}),
  choosePage: (org: number, id: number, page: string) =>
    api.post<SocialFeed>(`${base(org)}social/${id}/page/`, { page }),
  sync: (org: number, id: number) =>
    api.post<SocialFeed & { created: number }>(`${base(org)}social/${id}/sync/`),
  /** alle wartenden Beiträge des Kanals freigeben */
  publishPending: (org: number, id: number) =>
    api.post<SocialFeed & { published: number }>(`${base(org)}social/${id}/publish-pending/`),
  posts: (org: number, feed?: number) =>
    api.get<SocialPost[]>(`${base(org)}social/posts/${feed ? `?kanal=${feed}` : ''}`),
  setPost: (
    org: number,
    id: number,
    data: { state?: SocialPost['state']; alt_texts?: Record<string, string> },
  ) => api.put<SocialPost>(`${base(org)}social/posts/${id}/`, data),
}
