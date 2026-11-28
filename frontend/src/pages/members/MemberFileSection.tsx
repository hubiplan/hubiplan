import type { ReactNode } from 'react'

export function MemberFileSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="card card-wide">
      <h2>{title}</h2>
      {children}
    </div>
  )
}
