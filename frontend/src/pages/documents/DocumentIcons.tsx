/** Decorative icons: names, types and permissions are also available as text. */
export function FolderIcon({ locked = false }: { locked?: boolean }) {
  return (
    <svg
      className="doc-icon doc-icon-folder"
      viewBox="0 0 64 56"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M5 13V7h21l7 7h26v34H5Z" fill="currentColor" opacity=".6" />
      <path d="M5 19h54l-5 29H9Z" fill="currentColor" />
      {locked && (
        <g stroke="var(--color-text)" strokeWidth="2.5" fill="var(--color-surface)">
          <rect x="37" y="33" width="19" height="17" rx="3" />
          <path d="M41 33v-5a5.5 5.5 0 0 1 11 0v5" fill="none" />
          <path d="M46.5 39v5" />
        </g>
      )}
    </svg>
  )
}

export function DocumentIcon({
  name = '',
  contentType = '',
}: {
  name?: string
  contentType?: string
}) {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  const kind =
    ext === 'pdf' || contentType === 'application/pdf'
      ? 'pdf'
      : ['doc', 'docx', 'odt'].includes(ext) || /word|opendocument.text/.test(contentType)
        ? 'word'
        : ['xls', 'xlsx', 'ods', 'csv'].includes(ext) || /spreadsheet|excel|csv/.test(contentType)
          ? 'sheet'
          : ['ppt', 'pptx', 'odp'].includes(ext) || /presentation|powerpoint/.test(contentType)
            ? 'slides'
            : ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'].includes(ext) ||
                contentType.startsWith('image/')
              ? 'image'
              : 'text'
  const label = { pdf: 'PDF', word: 'DOC', sheet: 'XLS', slides: 'PPT', image: 'IMG', text: 'TXT' }[
    kind
  ]
  return (
    <svg
      className={`doc-icon doc-icon-${kind}`}
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M13 3h27l13 14v44H13Z"
        fill="var(--color-surface)"
        stroke="currentColor"
        strokeWidth="2"
      />
      <path d="M40 3v15h13" fill="none" stroke="currentColor" strokeWidth="2" />
      {kind === 'image' ? (
        <path
          d="m20 35 8-9 7 7 6-5 6 7ZM22 22h3"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
      ) : kind === 'sheet' ? (
        <path
          d="M20 24h25v12H20Zm0 6h25M28 24v12M37 24v12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
      ) : (
        <path d="M21 25h22M21 31h22M21 37h14" stroke="currentColor" strokeWidth="2" />
      )}
      <rect x="7" y="43" width="49" height="17" rx="3" fill="currentColor" />
      <text
        x="31.5"
        y="55.5"
        textAnchor="middle"
        fill="white"
        fontSize="11"
        fontFamily="sans-serif"
        fontWeight="700"
      >
        {label}
      </text>
    </svg>
  )
}
