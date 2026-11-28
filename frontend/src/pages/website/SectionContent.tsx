// Abschnitt bearbeiten (Startseite und Textseiten): das Formular zur Art des Abschnitts. Die
// Formulare stehen nach Thema in drei Dateien; die Tabelle unten ordnet jede Art einer zu. Eine
// Art ohne Eintrag hat kein Formular.
import type { ComponentType } from 'react'
import type { SectionContentProps } from './sectionContentShared.tsx'
import { SectionContentText } from './SectionContentText.tsx'
import { SectionContentLists } from './SectionContentLists.tsx'
import { SectionContentClub } from './SectionContentClub.tsx'

const FORM: Record<string, ComponentType<SectionContentProps>> = {
  // Texte, Bilder und Gestaltung
  text: SectionContentText,
  text_image: SectionContentText,
  cover: SectionContentText,
  banner: SectionContentText,
  buttons: SectionContentText,
  tiles: SectionContentText,
  quote: SectionContentText,
  divider: SectionContentText,
  columns: SectionContentText,
  callout: SectionContentText,
  accordion: SectionContentText,
  images: SectionContentText,
  video: SectionContentText,
  table: SectionContentText,
  // Listen und Angaben des Vereins
  contacts: SectionContentLists,
  faq: SectionContentLists,
  partners: SectionContentLists,
  directions: SectionContentLists,
  facts: SectionContentLists,
  countdown: SectionContentLists,
  join: SectionContentLists,
  donation: SectionContentLists,
  hours: SectionContentLists,
  timeline: SectionContentLists,
  program: SectionContentLists,
  downloads: SectionContentLists,
  app: SectionContentLists,
  // Inhalte, die HUBIplan selbst liefert
  event: SectionContentClub,
  album: SectionContentClub,
  event_list: SectionContentClub,
  document: SectionContentClub,
  chronicle: SectionContentClub,
  unit_honors: SectionContentClub,
  competition: SectionContentClub,
  albums: SectionContentClub,
  posts: SectionContentClub,
  live_facts: SectionContentClub,
}

export function SectionContent(props: SectionContentProps) {
  const Form = FORM[props.section.kind ?? '']
  return Form ? <Form {...props} /> : null
}
