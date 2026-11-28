import { RangePager } from '../../components/ListControls.tsx'

const PAGE_SIZE = 100

/** „1–100 von 340“ mit Blättern; nichts, wenn alles auf eine Seite passt */
export function PageNav({
  page,
  count,
  onPage,
  noun,
}: {
  page: number
  count: number
  onPage: (p: number) => void
  noun: string
}) {
  return <RangePager page={page} size={PAGE_SIZE} total={count} onPage={onPage} noun={noun} />
}
