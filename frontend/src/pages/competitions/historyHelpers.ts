// Wettbewerbe Schritt 4: Auszeichnungen einrichten, vergebene Titel und Würdenvorschläge,
// Reihen mit Archiv und Bestenliste, Wanderpokale mit Inhabern.
// Diese Datei: gemeinsame Helfer, Typen und Konstanten des Bereichs.
import { type Grant } from '../../api/competitionHistory.ts'
import { t } from '../../i18n/index.ts'

export function grantLine(g: Grant): string {
  const parts = [g.full_title || g.trophy_name]
  if (g.scoring_name && !g.title) parts.push(g.scoring_name)
  if (g.place) parts.push(t('Platz {n}', { n: g.place }))
  return parts.filter(Boolean).join(' · ')
}
