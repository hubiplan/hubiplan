import { describe, expect, it } from 'vitest'
import { conditionalTranslationKeys, untranslatedUi } from '../../scripts/i18n-source.mjs'

describe('Nicht angebundene sichtbare Texte', () => {
  it('katalogprüft jeden statischen Zweig eines dynamischen Schlüssels', async () => {
    expect(
      await conditionalTranslationKeys(
        "const text = t(on ? 'An' : mode ? 'Aus' : 'Unbekannt')",
        'probe.ts',
      ),
    ).toEqual([{ line: 1, keys: ['An', 'Aus', 'Unbekannt'] }])
    expect(await conditionalTranslationKeys("t(on ? title : 'Aus')", 'probe.ts')).toEqual([])
  })
  it('prüft direkte Ausdrücke, Parameter und dynamische Beschriftungstabellen', async () => {
    const hits = await untranslatedUi(
      `const CHANNEL_LABEL = { mail: 'Brief', get app() { return t('App') } }; const v = <p>{'Hinweis'} {t('Wert: {x}', {x: on ? 'ja' : 'nein'})}</p>`,
      'probe.tsx',
    )
    expect(hits.map((h) => h.text).sort()).toEqual(['Brief', 'Hinweis', 'ja', 'nein'].sort())
  })
  it('verwechselt Callback-Variablen, Enum-Werte und Entitäten nicht mit Text', async () => {
    expect(
      await untranslatedUi(
        `const OPTIONS = [{value:'day', label:t('Tag')}]; const v = <p>&nbsp;{items.map(item => { const cls = on ? 'active' : 'muted'; return <span className={cls}>{item.name}</span> })}</p>`,
        'probe.tsx',
      ),
    ).toEqual([])
  })
  it('erlaubt geprüfte Ausnahmen nur am benannten Ort', async () => {
    const source = '<p>Sprache / Language</p>'
    expect(await untranslatedUi(source, 'i18n/LanguageControls.tsx')).toEqual([])
    expect(await untranslatedUi(source, 'anderer-ort.tsx')).toHaveLength(1)
  })
  it('findet auch Überschriften ohne Umlaute und Aktionsbeschriftungen bei gefülltem Katalog', async () => {
    const hits = await untranslatedUi(
      `const view = <section><h1>Meldungen</h1><Field label="Titel" /><button>{busy ? 'Bitte warten' : 'Anlegen'}</button></section>`,
      'probe.tsx',
    )
    expect(hits.map((hit) => hit.text).sort()).toEqual(
      ['Meldungen', 'Titel', 'Bitte warten', 'Anlegen'].sort(),
    )
  })
  it('lässt Daten, technische Attribute und übersetzte Texte unangetastet', async () => {
    expect(
      await untranslatedUi(
        `const view = <section className="card stack"><h1>{call.title}</h1><button aria-label={t('Öffnen')}>{tn('{n} Eintrag', '{n} Einträge', n)}</button><a href="/meldungen">PDF</a></section>`,
        'probe.tsx',
      ),
    ).toEqual([])
  })
})
