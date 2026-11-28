// Gemeinsame Helfer, Typen und Konstanten von SurveysPage.
import type {
  NamesMode,
  QuestionKind,
  ResultsMode,
  SurveyOption,
  SurveyQuestion,
  SurveyStatus,
} from '../../api/surveys.ts'
import { berlin } from '../../components/calendar/time.ts'
import { t } from '../../i18n/index.ts'
import './surveys.css'

export function statusLabel(status: SurveyStatus) {
  if (status === 'open') return t('läuft')
  if (status === 'closed') return t('beendet')
  return t('Entwurf')
}

export function kindLabel(kind: QuestionKind) {
  switch (kind) {
    case 'single':
      return t('Einfachauswahl')
    case 'multiple':
      return t('Mehrfachauswahl')
    case 'yesno':
      return t('Ja / Nein / Enthaltung')
    case 'dates':
      return t('Terminfindung')
    case 'quantity':
      return t('Mengenauswahl (z. B. Essen)')
    default:
      return t('Freitext')
  }
}

export function namesLabel(mode: NamesMode) {
  if (mode === 'open') return t('offen: alle Befragten sehen Namen')
  if (mode === 'anonymous') return t('anonym: niemand sieht, wer was geantwortet hat')
  return t('nur die Verwaltung sieht Namen')
}

export function resultsLabel(mode: ResultsMode) {
  if (mode === 'always') return t('immer')
  if (mode === 'after_close') return t('erst nach dem Ende')
  if (mode === 'managers') return t('nur die Verwaltung')
  return t('nach der eigenen Antwort')
}

/** Wert für ein datetime-local-Feld (deutsche Zeit) */
export function local(value: string | null) {
  if (!value) return ''
  const b = berlin(value)
  return `${b.date}T${b.time}`
}

/** datetime-local → API (wird dort als deutsche Zeit gelesen) */
export function toApiTime(value: string) {
  return value ? `${value}:00` : null
}

export function emptyOption(): SurveyOption {
  return { label: '', starts_at: null, ends_at: null, all_day: false, capacity: null }
}

export function emptyQuestion(kind: QuestionKind = 'single'): SurveyQuestion {
  const options =
    kind === 'single' || kind === 'multiple' || kind === 'dates'
      ? [emptyOption(), emptyOption()]
      : kind === 'quantity'
        ? [emptyOption()]
        : []
  return { kind, text: '', required: true, max_choices: null, allow_maybe: true, options }
}
