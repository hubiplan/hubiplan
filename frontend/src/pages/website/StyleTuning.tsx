// Webseite › Feinabstimmung (Ralf 10.11.2026, Konzept webseite-baukasten G1; neu gegliedert
// 14.11.2026; übersichtlich nach Bereichen 16.11.2026, Konzept feinabstimmung-uebersichtlich):
// feste Stufen statt CSS. Links eine Leiste mit den Bereichen der Webseite (von oben nach unten),
// rechts die Regler des gewählten Bereichs mit Zwischenüberschriften. Zuerst stehen die
// wichtigsten Regler, der Rest unter „Weitere Einstellungen“. Verstellte Regler sind markiert
// und gezählt; was gerade nicht greift oder das Design festlegt, bleibt ausgegraut sichtbar und
// sagt, warum. Die Suche findet immer alle Regler. Auf dem Handy erst die Liste, dann der Bereich.
// Stufen, Sperren, Vorgaben und Voreinstellungen kommen aus HUBIplan (website/style.py),
// die Darstellungen der Bereiche aus website/variants.py; die Namen stehen hier.
import { useState, type ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { t } from '../../i18n/index.ts'
import { Sketch } from './AreaLayouts.tsx'
import { styleIcon } from './StyleIcons.tsx'
import { type Area, type Part } from './styleTuningHelpers.ts'
import { BASE, DEPENDS } from './styleTuningCatalog.ts'
import { useStyleTuning, type StyleTuningProps } from './useStyleTuning.ts'

/** Hinweis am Regler, wenn die Wahl schwer lesbar ist (UX-Audit WS-15) */
function readabilityWarning(key: string, value: unknown): string | null {
  if (key === 'heading_font' && value === 'fraktur')
    return t(
      'Fraktur ist für viele schwer lesbar. Am besten nur für kurze Überschriften verwenden, nicht für Namen oder Termine.',
    )
  if (key === 'script_greeting' && value === true)
    return t(
      'Schmuckschrift ist schwer lesbar. Die Begrüßung sollte dann kurz sein, längere Texte besser in der normalen Schrift.',
    )
  if (key === 'buttons' && value === 'label')
    return t(
      'Als Etikett stehen Knöpfe in kleinen Großbuchstaben. Das ist schwerer zu lesen; kurze Knopftexte helfen.',
    )
  return null
}

/** Eigene Schriftfolge (#526): Text mit Komma, übernommen beim Verlassen oder mit Enter. */
function FontStackInput({
  labelledBy,
  value,
  onCommit,
}: {
  labelledBy: string
  value: string
  onCommit: (next: string) => void
}) {
  // Der Aufrufer setzt key={value}: ein neuer Wert von außen beginnt mit frischem Text
  const [text, setText] = useState(value)
  function commit() {
    const next = text
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .join(', ')
    if (next !== value) onCommit(next)
    else setText(value)
  }
  return (
    <input
      type="text"
      className="style-fonts"
      aria-labelledby={labelledBy}
      value={text}
      maxLength={300}
      placeholder={t('z. B. Lucida Sans, Segoe UI, Arial')}
      spellCheck={false}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          commit()
        }
      }}
    />
  )
}

export function StyleTuning(props: StyleTuningProps) {
  const { catalog, designLabel, value, headerImage, onUndo } = props
  const {
    moved,
    presets,
    layoutValue,
    layoutByArea,
    defaults,
    query,
    setQuery,
    showAll,
    openMore,
    setOpenMore,
    openHint,
    setOpenHint,
    notice,
    setNotice,
    rowByKey,
    placed,
    known,
    labelOf,
    switchValue,
    effective,
    own,
    locked,
    wholeLocked,
    lockedHint,
    why,
    setKey,
    resetKeys,
    applyPreset,
    toggleShowAll,
    optionLabel,
    jumpTo,
    changedKeys,
    changed,
    countIn,
    current,
    showChanged,
    isIndex,
    q,
    matches,
  } = useStyleTuning(props)

  // --- Darstellung eines Reglers -------------------------------------------------------------
  function renderControl(key: string, labelId: string): ReactNode {
    if (key.startsWith('layout:')) {
      const areaKey = key.slice(7)
      const variants = layoutByArea[areaKey]?.variants ?? []
      const chosen = layoutValue[areaKey] ?? variants[0]?.key
      return (
        <div
          className={`style-segments style-n${variants.length} style-sketches`}
          role="group"
          aria-labelledby={labelId}
        >
          {variants.map((variant, i) => (
            <button
              key={variant.key}
              type="button"
              aria-pressed={chosen === variant.key}
              className={['has-icon', i === 0 ? 'is-default' : ''].filter(Boolean).join(' ')}
              onClick={() => setKey(key, variant.key)}
            >
              <Sketch id={`${areaKey}:${variant.key}`} />
              <span>{variant.label}</span>
              {i === 0 && <span className="style-default-dot" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )
    }
    const row = rowByKey[key]
    const options = catalog.options[key]
    if (options === 'fonts')
      return (
        <FontStackInput
          key={String(value[key] ?? '')}
          labelledBy={labelId}
          value={typeof value[key] === 'string' ? String(value[key]) : ''}
          onCommit={(next) => setKey(key, next || null)}
        />
      )
    if (options === 'switch')
      return (
        <label className="style-switch">
          <input
            type="checkbox"
            role="switch"
            aria-labelledby={labelId}
            checked={switchValue(value, key)}
            onChange={(e) => setKey(key, e.target.checked)}
          />
          <span aria-hidden="true">{switchValue(value, key) ? t('an') : t('aus')}</span>
          {!own(key) && <small className="muted">{t('wie das Design')}</small>}
        </label>
      )
    if (options.length > 5)
      return (
        <select
          className="style-select"
          aria-labelledby={labelId}
          value={typeof value[key] === 'string' ? String(value[key]) : ''}
          onChange={(e) => setKey(key, e.target.value || null)}
        >
          <option value="">
            {typeof defaults[key] === 'string'
              ? `${t('wie das Design')} (${row.options?.[String(defaults[key])] ?? defaults[key]})`
              : t('wie das Design')}
          </option>
          {options.map((option) => (
            <option key={option} value={option} disabled={locked(key, option)}>
              {row.options?.[option] ?? option}
            </option>
          ))}
        </select>
      )
    return (
      <div
        className={`style-segments style-n${options.length}`}
        role="group"
        aria-labelledby={labelId}
      >
        {options.map((option) => {
          const on = value[key] === option
          const off = locked(key, option)
          const isDefault = defaults[key] === option
          const icon = styleIcon(key, option)
          return (
            <button
              key={option}
              type="button"
              aria-pressed={on}
              disabled={off}
              className={[isDefault ? 'is-default' : '', icon ? 'has-icon' : '']
                .filter(Boolean)
                .join(' ')}
              title={
                off
                  ? lockedHint
                  : isDefault
                    ? t('So zeigt es das Design „{design}“.', { design: designLabel })
                    : undefined
              }
              onClick={() => setKey(key, on ? null : option)}
            >
              {icon}
              <span>{row.options?.[option] ?? option}</span>
              {isDefault && <span className="style-default-dot" aria-hidden="true" />}
            </button>
          )
        })}
      </div>
    )
  }

  function renderRow(key: string, context?: string): ReactNode {
    const row = rowByKey[key]
    const id = `style-${key.replace(':', '-')}`
    const label = labelOf(key)
    const reason = why(key)
    const isLocked = wholeLocked(key)
    const mine = own(key)
    const hint = row?.hint
    const hintOpen = !!openHint[key]
    return (
      <div
        key={key}
        id={`style-row-${key}`}
        className={[
          'style-row',
          DEPENDS[key] ? 'is-dependent' : '',
          mine ? 'is-changed' : '',
          reason || isLocked ? 'is-unavailable' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <span className="style-label">
          <span className="style-label-line">
            <span id={id}>{label}</span>
            {hint && !reason && !isLocked && (
              <button
                type="button"
                className="style-info"
                aria-expanded={hintOpen}
                aria-label={t('Erklärung zu „{label}“', { label })}
                onClick={() => setOpenHint((o) => ({ ...o, [key]: !hintOpen }))}
              >
                i
              </button>
            )}
          </span>
          {context && <small className="muted">{context}</small>}
          {hint && hintOpen && <small className="muted style-hint">{hint}</small>}
        </span>
        <div className="style-control">
          {isLocked ? (
            <span className="muted small">
              {lockedHint} <Link to="/webseite/gestaltung">{t('Design wechseln')}</Link>
            </span>
          ) : reason ? (
            <span className="muted small">
              {reason.text}{' '}
              {reason.jump && (
                <button type="button" className="link-button" onClick={() => jumpTo(reason.jump!)}>
                  {t('Hin')}
                </button>
              )}
              {reason.link && <Link to={reason.link.to}>{reason.link.label}</Link>}
            </span>
          ) : (
            renderControl(key, id)
          )}
          {mine && (
            <button
              type="button"
              className="style-reset"
              aria-label={t('{label} zurücksetzen', { label })}
              title={t('Zurück auf das Design')}
              onClick={() => setKey(key, null)}
            >
              ↺
            </button>
          )}
        </div>
        {!isLocked && !reason && readabilityWarning(key, effective(key)) && (
          <p className="style-extra style-warn small" role="note">
            {readabilityWarning(key, effective(key))}
          </p>
        )}
        {key === 'header_bg' &&
          !isLocked &&
          (value.header_bg === 'image' || value.header_bg === undefined) && (
            <div className="style-extra">{headerImage}</div>
          )}
      </div>
    )
  }

  function renderPart(inArea: Area, part: Part): ReactNode {
    const id = `${inArea.id}/${part.id}`
    const slots = part.slots.filter((x) => known(x.key))
    const lockedHere = slots.filter((x) => wholeLocked(x.key))
    const usable = slots.filter((x) => !wholeLocked(x.key))
    const basic = usable.filter((x) => !x.more || own(x.key) || showAll)
    const more = usable.filter((x) => !basic.includes(x))
    if (usable.length === 0 && lockedHere.length === 0) return null
    const partChanged = slots.filter((x) => own(x.key)).length
    const moreOpen = !!openMore[id]
    const headingId = `style-part-${inArea.id}-${part.id}`
    return (
      <section key={part.id} className="style-part" aria-labelledby={headingId}>
        <div className="style-part-head">
          <h3 id={headingId}>{part.title}</h3>
          {partChanged > 0 && (
            <button
              type="button"
              className="link-button style-part-reset"
              onClick={() =>
                resetKeys(
                  slots.map((x) => x.key),
                  t('„{part}“ zurückgesetzt.', { part: part.title }),
                )
              }
            >
              ↺ {t('{n} verstellt', { n: partChanged })}
            </button>
          )}
        </div>
        {basic.map((x) => renderRow(x.key))}
        {more.length > 0 && (
          <>
            <button
              type="button"
              className="style-more"
              aria-expanded={moreOpen}
              onClick={() => setOpenMore((o) => ({ ...o, [id]: !moreOpen }))}
            >
              {moreOpen ? '▾' : '▸'} {t('Weitere Einstellungen ({n})', { n: more.length })}
              {!moreOpen && (
                <span className="muted">: {more.map((x) => labelOf(x.key)).join(', ')}</span>
              )}
            </button>
            {moreOpen && more.map((x) => renderRow(x.key))}
          </>
        )}
        {lockedHere.length > 0 && (
          <p className="muted small style-locked">
            {t('Legt das Design „{design}“ selbst fest: {list}.', {
              design: designLabel,
              list: lockedHere.map((x) => labelOf(x.key)).join(', '),
            })}{' '}
            <Link to="/webseite/gestaltung">{t('Design wechseln')}</Link>
          </p>
        )}
      </section>
    )
  }

  // --- Inhalt rechts ---------------------------------------------------------------------------
  function renderSearch(): ReactNode {
    const hits = placed.list.filter((x) => known(x.slot.key) && matches(x.slot.key, x.part, x.area))
    const movedHits = moved.filter((m) => m.label.toLowerCase().includes(q))
    return (
      <div className="style-results">
        {hits.map((x) => renderRow(x.slot.key, `${x.area.title} › ${x.part.title}`))}
        {movedHits.map((m) => (
          <div key={m.key} className="style-row is-unavailable">
            <span className="style-label">{m.label}</span>
            <span className="muted small">
              {t('Steht jetzt unter {where}.', { where: m.where })}{' '}
              <Link to={m.to}>{t('Hin')}</Link>
            </span>
          </div>
        ))}
        {hits.length === 0 && movedHits.length === 0 && (
          <p className="muted">{t('Kein Regler gefunden.')}</p>
        )}
      </div>
    )
  }

  function renderChanged(): ReactNode {
    return (
      <>
        <div className="style-area-head">
          <h2>{t('Verstellte Regler')}</h2>
        </div>
        {changed === 0 ? (
          <p className="muted">{t('Nichts verstellt. Alles zeigt, was das Design vorsieht.')}</p>
        ) : (
          <ul className="style-changed-list" aria-label={t('Verstellte Regler')}>
            {placed.list
              .filter((x) => known(x.slot.key) && own(x.slot.key))
              .map((x) => {
                const key = x.slot.key
                const v = key.startsWith('layout:') ? layoutValue[key.slice(7)] : value[key]
                return (
                  <li key={key} className="style-chip-item">
                    <Link
                      className="style-chip"
                      to={`${BASE}/${x.area.id}`}
                      onClick={() => jumpTo(key)}
                    >
                      {x.area.title} › {labelOf(key)}: <strong>{optionLabel(key, v)}</strong>
                    </Link>
                    <button
                      type="button"
                      className="style-chip-x"
                      aria-label={t('{label} zurücksetzen', { label: labelOf(key) })}
                      onClick={() => setKey(key, null)}
                    >
                      ×
                    </button>
                  </li>
                )
              })}
          </ul>
        )}
      </>
    )
  }

  function renderStart(): ReactNode {
    const presetNames = Object.keys(catalog.presets ?? {}).filter((n) => n in presets)
    return (
      <>
        <div className="style-area-head">
          <h2>{t('Schnellstart')}</h2>
        </div>
        <p className="muted small">
          {t(
            'Ohne eigene Wahl zeigt die Webseite, was das Design „{design}“ vorsieht; diese Stufe ist mit einem Punkt markiert. Links stehen die Bereiche der Webseite von oben nach unten.',
            { design: designLabel },
          )}{' '}
          <Link to="/webseite/gestaltung">{t('Design wechseln')}</Link>
        </p>
        {presetNames.length > 0 && (
          <section className="style-part" aria-labelledby="style-presets-label">
            <div className="style-part-head">
              <h3 id="style-presets-label">{t('Voreinstellungen')}</h3>
            </div>
            <p className="muted small">
              {t('Setzt mehrere Regler auf einmal; danach bleibt alles einzeln änderbar.')}
            </p>
            <div className="style-presets" role="group" aria-labelledby="style-presets-label">
              {presetNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  className="style-preset"
                  onClick={() => applyPreset(name)}
                >
                  <strong>{presets[name].label}</strong>
                  <small className="muted">{presets[name].hint}</small>
                </button>
              ))}
            </div>
          </section>
        )}
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            disabled={changed === 0}
            onClick={() => resetKeys(changedKeys, t('Alles zurückgesetzt.'))}
          >
            {t('Alles zurücksetzen')}
          </button>
          <span className="muted small">
            {changed === 0
              ? t('Alles wie das Design.')
              : t('{n} Regler verstellt.', { n: changed })}
          </span>
        </div>
      </>
    )
  }

  function renderArea(a: Area): ReactNode {
    const n = countIn(a)
    const parts = a.parts.map((p) => renderPart(a, p)).filter(Boolean)
    return (
      <>
        <div className="style-area-head">
          <h2>{a.title}</h2>
          {n > 0 && (
            <button
              type="button"
              className="link-button"
              onClick={() =>
                resetKeys(
                  a.parts.flatMap((p) => p.slots.map((x) => x.key)),
                  t('Bereich „{area}“ zurückgesetzt.', { area: a.title }),
                )
              }
            >
              ↺ {t('Bereich zurücksetzen')}
            </button>
          )}
        </div>
        {parts.length > 0 ? (
          parts
        ) : (
          <p className="muted">{t('Hier gibt es auf diesem Server nichts einzustellen.')}</p>
        )}
      </>
    )
  }

  const navLink = (id: string, label: string, icon: string, count: number) => (
    <li key={id}>
      <NavLink
        to={`${BASE}/${id}`}
        className={({ isActive }) =>
          `style-nav-link${isActive || (id === 'schnellstart' && isIndex) ? ' active' : ''}`
        }
        onClick={() => setQuery('')}
      >
        <span className="style-nav-icon" aria-hidden="true">
          {icon}
        </span>
        <span>{label}</span>
        {count > 0 && (
          <span className="style-nav-count" aria-label={t('{n} verstellt', { n: count })}>
            {count}
          </span>
        )}
      </NavLink>
    </li>
  )

  return (
    <div className="style-tuning" data-index={isIndex ? '' : undefined}>
      <nav className="style-nav" aria-label={t('Bereiche der Feinabstimmung')}>
        <ul>
          {navLink('schnellstart', t('Schnellstart'), '★', 0)}
          {placed.areas.map((a) => navLink(a.id, a.title, a.icon, countIn(a)))}
          {navLink('verstellt', t('Nur Verstelltes'), '●', changed)}
        </ul>
      </nav>
      <div className="style-main">
        <Link className="style-back" to={BASE}>
          ‹ {t('Alle Bereiche')}
        </Link>
        <div className="style-tools">
          <label className="style-search">
            <span className="sr-only">{t('Regler suchen')}</span>
            <input
              type="search"
              placeholder={t('Regler suchen, z. B. Wappen oder Handy')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label className="style-switch style-show-all">
            <input
              type="checkbox"
              role="switch"
              checked={showAll}
              onChange={(e) => toggleShowAll(e.target.checked)}
            />
            <span>{t('Alle Regler zeigen')}</span>
          </label>
        </div>
        {notice && (
          <div className="style-notice" role="status">
            <span>{notice}</span>
            {onUndo && (
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setNotice(null)
                  onUndo()
                }}
              >
                {t('Rückgängig')}
              </button>
            )}
          </div>
        )}
        {q
          ? renderSearch()
          : showChanged
            ? renderChanged()
            : current
              ? renderArea(current)
              : renderStart()}
      </div>
    </div>
  )
}
