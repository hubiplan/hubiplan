// Bildschirmfotos der Hilfe (src/help/bilder.json) mit Playwright, je Sprache einmal.
// Aufruf nur über scripts/hilfe-bilder.sh (startet Backend und Oberfläche mit Demodaten).
//
//   BASE_URL=http://web:5173 DEMO_PASSWORD=… OUT=/out node scripts/hilfe-bilder.mjs [name …]
import { mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { chromium } from 'playwright'

const base = process.env.BASE_URL ?? 'http://localhost:5173'
const password = process.env.DEMO_PASSWORD
const out = process.env.OUT ?? new URL('../public/hilfe-bilder', import.meta.url).pathname
if (!password) throw new Error('DEMO_PASSWORD fehlt')
const spec = JSON.parse(readFileSync(new URL('../src/help/bilder.json', import.meta.url), 'utf8'))
const only = new Set(process.argv.slice(2))
const images = spec.bilder.filter((b) => !only.size || only.has(b.name))

const MAX_HOEHE = 900
const browser = await chromium.launch()
let failed = 0
for (const language of ['de', 'en']) {
  mkdirSync(join(out, language), { recursive: true })
  const byUser = Map.groupBy(images, (b) => b.zugang)
  for (const [user, list] of byUser) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 860 },
      deviceScaleFactor: 1,
      colorScheme: 'light',
      reducedMotion: 'reduce',
      locale: language === 'en' ? 'en-GB' : 'de-DE',
    })
    const page = await context.newPage()
    await page.goto(`${base}/anmelden`)
    await page.locator('input[autocomplete="username"]').fill(user)
    await page.locator('input[autocomplete="current-password"]').fill(password)
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL((u) => !u.pathname.startsWith('/anmelden'))
    // Sprache am Konto setzen; der Server stellt das Cookie passend ein
    const status = await page.evaluate(async (code) => {
      const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? ''
      const r = await fetch('/api/me/language/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ language: code }),
      })
      return r.status
    }, language)
    if (status !== 200) throw new Error(`Sprache ${language} nicht wählbar (HTTP ${status})`)
    for (const b of list) {
      const file = join(out, language, `${b.name}.png`)
      try {
        await page.goto(`${base}${b.seite}`)
        await page.waitForLoadState('networkidle')
        if (b.name === 'mitteilungen-lesen') {
          await page
            .getByRole('button', { name: 'Einladung zur Mitgliederversammlung', exact: true })
            .click()
          const heading = page.getByRole('heading', {
            name: 'Einladung zur Mitgliederversammlung',
            exact: true,
          })
          await heading.waitFor()
          const initial = new URL(page.url())
          const contexts = await (await page.request.get(`${base}/api/me/contexts/`)).json()
          const access = contexts.portal[0].id
          initial.searchParams.set('zugang', String(access))
          const target = initial.pathname + initial.search
          // Neue Browsersitzung: normale Anmeldung muss beide Zielparameter erhalten.
          await context.clearCookies()
          await page.goto(`${base}${target}`)
          await page.locator('input[autocomplete="username"]').fill(user)
          await page.locator('input[autocomplete="current-password"]').fill(password)
          await page.locator('button[type="submit"]').first().click()
          await heading.waitFor()
          await page.waitForLoadState('networkidle')
          if (new URL(page.url()).search !== initial.search)
            throw new Error('Rundschreibenziel nach Anmeldung verloren')
          if (!(await heading.evaluate((el) => document.activeElement === el)))
            throw new Error('Schreiben erhält keinen Fokus')
          const attachment = page.getByRole('link', { name: 'Einladung.pdf', exact: true })
          const response = await page.request.get(
            new URL(await attachment.getAttribute('href'), base).href,
          )
          if (
            response.status() !== 200 ||
            !(await response.body()).toString('ascii').startsWith('%PDF-')
          )
            throw new Error('Gewählter Anhang nicht erreichbar')
          await page.setViewportSize({ width: 320, height: 720 })
          if (
            !(await page
              .locator('main .card-wide')
              .evaluate((el) => el.scrollWidth <= el.clientWidth))
          )
            throw new Error('Schreiben läuft bei 320px über')
          await page.setViewportSize({ width: 1280, height: 860 })
          console.log(
            `${language}: App-Ziel → Browseranmeldung → richtiges Schreiben → PDF; Fokus und 320px geprüft`,
          )
        }
        if (b.name === 'beitragslauf' || b.name === 'rolle-anlegen') {
          if (b.name === 'beitragslauf')
            await page
              .getByRole('button', {
                name: language === 'en' ? 'New fee run' : 'Neuer Beitragslauf',
                exact: true,
              })
              .waitFor()
          else
            await page
              .getByRole('heading', { name: language === 'en' ? 'Roles' : 'Rollen', exact: true })
              .first()
              .waitFor()
          console.log(
            `${language}: Verwaltungsansicht ${b.name} mit übersetzter Systemüberschrift geladen`,
          )
          if (b.name === 'beitragslauf' && language === 'en') {
            const text = await page.locator('main').innerText()
            if (text.includes('Züge') || !/\bplatoons\b/i.test(text))
              throw new Error(`Englische Bezeichnung der Untereinheiten fehlt: ${text}`)
          }
        }
        if (b.name === 'kalender-kontext') {
          await page
            .getByRole('button', { name: language === 'en' ? 'Month' : 'Monat', exact: true })
            .click()
          const continuation = page.getByRole('button', {
            name:
              language === 'en'
                ? /Nachtwanderung.*Continued until 01:05/
                : /Nachtwanderung.*Fortsetzung bis 01:05/,
          })
          await continuation.waitFor()
          const names = await page
            .locator('.calendar-day .event-item')
            .filter({ hasText: 'Übungsabend' })
            .allTextContents()
          if (names.length < 2 || new Set(names).size < 2)
            throw new Error('Kalenderkontext der gleichnamigen Termine fehlt')
          await continuation.focus()
          await page.keyboard.press('Enter')
          const dialog = page.getByRole('dialog')
          await dialog.waitFor()
          await page.keyboard.press('Escape')
          await dialog.waitFor({ state: 'detached' })
          if (!(await continuation.evaluate((el) => document.activeElement === el)))
            throw new Error('Kalender verliert Rückfokus')
          await page.setViewportSize({ width: 320, height: 720 })
          await page
            .getByRole('button', { name: language === 'en' ? 'List' : 'Liste', exact: true })
            .click()
          await page
            .locator('.calendar-list .event-item')
            .filter({ hasText: 'Nachtwanderung' })
            .waitFor()
          const fits = await page.locator('.calendar-list').evaluate(
            (el) =>
              el.scrollWidth <= el.clientWidth &&
              [...el.querySelectorAll('.event-item')].every((item) => {
                const box = item.getBoundingClientRect()
                return box.left >= 0 && box.right <= document.documentElement.clientWidth
              }),
          )
          if (!fits) throw new Error('Kalenderliste läuft bei 320 CSS-Pixeln über')
          await page.screenshot({
            path: join(out, language, 'kalender-kontext-mobil.png'),
            fullPage: true,
          })
          await page.setViewportSize({ width: 1280, height: 860 })
          await page
            .getByRole('button', { name: language === 'en' ? 'Month' : 'Monat', exact: true })
            .click()
          await continuation.waitFor()
        }
        if (b.name === 'mitglieder-aufnehmen-details') {
          await page.getByLabel('Name', { exact: true }).fill('Muster')
          await page
            .getByLabel(language === 'en' ? 'First name' : 'Vorname', { exact: true })
            .fill('Erika')
          await page
            .getByLabel(language === 'en' ? 'Date of birth' : 'Geburtsdatum', { exact: true })
            .fill('1980-05-17')
          await page
            .getByRole('button', { name: language === 'en' ? 'Next' : 'Weiter', exact: true })
            .click()
          const heading = page.getByRole('heading', {
            name: language === 'en' ? '2. Membership and contact' : '2. Mitgliedschaft und Kontakt',
            exact: true,
          })
          await heading.waitFor()
          if (!(await heading.evaluate((el) => document.activeElement === el)))
            throw new Error('Die zweite Aufnahmestufe erhält keinen Tastaturfokus')
        }
        await page
          .locator('main [role="status"]', { hasText: /Lädt|Loading/ })
          .waitFor({ state: 'detached' })
          .catch(() => {})
        // wurzel: Bereich außerhalb des Inhalts, etwa die Kopfleiste (Standard: main)
        const root = b.wurzel ?? 'main'
        const target = page.locator(b.ausschnitt ? `${root} ${b.ausschnitt}` : root).first()
        await target.waitFor({ state: 'visible', timeout: 15000 })
        // Organisationsanzeigen dieser Bilder müssen aus dem erfundenen Screenshot-Bestand stammen.
        const requiredNames =
          b.name === 'modul-einschalten'
            ? ['Dachverband Musterstadt', 'Schützenverein Beispieldorf']
            : b.name === 'dokument-hochladen'
              ? ['Schützenverein Beispieldorf']
              : []
        const visibleText = await target.innerText()
        for (const name of requiredNames) {
          if (!visibleText.includes(name)) throw new Error('Erfundene Organisationsanzeige fehlt')
        }
        // Hinweise mit Datum (z. B. Frist für die Zwei-Faktor-Anmeldung) veralten im Bild
        await page.addStyleTag({
          content: 'main.content > .alert[role="status"] { display: none !important; }',
        })
        // Ausschnitt aus der ganzen Seite: so liegt die feste Kopfleiste nicht über dem
        // Bild, lange Seiten werden nach MAX_HOEHE abgeschnitten, leerer Rand unten fehlt
        const clip = await target.evaluate((el, maxHeight) => {
          window.scrollTo(0, 0)
          const box = el.getBoundingClientRect()
          let bottom = box.top
          for (const child of el.children) {
            const r = child.getBoundingClientRect()
            if (r.height) bottom = Math.max(bottom, r.bottom)
          }
          const padding = el.tagName === 'MAIN' ? 24 : 0
          bottom = el.tagName === 'MAIN' ? bottom + padding : box.bottom
          return {
            x: Math.max(0, box.left),
            y: Math.max(0, box.top),
            width: box.width,
            height: Math.min(bottom - box.top, maxHeight),
          }
        }, MAX_HOEHE)
        await page.screenshot({
          path: file,
          clip,
          fullPage: true,
          animations: 'disabled',
          caret: 'hide',
        })
        console.log(`${language}/${b.name}.png`)
      } catch (err) {
        failed++
        console.error(`FEHLER ${language}/${b.name}: ${err.message.split('\n')[0]}`)
      }
    }
    // Sprache zurück auf Deutsch, damit der Demozugang so bleibt wie vorher
    await page.evaluate(async () => {
      const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? ''
      await fetch('/api/me/language/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ language: 'de' }),
      })
    })
    await context.close()
  }
}
await browser.close()
if (failed) {
  console.error(`${failed} Bild(er) fehlgeschlagen`)
  process.exit(1)
}
