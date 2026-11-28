// Webseite › Menü und Seiten: Menü, Seiten, Bausteine und was Einheiten darüber und darunter zeigen.
import { hasDraft } from '../../api/website.ts'
import type { WebsiteSettings } from '../../api/website.ts'
import { Alert, Checkbox, SelectField } from '../../components/ui.tsx'
import { Why } from '../../learning/Aids.tsx'
import { DraftBar } from './DesignPreview.tsx'
import { t } from '../../i18n/index.ts'
import { NameFormats } from './NameFormats.tsx'
import { LINK, MenuTree } from './MenuTree.tsx'
import { UnitList } from './UnitList.tsx'
import { MenuPlacesField } from './MenuPlacesField.tsx'

import type { WebsiteAdminModel } from './useWebsiteAdmin.tsx'
import { type MenuItem, type MenuNode } from '../../api/website.ts'
import { normalizeMenu } from './menuTree.ts'

/** Eigene Überschrift im Menü (Ralf 05.11.): ``heading:<Nummer>``, Name in ``block_names`` */
const HEADING = /^heading:[1-9][0-9]{0,2}$/

/** Eigene Überschrift oder Link nach außen: lebt nur, solange er einen Namen hat */
const isOwn = (key: string) => HEADING.test(key) || LINK.test(key)

/** Menüpunkte vom Server plus noch nicht gespeicherte eigene Überschriften und Links;
 * gelöschte fallen weg */
function menuItems(
  items: MenuItem[],
  names: Record<string, string>,
  links: Record<string, string>,
): MenuItem[] {
  const known = new Set(items.map((it) => it.key))
  const added: MenuItem[] = Object.keys(names)
    .filter((key) => isOwn(key) && !known.has(key))
    .map((key) => ({
      key,
      label: names[key],
      default_label: '',
      renamable: true,
      hint: HEADING.test(key)
        ? t('eigene Überschrift ohne eigene Seite; Name leer lassen entfernt sie')
        : '',
      toggle: null,
      heading: HEADING.test(key),
      parent: null,
      url: links[key] ?? '',
    }))
  return [...items.filter((it) => !isOwn(it.key) || it.key in names), ...added]
}

/** Nächste freie Nummer für ``heading:`` oder ``link:`` */
function withNew(
  names: Record<string, string>,
  pattern: RegExp,
  prefix: string,
  label: string,
): Record<string, string> {
  const used = Object.keys(names)
    .filter((key) => pattern.test(key))
    .map((key) => Number(key.split(':')[1]))
  const next = Math.max(0, ...used) + 1
  return { ...names, [`${prefix}:${next}`]: label }
}

/** Ein Hauptpunkt des Menüs als Knopf (Ralf 10.11.), z. B. „Mitglied werden“ */
function MenuButtonField({
  items,
  menu,
  names,
  value,
  error,
  disabled,
  onChange,
}: {
  items: MenuItem[]
  menu: MenuNode[]
  names: Record<string, string>
  value: string
  error?: string
  disabled: boolean
  onChange: (key: string) => void
}) {
  const byKey = new Map(items.map((it) => [it.key, it]))
  // Nur einfache Hauptpunkte: keine Überschrift, kein Aufklappmenü
  const options = normalizeMenu(menu, items)
    .filter((n) => n.children.length === 0 && byKey.has(n.key) && !byKey.get(n.key)!.heading)
    .map((n) => {
      const it = byKey.get(n.key)!
      return { key: n.key, label: (it.renamable && names[n.key]?.trim()) || it.label }
    })
  return (
    <SelectField
      label={t('Menüpunkt als Knopf hervorheben')}
      hint={t(
        'Ein Hauptpunkt erscheint im Menü als farbiger Knopf, z. B. „Kontakt“ oder ein Link „Mitglied werden“. Punkte mit Unterpunkten und Überschriften gehen nicht.',
      )}
      value={options.some((o) => o.key === value) ? value : ''}
      error={error}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{t('keiner')}</option>
      {options.map((o) => (
        <option key={o.key} value={o.key}>
          {o.label}
        </option>
      ))}
    </SelectField>
  )
}

export function WebsiteStructure({ m }: { m: WebsiteAdminModel }) {
  const { data, website, onReset, reload, org, v, set, errors, auto, settings } = m
  const hasUnits = data.units.length > 0
  // Ältere Server liefern has_parent_units nicht: dann wie bisher zeigen
  const hasParents = data.has_parent_units ?? true
  return (
    <>
      {/* Lange Seite: der Hinweis steht oben und bleibt beim Scrollen unter der Kopfzeile */}
      {hasDraft(website) && (
        <DraftBar
          website={website}
          auto={auto}
          canManage={data.can_manage}
          onReset={onReset}
          sticky
        />
      )}
      {settings(
        // Ein Begriff je Sache (UX-Audit WS-15): feste Bereiche heißen „Seiten“
        t('Seiten'),
        <>
          <p className="muted small">
            {t(
              'Welche Seiten die Webseite zeigt, in der Reihenfolge des Menüs. Mit dem Stift gibst du einer Seite einen eigenen Namen für Menü und Überschrift.',
            )}
          </p>
          <p className="muted small">
            {t(
              'Reihenfolge, Namen, Links und Knopf des Menüs kommen in den Entwurf und erscheinen erst nach „Veröffentlichen“. Die Häkchen (Seite an oder aus) gelten sofort.',
            )}
          </p>
          {website.menu_items && (
            <>
              <MenuTree
                items={menuItems(website.menu_items, v.block_names ?? {}, v.menu_links ?? {})}
                value={v.menu ?? []}
                blocks={v.blocks}
                names={v.block_names ?? {}}
                links={v.menu_links ?? {}}
                button={v.menu_button ?? ''}
                disabled={!data.can_manage}
                onChange={(next) => set('menu', next)}
                onRename={(key, name) => {
                  const next = { ...(v.block_names ?? {}) }
                  // Eigene Überschrift oder Link: leer lassen entfernt sie beim Speichern
                  if (name.trim() || isOwn(key)) next[key] = name
                  else delete next[key]
                  set('block_names', next)
                }}
                onLinkUrl={(key, url) => set('menu_links', { ...(v.menu_links ?? {}), [key]: url })}
                onToggle={(key, on) => set('blocks', { ...v.blocks, [key]: on })}
              />
              {data.can_manage && (
                <div className="actions">
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() =>
                      set(
                        'block_names',
                        withNew(v.block_names ?? {}, HEADING, 'heading', t('Neue Überschrift')),
                      )
                    }
                  >
                    {t('Überschrift hinzufügen')}
                  </button>
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() =>
                      set(
                        'block_names',
                        withNew(v.block_names ?? {}, LINK, 'link', t('Neuer Link')),
                      )
                    }
                  >
                    {t('Link nach außen hinzufügen')}
                  </button>
                </div>
              )}
              {errors.menu_links && <Alert kind="error">{errors.menu_links}</Alert>}
              <MenuButtonField
                items={menuItems(website.menu_items, v.block_names ?? {}, v.menu_links ?? {})}
                menu={v.menu ?? []}
                names={v.block_names ?? {}}
                value={v.menu_button ?? ''}
                error={errors.menu_button}
                disabled={!data.can_manage}
                onChange={(key) => set('menu_button', key)}
              />
              <MenuPlacesField
                items={menuItems(website.menu_items, v.block_names ?? {}, v.menu_links ?? {})}
                menu={v.menu ?? []}
                names={v.block_names ?? {}}
                value={v.menu_places ?? {}}
                error={errors.menu_places}
                disabled={!data.can_manage}
                onChange={(next) => set('menu_places', next)}
              />
            </>
          )}
          {errors.block_names && <Alert kind="error">{errors.block_names}</Alert>}
          {Object.entries(data.block_labels)
            .filter(([key]) => !website.menu_items?.some((it) => it.toggle === key))
            .map(([key, label]) => (
              <Checkbox
                key={key}
                label={label}
                hint={data.block_hints?.[key]}
                checked={v.blocks[key] ?? true}
                onChange={(on) => set('blocks', { ...v.blocks, [key]: on })}
              />
            ))}
        </>,
      )}
      {settings(
        t('Personen'),
        <>
          <div className="grid-2">
            <SelectField
              label={t('Namensform')}
              value={v.name_format}
              onChange={(e) => set('name_format', e.target.value as WebsiteSettings['name_format'])}
            >
              <option value="full">{t('Vorname Name')}</option>
              <option value="short">{t('V. Nachname')}</option>
              <option value="initial">{t('Vorname N.')}</option>
            </SelectField>
            <SelectField
              label={t('Personen ohne Einwilligung (z. B. in der Chronik)')}
              value={v.missing_consent}
              onChange={(e) =>
                set('missing_consent', e.target.value as WebsiteSettings['missing_consent'])
              }
            >
              <option value="omit">{t('auslassen')}</option>
              <option value="nn">{t('als „N. N.“ zeigen')}</option>
            </SelectField>
          </div>
          <div className="aid-row">
            <Why k="web_names" />
            <Why k="web_consent" />
          </div>
          <NameFormats
            value={v.name_formats ?? {}}
            base={v.name_format}
            menuItems={website.menu_items}
            onChange={(next) => set('name_formats', next)}
          />
          <Checkbox
            label={t('Titel vor dem Namen nennen')}
            hint={t('z. B. „Dr. Max Muster“; Titel aus der Mitgliedsakte')}
            checked={v.show_titles ?? false}
            onChange={(on) => set('show_titles', on)}
          />
          <Checkbox
            label={t('Unbesetzte Funktionen als „derzeit unbesetzt“ zeigen')}
            checked={v.show_vacant}
            onChange={(on) => set('show_vacant', on)}
          />
          {org.modules.includes('music') && (
            <Checkbox
              label={t('Hauptinstrument unter dem Namen zeigen')}
              hint={t('aus Musik › Musiker; bei Vorstand und Mitgliederlisten')}
              checked={v.show_instrument ?? false}
              onChange={(on) => set('show_instrument', on)}
            />
          )}
          <Checkbox
            label={t('Anschrift beim Vorstand zeigen')}
            hint={t('nur bei Personen mit Einwilligung „Anschrift“')}
            checked={v.show_address ?? false}
            onChange={(on) => set('show_address', on)}
          />
          <Checkbox
            label={t('Mitgliederlisten mit Eintrittsjahr')}
            checked={v.show_member_since ?? true}
            onChange={(on) => set('show_member_since', on)}
          />
          <p className="muted small">
            {t(
              'Welche Funktionen erscheinen, legst du an den Rollen fest („auf der Webseite zeigen“). Einwilligungen und Widersprüche stehen in der Mitgliederakte unter „Veröffentlichung“.',
            )}
          </p>
        </>,
      )}
      {settings(
        t('Untereinheiten'),
        <>
          <SelectField
            label={t('Untereinheiten auf der Webseite')}
            value={v.units_mode}
            onChange={(e) => set('units_mode', e.target.value as WebsiteSettings['units_mode'])}
          >
            <option value="all">{t('alle')}</option>
            <option value="selected">{t('ausgewählte')}</option>
            <option value="none">{t('keine')}</option>
          </SelectField>
          {v.units_mode !== 'none' && (
            <UnitList
              orgId={org.id}
              units={data.units}
              sortable={!!data.can_sort_units && data.units.length > 1}
              selected={v.units_mode === 'selected' ? v.unit_ids : null}
              onSelect={(ids) => set('unit_ids', ids)}
              onReorder={reload}
            />
          )}
          {errors.unit_ids && <Alert kind="error">{errors.unit_ids}</Alert>}
        </>,
      )}
      {/* Häkchen nur, wenn es Einheiten darunter bzw. darüber gibt; sonst entfällt der Block.
          Gespeicherte Werte bleiben unverändert. */}
      {org.modules.includes('events') &&
        (hasUnits || hasParents) &&
        settings(
          t('Termine'),
          <>
            {hasUnits && (
              <Checkbox
                label={t('Öffentliche Termine der Untereinheiten im Kalender der Webseite')}
                checked={v.include_unit_events}
                onChange={(on) => set('include_unit_events', on)}
              />
            )}
            {hasParents && (
              <Checkbox
                label={t(
                  'Öffentliche Termine der übergeordneten Einheiten im Kalender der Webseite',
                )}
                hint={t('z. B. Dachverband; nur Termine, die nach unten freigegeben sind')}
                checked={v.include_parent_events}
                onChange={(on) => set('include_parent_events', on)}
              />
            )}
          </>,
        )}
      {org.modules.includes('honors') &&
        settings(
          t('Würdenträger'),
          <>
            <Checkbox
              label={t('Weitergegebene Würden der übergeordneten Einheiten zeigen')}
              hint={t('z. B. Könige des Dachverbands; nur die Träger, die aus eurer Einheit kamen')}
              checked={v.include_parent_honors}
              onChange={(on) => set('include_parent_honors', on)}
            />
          </>,
        )}
    </>
  )
}
