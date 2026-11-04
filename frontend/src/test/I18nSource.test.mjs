import { describe, expect, it } from 'vitest'
import { untranslatedUi } from '../../scripts/i18n-source.mjs'

describe('Nicht angebundene sichtbare Texte', () => {
  it('findet auch Überschriften ohne Umlaute und Aktionsbeschriftungen bei gefülltem Katalog', async () => {
    const hits = await untranslatedUi(
      `const view = <section><h1>Meldungen</h1><Field label="Titel" /><button>{busy ? 'Bitte warten' : 'Anlegen'}</button></section>`,
      'probe.tsx',
    )
    expect(hits.map((hit) => hit.text)).toEqual(['Meldungen', 'Titel', 'Bitte warten', 'Anlegen'])
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
