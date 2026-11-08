// Eigene Fehlermeldungen am Feld statt Browserblasen (UX-Audit 08.11., W-08).
//
// Der Browser prüft Pflichtfelder, Mindestwerte usw. weiter selbst und hält das Absenden an.
// Seine flüchtige Blase (in der Sprache des Browsers) ersetzen wir durch einen bleibenden
// Text unter dem Feld, verknüpft über aria-describedby und mit aria-invalid. Das gilt für
// alle Formulare auf einmal, auch für Felder ohne den Baustein Field. Sobald das Feld
// gültig ist, verschwindet die Meldung wieder.
import { t } from '../i18n/index.ts'

type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement

const ATTR = 'data-feldpruefung'
let counter = 0

function isControl(el: EventTarget | null): el is Control {
  return (
    el instanceof HTMLInputElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLTextAreaElement
  )
}

/** Text der Meldung für ein ungültiges Feld, in der Sprache der Oberfläche. */
export function validityMessage(el: Control): string {
  const v = el.validity
  const type = el instanceof HTMLInputElement ? el.type : el.tagName.toLowerCase()
  if (v.customError && el.validationMessage) return el.validationMessage
  if (v.valueMissing) {
    if (type === 'select') return t('Bitte wähle etwas aus.')
    if (type === 'checkbox') return t('Bitte setze dieses Häkchen.')
    if (type === 'radio') return t('Bitte wähle eine Möglichkeit aus.')
    if (type === 'file') return t('Bitte wähle eine Datei aus.')
    return t('Bitte fülle dieses Feld aus.')
  }
  if (v.typeMismatch) {
    if (type === 'email') return t('Bitte gib eine gültige E-Mail-Adresse ein.')
    if (type === 'url')
      return t('Bitte gib eine vollständige Adresse ein, z. B. https://example.org.')
  }
  if (v.badInput) {
    if (type === 'number') return t('Bitte gib eine Zahl ein.')
    return t('Bitte gib ein gültiges Datum oder eine gültige Uhrzeit ein.')
  }
  if (v.rangeUnderflow && 'min' in el)
    return t('Der Wert muss mindestens {min} sein.', { min: el.min })
  if (v.rangeOverflow && 'max' in el)
    return t('Der Wert darf höchstens {max} sein.', { max: el.max })
  if (v.tooShort && 'minLength' in el)
    return t('Bitte gib mindestens {n} Zeichen ein.', { n: String(el.minLength) })
  if (v.tooLong && 'maxLength' in el)
    return t('Bitte gib höchstens {n} Zeichen ein.', { n: String(el.maxLength) })
  if (v.patternMismatch) return el.title || t('Bitte prüfe das Format dieser Eingabe.')
  if (v.stepMismatch) return t('Dieser Wert passt nicht, bitte prüfe ihn.')
  return t('Bitte prüfe diese Eingabe.')
}

/** Wohin die Meldung kommt: hinter das Feld oder, wenn es in einer Beschriftung steckt, dahinter. */
function anchorOf(el: Control): Element {
  return el.closest('label') ?? el
}

function describedBy(el: Control, id: string, add: boolean) {
  const ids = (el.getAttribute('aria-describedby') ?? '').split(/\s+/).filter((x) => x && x !== id)
  if (add) ids.push(id)
  if (ids.length) el.setAttribute('aria-describedby', ids.join(' '))
  else el.removeAttribute('aria-describedby')
}

function noteFor(el: Control): HTMLElement | null {
  const id = el.getAttribute(ATTR)
  return id ? document.getElementById(id) : null
}

export function showFieldError(el: Control) {
  const text = validityMessage(el)
  let note = noteFor(el)
  if (!note) {
    const id = `feldpruefung-${++counter}`
    note = document.createElement('small')
    note.id = id
    note.className = 'field-error field-check'
    note.setAttribute(ATTR, '')
    anchorOf(el).insertAdjacentElement('afterend', note)
    el.setAttribute(ATTR, id)
    describedBy(el, id, true)
  }
  if (note.textContent !== text) note.textContent = text
  el.setAttribute('aria-invalid', 'true')
}

export function clearFieldError(el: Control) {
  const note = noteFor(el)
  const id = el.getAttribute(ATTR)
  if (!id) return
  note?.remove()
  el.removeAttribute(ATTR)
  describedBy(el, id, false)
  // Felder des Bausteins Field zeigen eigene Fehler; deren Markierung bleibt
  if (!el.closest('.field-invalid')) el.setAttribute('aria-invalid', 'false')
}

let focusedThisRound = false

function onInvalid(e: Event) {
  if (!isControl(e.target)) return
  const el = e.target
  // Keine Browserblase; das Absenden hält der Browser trotzdem an
  e.preventDefault()
  showFieldError(el)
  // Der Browser fokussiert ohne Blase nicht mehr: erstes ungültiges Feld selbst ansteuern
  if (!focusedThisRound) {
    focusedThisRound = true
    el.focus()
    setTimeout(() => {
      focusedThisRound = false
    }, 0)
  }
}

function onEdit(e: Event) {
  if (!isControl(e.target)) return
  const el = e.target
  if (!el.hasAttribute(ATTR)) return
  if (el.validity.valid) clearFieldError(el)
  else showFieldError(el)
  // Optionsfelder einer Gruppe teilen sich die Pflicht
  if (el instanceof HTMLInputElement && el.type === 'radio' && el.name && el.form) {
    for (const other of Array.from(el.form.querySelectorAll<HTMLInputElement>(`input[type=radio]`)))
      if (other.name === el.name && other.validity.valid) clearFieldError(other)
  }
}

let watching = false

/** Einmal beim Start: gilt für alle Formulare der Oberfläche. */
export function watchFormValidation(doc: Document = document) {
  if (watching) return
  watching = true
  doc.addEventListener('invalid', onInvalid, true)
  doc.addEventListener('input', onEdit, true)
  doc.addEventListener('change', onEdit, true)
}
