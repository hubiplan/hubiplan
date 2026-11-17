// UX-Audit 16.11.2026: eine dauerhaft vorhandene Ansage-Region (VW-29, X-04) und Fokus in
// neu eingeblendeten Formularen (VW-43).
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { announce, prepareAnnouncements } from '../components/announce.ts'
import { useRevealFocus } from '../components/revealFocus.ts'
import { Loading } from '../components/ui.tsx'

describe('Ansage-Region', () => {
  it('steht vor der ersten Meldung und nimmt höfliche und dringende Texte', async () => {
    prepareAnnouncements()
    const polite = document.getElementById('ansage-hoeflich')!
    const urgent = document.getElementById('ansage-dringend')!
    expect(polite).toHaveAttribute('aria-live', 'polite')
    expect(urgent).toHaveAttribute('aria-live', 'assertive')
    announce('Gespeichert')
    await waitFor(() => expect(polite).toHaveTextContent('Gespeichert'))
    announce('Nicht gespeichert', true)
    await waitFor(() => expect(urgent).toHaveTextContent('Nicht gespeichert'))
    // nur eine Region je Art, auch nach mehreren Meldungen
    expect(document.querySelectorAll('#ansage-hoeflich')).toHaveLength(1)
  })

  it('sagt längeres Laden über die Region an, die Ladezeile selbst ist keine Live-Region', async () => {
    prepareAnnouncements()
    document.getElementById('ansage-hoeflich')!.textContent = ''
    render(<Loading />)
    expect(screen.getByText('Wird geladen …')).not.toHaveAttribute('aria-live')
    await waitFor(() =>
      expect(document.getElementById('ansage-hoeflich')).toHaveTextContent('Wird geladen …'),
    )
  })
})

describe('Eingeblendetes Formular', () => {
  function Form({ fresh }: { fresh: boolean }) {
    const ref = useRevealFocus<HTMLFormElement>(fresh)
    return (
      <form ref={ref}>
        <h2>Neuer Geschäftspartner</h2>
        <input type="hidden" name="x" />
        <input aria-label="Name" />
        <input aria-label="Ort" />
      </form>
    )
  }

  it('setzt den Fokus in das erste Feld', () => {
    render(<Form fresh />)
    expect(screen.getByLabelText('Name')).toHaveFocus()
  })

  it('lässt den Fokus bei einem geöffneten Datensatz, wo er ist', () => {
    render(<Form fresh={false} />)
    expect(screen.getByLabelText('Name')).not.toHaveFocus()
  })
})
