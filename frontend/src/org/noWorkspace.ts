/** Seite braucht einen anderen Arbeitsbereich: PageErrorBoundary zeigt dafür „Kein Zugriff“
 * statt eines Ladefehlers (UX-Audit 16.11. VW-09 c). */
export class NoWorkspaceError extends Error {}
