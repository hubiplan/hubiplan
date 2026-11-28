// Gemeinsame Helfer, Typen und Konstanten von SocialPage.

export function hostOf(uri: string): string {
  try {
    return new URL(uri).host
  } catch {
    return ''
  }
}
