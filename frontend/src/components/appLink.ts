// App-Link zum Verbinden der HUBIplan-App (UX-Audit 08.11., X-04).

/** Google Play-Eintrag der App (wie auf der Produktseite). */
export const APP_STORE_URL = 'https://play.google.com/store/apps/details?id=de.hubiplan.app'

/**
 * App-Link aus der QR-Adresse https://<Instanz>/app/verbinden#code=<Code>. Format mit der
 * Android-App abgestimmt: hubiplan://verbinden?server=<Origin>&code=<Code>. Ohne gültige
 * https-Adresse oder Code null.
 */
export function appPairLink(pairUrl: string): string | null {
  let url: URL
  try {
    url = new URL(pairUrl)
  } catch {
    return null
  }
  // Wie die App beim QR-Code: Wert hinter „code=“ unverändert übernehmen
  const code = url.hash
    .replace(/^#/, '')
    .split('&')
    .find((part) => part.startsWith('code='))
    ?.slice('code='.length)
  if (!code || url.protocol !== 'https:') return null
  return `hubiplan://verbinden?server=${encodeURIComponent(url.origin)}&code=${encodeURIComponent(code)}`
}
