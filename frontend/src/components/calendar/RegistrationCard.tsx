// Karte mit Überschrift im Bereich „Anmeldung“ eines Termins.
import type { ReactNode } from 'react'

export function RegistrationCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card event-card">
      <h3 className="event-card-title">{title}</h3>
      <div className="stack-sm">{children}</div>
    </section>
  )
}
