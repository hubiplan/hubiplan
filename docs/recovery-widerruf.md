# Sicherheitsänderungen und Wiederherstellung

Bei Passwort- und Zwei-Faktor-Änderungen erhöht HUBIplan eine kontoweite
Authentifizierungsversion. Frühere Browser-Anmeldungen, noch offene OIDC-Anmeldecodes und
OIDC-Zugriffstokens sind dadurch ungültig. Das gilt für das Konto in allen Vereinen.
Die eigene Sitzung darf beim selbst ausgeführten Passwort-/Faktorwechsel bestehen bleiben.
Beim Entfernen oder Zurücksetzen eines Faktors wird ihr früherer MFA-Nachweis entfernt;
ein alter Authentifizierungszeitpunkt ersetzt keinen neuen zweiten Faktor.

Setzt eine berechtigte zweite Person die Zwei-Faktor-Anmeldung zurück, werden alle
Browser- und App-Anmeldungen des Zielkontos widerrufen. Offene Anmelde-, E-Mail- und
App-Kopplungslinks gelten nicht mehr. Eingehende Anmeldeverknüpfungen mit Partnerinstanzen
werden entfernt. Nach der erneuten Einrichtung müssen sie bewusst neu verknüpft werden.
Noch offene lokale Peer-SSO-Faktorabfragen sind ebenfalls an die Version gebunden.
Die bestehenden Grenzen für Rücksetzungen durch einen einzelnen Verein bleiben erhalten.

Bereits offline überprüfbare OIDC-ID-Tokens bleiben beim externen Empfänger bis zu ihrem
Ablauf überprüfbar (höchstens fünf Minuten). Ausgehende, bereits ausgestellte
Peer-SSO-Bestätigungen haben eine Laufzeit von höchstens zwei Minuten. Ein sofortiger
Widerruf solcher Bestätigungen beim anderen Dienst würde ein zusätzliches
Widerrufs-/Rückfrageprotokoll benötigen. Bereits angemeldete Sitzungen bei externen
Diensten sind dort gesondert zu beenden; HUBIplan behauptet dafür keinen Sofortwiderruf.

Die Migration ergänzt die Version mit dem Datenbankstandardwert null. Vorhandene
Sitzungen und alte kurzfristige Cacheeinträge bleiben bei Version null kompatibel; nach
einer Sicherheitsänderung werden sie abgewiesen. Ein Rollback auf eine ältere
Serverfassung kann eine erneute Browser-Anmeldung erfordern.

## English

Password and second-factor changes increment an account-wide authentication version.
Older browser sessions and pending OIDC codes/access tokens then become invalid across
all clubs. An explicitly retained session for a self-service change can stay signed in.
Removing/resetting MFA clears that session's historical MFA evidence.

Administrative MFA recovery revokes the target account's browser/app sessions and pending
login, email-change and pairing links. Incoming peer sign-in links are removed and must
be explicitly reconnected after setting up MFA again. Pending local peer step-up requests
are version-bound. Existing cross-club recovery restrictions still apply.

Already signed offline-verifiable OIDC ID tokens can remain valid at an external recipient
until their expiry (up to five minutes); already issued outgoing peer assertions expire
within two minutes. Immediate revocation would require an additional protocol. Sessions
already established at external services must be ended there separately.

Version zero preserves compatibility for existing sessions and short-lived cache entries.
The additive migration has a database default of zero. Rolling back server code can
require affected users to sign in again.
