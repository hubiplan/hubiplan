// Webseite der Einheit: Einrichtung, Zustand, Domains, Vorschau, Einwilligungen.
import { api, requestBlob } from './client.ts'
import type { CropArea } from '../components/ImageCrop.tsx'
import type { Gradient, PaletteColor } from './orgs.ts'

export type WebsiteState = 'off' | 'maintenance' | 'public'

export interface WebsiteSettings {
  state: WebsiteState
  maintenance_text: string
  blocks: Record<string, boolean>
  /** Anordnung des Menüs (Reihenfolge, Unterpunkte) */
  menu?: MenuNode[]
  /** Eigene Namen der Bausteine für Menü und Überschrift; fehlt = Standardname */
  block_names?: Record<string, string>
  /** Adressen der Links nach außen im Menü: ``link:<Nummer>`` → https://… (Name in block_names) */
  menu_links?: Record<string, string>
  /** Hauptpunkt des Menüs, der als Knopf hervorgehoben ist; leer = keiner */
  menu_button?: string
  /** Platz von Hauptpunkten (Webseite #75): footer = nur im Fuß, both = Menü und Fuß; fehlt = Menü */
  menu_places?: Record<string, MenuPlace>
  /** Bausteine der Startseite in ihrer Reihenfolge */
  home_sections: HomeSection[]
  /** Standarddesign der Webseite (classic, festive, sidebar, stage, newspaper) */
  design: string
  /** Eigene Farbzuordnung je Design: Rolle → Palettenplatz oder „light“/„dark“ */
  color_roles: ColorRoles
  /** Kopfbild statt Wappen und Vereinsname (Bild der Bilderverwaltung) */
  header_image?: number | null
  /** Kopfbild für schmale Bildschirme unter 600 px (Webseite #73), optional */
  header_image_narrow?: number | null
  /** Stilregler (Feinabstimmung): nur verstellte; fehlt = wie das Design */
  style?: StyleValues
  /** Darstellung der festen Bereiche (G5): nur abweichende Varianten; fehlt = Standard */
  layouts?: Record<string, string>
  name_format: 'full' | 'initial'
  show_vacant: boolean
  /** Hauptinstrument aus dem Musikmodul unter dem Namen (fehlt bei älteren Ständen) */
  show_instrument?: boolean
  /** Titel (Dr., Prof. …) vor dem Namen; Standard aus */
  show_titles?: boolean
  /** Anschrift beim Vorstand, nur mit Einwilligung der Person */
  show_address?: boolean
  /** Mitgliederlisten mit Eintrittsjahr */
  show_member_since?: boolean
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
  /** Hinweisleiste oben auf allen Seiten (G6); leer = keine */
  notice_text?: string
  /** Ziel der Hinweisleiste wie bei Knöpfen; {} = keins */
  notice_target?: HomeTarget | Record<string, never>
  /** Zeitraum (JJJJ-MM-TT, Grenzen eingeschlossen); null = offen */
  notice_from?: string | null
  notice_until?: string | null
  /** Server, von denen ein KI-Assistent Bilder per Adresse holen darf (W3); fehlt = keine */
  image_hosts?: string[]
}

export type ColorRoles = Record<string, Record<string, number | string>>

/** Stilregler: Stufe (Text) oder Schalter (ja/nein) */
export type StyleValues = Record<string, string | boolean>

/** Stufen je Regler ("switch" = Schalter) und vom Design gesperrte Regler oder Stufen */
/** Bereich mit seinen Darstellungen (G5); die erste ist der Standard */
export interface LayoutArea {
  area: string
  variants: { key: string; label: string }[]
}

export interface StyleCatalog {
  options: Record<string, string[] | 'switch'>
  locks: Record<string, Record<string, string[] | null>>
  /** Stufe, die jedes Standarddesign ohne eigene Wahl zeigt (fehlt bei älteren Ständen) */
  defaults?: Record<string, Record<string, string | boolean>>
  /** Voreinstellungen: mehrere Regler auf einmal (fehlt bei älteren Ständen) */
  presets?: Record<string, Record<string, string | boolean>>
}
/** Farben je Rolle eines Designs */
export type RoleColors = Record<
  string,
  {
    color: string
    on_color: string
    /** Verlauf statt Vollfarbe (Kopf, Fuß, Bänder, Zierlinien) */
    gradient?: { from: string; to: string; direction: string }
  }
>

export interface DesignInfo {
  key: string
  label: string
  hint: string
  roles: {
    key: string
    label: string
    default: number | string | null
    /** Rolle kann einen Verlauf nehmen */
    gradient?: boolean
    /** Rolle in jedem Design (Text, Flächen, Hintergrund); Vorgabe ist das Design */
    common?: boolean
  }[]
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
export type MenuPlace = 'footer' | 'both'

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
  /** Adresse eines Links nach außen */
  url?: string | null
}

/** Eigene Abschnitte der Startseite (G3): mehrfach einsetzbar */
export type HomeKind =
  | 'text'
  | 'text_image'
  | 'banner'
  | 'buttons'
  | 'tiles'
  | 'event'
  | 'album'
  | 'quote'
  | 'contacts'
  | 'faq'
  | 'partners'
  | 'directions'
  | 'event_list'
  | 'document'
  | 'video'
  | 'chronicle'
  | 'facts'
  | 'divider'
  /** laufender Zähler bis zu einem Termin oder Zeitpunkt (Ralf 14.11.2026) */
  | 'countdown'
  | 'join'
  | 'donation'
  | 'hours'
  | 'columns'
  | 'table'
  | 'timeline'
  | 'program'
  | 'callout'
  | 'accordion'
  | 'images'
  | 'downloads'
  | 'unit_honors'
  | 'competition'
  | 'albums'
  | 'posts'
  | 'app'
  | 'live_facts'
  /** nur auf Textseiten (G6): schmales Bild über der Überschrift */
  | 'cover'

/** Ziel eines Knopfs oder einer Kachel: Menüpunkt, Termin oder Link nach außen */
export type HomeTarget = { page: string } | { event: number } | { url: string } | null

export interface HomeButton {
  label: string
  target: HomeTarget
}

export interface HomeTile {
  title: string
  text: string
  image: number | null
  target: HomeTarget
}

/** Inhalt eines eigenen Abschnitts; welche Felder zählen, hängt von der Art ab */
export interface HomeSectionData {
  title?: string
  text?: string
  image?: number | null
  side?: 'left' | 'right'
  /** Text mit Bild: small/half; Trenner: small/large */
  size?: 'small' | 'half' | 'large'
  line?: string
  height?: 'low' | 'high'
  buttons?: HomeButton[]
  align?: 'left' | 'center' | 'right'
  tiles?: HomeTile[]
  /** Kacheln 2|3, Bilder 2|3|4 */
  columns?: 2 | 3 | 4
  event?: number | null
  album?: number | null
  count?: number
  name?: string
  roles?: number[]
  /** Häufige Fragen, Partner, Zahlen: Einträge je nach Art */
  items?: HomeItem[]
  place?: number | null
  category?: number | null
  document?: number | null
  url?: string
  label?: string
  /** Trenner: line/space; Hinweis-Kasten: info/warning/success */
  style?: 'line' | 'space' | 'info' | 'warning' | 'success'
  /** Spendenaufruf */
  holder?: string
  iban?: string
  bic?: string
  purpose?: string
  goal?: number | null
  raised?: number | null
  /** Tabelle: Spaltenköpfe und Zeilen */
  head?: string[]
  rows?: string[][]
  /** Download-Liste: Dokumentnummern */
  documents?: number[]
  /** Majestäten einer Untereinheit */
  unit?: number | null
  /** Ergebnisse eines Wettbewerbs */
  competition?: number | null
  /** Neueste Beiträge */
  channel?: 'all' | 'instagram' | 'facebook'
  /** Mitgliederbereich und App */
  qr?: boolean
  store?: boolean
  /** Countdown: Ziel ist ein Termin oder ein frei gewählter Zeitpunkt (Ortszeit) */
  mode?: 'event' | 'date'
  at?: string
  /** Countdown nach Ablauf: ausblenden oder Text zeigen */
  after?: 'hide' | 'text'
  after_text?: string
}

/** Eintrag einer Liste: Frage/Antwort, Partner (Name, Logo, Link) oder Zahl mit Text */
export interface HomeItem {
  /** Zeiten, Festprogramm: Tag; Zeitstrahl: Zeitangabe */
  day?: string
  time?: string
  note?: string
  when?: string
  /** Zwei Spalten, Aufklappbar, Zeitstrahl */
  title?: string
  text?: string
  caption?: string
  /** Zahlen aus HUBIplan: members, years, units */
  fact?: string
  question?: string
  answer?: string
  name?: string
  image?: number | null
  url?: string
  value?: string
  label?: string
}

export interface HomeSection {
  key: string
  on: boolean
  /** Hintergrund: keiner, hell oder Palettenfarbe p0 … p9 (G3; fehlt bei älteren Ständen) */
  bg?: string
  width?: 'content' | 'text' | 'full'
  /** Spalte im Design „Zeitung“ */
  column?: 'main' | 'side'
  /** Nur eigene Abschnitte (Schlüssel c:…) */
  kind?: HomeKind
  data?: HomeSectionData
}

/** Auswahl für eigene Abschnitte: Rollen auf der Webseite, Alben, kommende Termine */
export interface HomeChoices {
  roles: { id: number; name: string }[]
  albums: { id: number; title: string }[]
  events: { id: number; title: string; starts_at: string }[]
  places?: { id: number; name: string }[]
  categories?: { id: number; name: string }[]
  documents?: { id: number; title: string }[]
  /** Majestäten einer Untereinheit, Ergebnisse eines Wettbewerbs, Zahlen aus HUBIplan */
  units?: { id: number; name: string }[]
  competitions?: { id: number; title: string; date: string }[]
  live_facts?: Record<string, string>
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
  /** Entwurf der Gestaltung: nur Abweichungen vom veröffentlichten Stand (fehlt bei älteren Ständen) */
  draft?: DesignDraft
  /** Frühere veröffentlichte Gestaltungen, neueste zuerst */
  design_versions?: DesignVersion[]
  /** F7: Entwurf ändert nur Inhalte der Abschnitte (dann auch mit „Inhalte bearbeiten“) */
  draft_content_only?: boolean
}

/** Was der Entwurf umfasst (Konzept webseite-baukasten G2) */
export const DRAFT_FIELDS = [
  'design',
  'color_roles',
  'style',
  'header_image',
  'header_image_narrow',
  'home_sections',
  'layouts',
  // Menü mit Namen, Links und Knopf (KI-Schnittstelle W2): erst nach „Veröffentlichen“ sichtbar
  'menu',
  'block_names',
  'menu_links',
  'menu_button',
  'menu_places',
] as const
export type DraftField = (typeof DRAFT_FIELDS)[number]
export type DesignDraft = Partial<Pick<WebsiteSettings, DraftField>>

export function hasDraft(website: Website): boolean {
  return Object.keys(website.draft ?? {}).length > 0
}

export interface DesignVersion {
  id: number
  published_at: string
  published_by: string
}

/** Was der Abschnitts-Baukasten braucht (Startseite: WebsiteData, Textseiten: Texte-Liste) */
export type SectionOptions = Pick<
  WebsiteData,
  | 'block_labels'
  | 'home_labels'
  | 'home_hints'
  | 'home_needs_block'
  | 'home_kinds'
  | 'home_kind_hints'
  | 'home_kind_needs_block'
  | 'home_choices'
  | 'palette'
  | 'gradients'
  | 'units'
>
export interface SectionSite {
  menu_items?: MenuItem[]
}
/** Abschnitte der Textseiten (G4): Auswahl und Bereiche der Webseite */
export type PageSectionOptions = SectionOptions & SectionSite & { blocks: Record<string, boolean> }

export interface WebsiteData {
  module_enabled: boolean
  can_manage: boolean
  can_edit_content: boolean
  /** F7: Inhalte der Startseiten-Abschnitte bearbeiten (fehlt bei älteren Ständen) */
  can_edit_home_content?: boolean
  preview_only: boolean
  block_labels: Record<string, string>
  /** Kurze Erklärung je Baustein (fehlt bei älteren Ständen) */
  block_hints?: Record<string, string>
  /** Bausteine der Startseite: Name, Erklärung, nötiger Bereich der Webseite */
  home_labels?: Record<string, string>
  home_hints?: Record<string, string>
  home_needs_block?: Record<string, string>
  /** Eigene Abschnitte (G3): Arten mit Hinweis und nötigem Bereich */
  home_kinds?: Record<HomeKind, string>
  home_kind_hints?: Record<HomeKind, string>
  home_kind_needs_block?: Partial<Record<HomeKind, string>>
  home_choices?: HomeChoices
  units: { id: number; name: string }[]
  /** Es gibt Einheiten darüber, deren öffentliche Termine die Webseite zeigen kann */
  has_parent_units?: boolean
  /** Standarddesigns zur Auswahl (fehlt bei älteren Ständen) */
  designs?: DesignInfo[]
  /** Farben der Einheit: Haupt-, Zweit- und weitere Farben */
  palette?: PaletteColor[]
  /** Verläufe der Einheit (Einstellungen › Erscheinungsbild) */
  gradients?: Gradient[]
  /** Darf Designpakete einspielen und freigeben (Plattformverwalter) */
  can_import_designs?: boolean
  /** Stilregler der Feinabstimmung (fehlt bei älteren Ständen) */
  style_catalog?: StyleCatalog
  /** Darstellung der festen Bereiche (G5, fehlt bei älteren Ständen) */
  layout_catalog?: LayoutArea[]
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
  save: (org: number, data: Partial<WebsiteSettings & WebsitePrivacy> & { draft?: DesignDraft }) =>
    api.put<WebsiteData>(base(org), data),
  publishDesign: (org: number) => api.post<WebsiteData>(`${base(org)}design/publish/`),
  /** F7: nur Inhalte vorhandener Abschnitte der Startseite, auch mit „Inhalte bearbeiten“ */
  saveHomeContent: (org: number, home_sections: HomeSection[]) =>
    api.put<WebsiteData>(`${base(org)}home-content/`, { home_sections }),
  publishHomeContent: (org: number) => api.post<WebsiteData>(`${base(org)}home-content/publish/`),
  discardDesign: (org: number) => api.post<WebsiteData>(`${base(org)}design/discard/`),
  restoreDesign: (org: number, id: number) =>
    api.post<WebsiteData>(`${base(org)}design/versions/${id}/restore/`),
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

/** intro = Einleitung eines festen Bereichs (G5), Adresse = Bereich */
export type TextKind = 'greeting' | 'page' | 'unit' | 'intro'

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
  /** Aufnahmezeit aus der Kamera (zum Sortieren der Galerie) */
  taken_at?: string | null
  file_name?: string
}

/** Bild mit den Stellen, an denen es verwendet wird */
export interface WebsiteImageDetail extends WebsiteImage {
  /** ``text`` bei Texten, ``album`` bei Alben der Galerie */
  usage: {
    text: number | null
    album?: number
    header?: boolean
    label: string
    places: string[]
  }[]
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
  /** Einleitung (G5): Name des Bereichs */
  area_label?: string | null
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
  /** Abschnitte der Textseite (G4); „body“ ist Bild und Text oben (fehlt bei älteren Ständen) */
  sections?: HomeSection[]
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
  sections?: HomeSection[]
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

/** Chronik (Modul „Chronik“): Textseite „geschichte“ mit Zeitleiste, auch ohne Webseite */
export interface ChronicleState {
  text: WebsiteText | null
  can_edit: boolean
  website: boolean
}

export const chronicleApi = {
  get: (org: number) => api.get<ChronicleState>(`/api/orgs/${org}/chronicle/`),
}

export const contentApi = {
  texts: (org: number) =>
    api.get<{
      texts: WebsiteTextSummary[]
      units: { id: number; name: string }[]
      /** Seiten der eigenen Webseite für den Link-Dialog */
      link_targets?: LinkTarget[]
      /** Auswahl für die Abschnitte der Textseiten (fehlt bei älteren Ständen) */
      section_options?: PageSectionOptions
      /** Bereiche, über denen eine Einleitung stehen kann (G5) */
      intro_areas?: { area: string; label: string }[]
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

// --- Galerie (Ralf 05.11.2026) ---

export type ImageSort =
  | 'manual'
  | 'taken'
  | 'taken_desc'
  | 'name'
  | 'name_desc'
  | 'uploaded'
  | 'uploaded_desc'
  | 'caption'
  | 'caption_desc'
export type AlbumSort = 'manual' | 'date_desc' | 'date' | 'title' | 'title_desc'

export interface GalleryAlbum {
  id: number
  parent: number | null
  title: string
  slug: string
  description: string
  date: string | null
  cover: number | null
  published: boolean
  show_captions: boolean
  image_order: ImageSort
  children_order: AlbumSort
  position: number
  image_count: number
  updated_at: string
  /** nur in der Liste: kleines Titelbild */
  cover_url?: string | null
  /** nur einzeln: Bilder in Anzeigereihenfolge */
  images?: WebsiteImage[]
}

export interface GalleryListing {
  albums: GalleryAlbum[]
  block_on: boolean
  gallery_order: AlbumSort
  image_orders: { value: ImageSort; label: string }[]
  album_orders: { value: AlbumSort; label: string }[]
}

export type AlbumDraft = Partial<
  Pick<
    GalleryAlbum,
    | 'parent'
    | 'title'
    | 'slug'
    | 'description'
    | 'date'
    | 'cover'
    | 'published'
    | 'show_captions'
    | 'image_order'
    | 'children_order'
  >
> & { images?: number[] }

export const galleryApi = {
  list: (org: number) => api.get<GalleryListing>(`${base(org)}albums/`),
  setOrder: (org: number, order: AlbumSort) =>
    api.put<GalleryListing>(`${base(org)}albums/`, { gallery_order: order }),
  create: (org: number, data: AlbumDraft) => api.post<GalleryAlbum>(`${base(org)}albums/`, data),
  get: (org: number, id: number) => api.get<GalleryAlbum>(`${base(org)}albums/${id}/`),
  save: (org: number, id: number, data: AlbumDraft) =>
    api.put<GalleryAlbum>(`${base(org)}albums/${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}albums/${id}/`),
  addImages: (org: number, id: number, images: number[]) =>
    api.post<GalleryAlbum>(`${base(org)}albums/${id}/images/`, { images }),
  reorder: (org: number, ids: number[], parent: number | null) =>
    api.post(`${base(org)}albums/reorder/`, { ids, parent }),
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

/** Entwurf für einen Beitrag auf Instagram oder Facebook (KI-Schnittstelle W3) */
export interface SocialDraft {
  id: number
  channel: '' | 'instagram' | 'facebook'
  channel_label: string
  text: string
  images: { id: number; url: string; small_url: string; alt_text: string }[]
  created_at: string
  created_by: string
  via: string
  done_at: string | null
}

export const socialApi = {
  drafts: (org: number) =>
    api.get<{ drafts: SocialDraft[]; can_manage: boolean }>(`${base(org)}social/drafts/`),
  setDraft: (org: number, id: number, data: { done: boolean }) =>
    api.put<SocialDraft>(`${base(org)}social/drafts/${id}/`, data),
  removeDraft: (org: number, id: number) => api.del(`${base(org)}social/drafts/${id}/`),

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
    api.post<SocialFeed & { created: number; queued: boolean }>(`${base(org)}social/${id}/sync/`),
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

// --- Dokumente: Pressespiegel und eigene Dokumente (Ralf 05.11.2026) ---

export type DocumentSection = 'press' | 'documents'

export interface WebsiteDocument {
  id: number
  section: DocumentSection
  title: string
  source: string
  date: string | null
  published: boolean
  kind: 'pdf' | 'image'
  size: number
  file_name: string
  url: string
  preview_url: string | null
  uploaded_at: string
}

export interface DocumentDraft {
  section?: DocumentSection
  title?: string
  source?: string
  date?: string | null
  published?: boolean
}

export const documentApi = {
  list: (org: number) => api.get<WebsiteDocument[]>(`${base(org)}documents/`),
  upload: (org: number, file: File, data: DocumentDraft) => {
    const form = new FormData()
    form.append('file', file)
    for (const [k, v] of Object.entries(data)) {
      if (v !== undefined && v !== null) form.append(k, String(v))
    }
    return api.post<WebsiteDocument>(`${base(org)}documents/`, form)
  },
  save: (org: number, id: number, data: DocumentDraft) =>
    api.patch<WebsiteDocument>(`${base(org)}documents/${id}/`, data),
  remove: (org: number, id: number) => api.del(`${base(org)}documents/${id}/`),
}
