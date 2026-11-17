# Beitragsnachweise (Ermäßigung mit Nachweis)

App `backend/feeproofs`, gehört zum Modul Beiträge (`billing`, Vereine und Dachverbände mit
Mitgliedern). Seite `/mitglieder/beitragsnachweise`, Einrichtung unter Finanzen ›
Beitragssätze, am Mitglied die Karte „Ermäßigung mit Nachweis“, im Mitgliederbereich und in
den Apps „Beitragsnachweise“, persönlicher Link `/nachweis/<Geheimnis>`.

Gedacht für Regeln wie: „Der Nachweis ist mit dem Aufnahmeantrag und anschließend jährlich
unaufgefordert bis spätestens 28. Februar des Beitragsjahres vorzulegen. Wird er nicht
fristgerecht erbracht, gilt für das laufende Beitragsjahr der reguläre Beitrag.“

Rechte: einrichten mit `billing.edit`; sehen mit `members.view`; zuordnen, prüfen und
eintragen mit `members.edit`. Die Kasse sieht den Stand in der Vorschau des Beitragslaufs.

## Begriffe

- **Ermäßigung mit Nachweis** (`ProofDiscount`): ermäßigter Jahresbeitrag (Betrag) oder
  Abschlag in Prozent, optional nur für eine Mitgliedsart. Dazu Frist (Tag und Monat im
  Beitragsjahr, Vorgabe 28.02.), optionale Kulanzzeit in Tagen, Frist für später Eintretende
  (Vorgabe 28 Tage nach Beginn), Erinnerungen (Vorgabe 15.01. und 14 Tage vor der Frist),
  Mitteilung nach Fristablauf (an/aus) und die Arten von Nachweisen, die zählen.
- **Zuordnung** (`DiscountAssignment`): Mitglied hat die Ermäßigung von … bis … . Die
  Mitgliedsart bleibt dabei unverändert. Endet die Voraussetzung, trägt der Vorstand das Ende
  ein (z. B. 31.12., „endet mit Ablauf des Kalenderjahres“).
- **Nachweis** (`FeeProof`): je Mitglied, Ermäßigung und Beitragsjahr; Stand eingegangen,
  Rückfrage, anerkannt, abgelehnt. Weg: Mitgliederbereich, App, persönlicher Link, Antwort per
  Mail, Mitgliedsantrag oder vom Vorstand eingetragen (auch ohne Datei als Einsichtsvermerk).

Das Beitragsjahr ist das Geschäftsjahr des Vereins.

## Was zählt

Ein Nachweis zählt für ein Jahr, wenn er zwischen dem 01.10. des Vorjahres (bzw. 92 Tage vor
Beginn des Beitragsjahres) und der Frist samt Kulanzzeit eingeht und am Tag des Eingangs oder
zu Beginn des Beitragsjahres gültig ist. Später eingereichte Nachweise werden angenommen und
als „nach der Frist“ markiert; ob sie zählen, entscheidet der Vorstand.

Stand je Mitglied und Jahr: `accepted` (Ermäßigung gilt), `pending` (eingereicht, noch nicht
geprüft: Ermäßigung gilt vorläufig), `question`, `open` (Frist läuft: Ermäßigung gilt
vorläufig), `missing` (Frist samt Kulanz vorbei, kein anerkannter Nachweis: normaler Beitrag).

## Ablauf

1. **Erinnerung**: täglich um 9:40 und 17:40 Uhr prüft eine Hintergrundaufgabe, wer noch
   keinen Nachweis hat, und schickt die erste und zweite Erinnerung sowie nach Fristablauf
   die Mitteilung „normaler Beitrag“. Jede Mail enthält einen persönlichen Link und, wenn das
   Rechnungspostfach eingerichtet ist, eine Antwortadresse `…+nw<Schlüssel>@…`: Wer einfach
   antwortet und die Bescheinigung anhängt, hat eingereicht.
2. **Vorprüfung** (nur ein Hinweis): bei PDF mit Text Name, Geburtsdatum, Semester bzw.
   „gültig bis“ und eine elektronische Signatur; Ampel grün, gelb, rot mit Gründen und einem
   Vorschlag für „gültig bis“. Fotos sind immer gelb.
3. **Prüfen** unter Mitglieder › Beitragsnachweise: Datei ansehen, anerkennen (mit „gültig
   bis“), ablehnen (mit Grund) oder Rückfrage. Das Mitglied bekommt eine Mail. Nach der
   Entscheidung wird die Datei gelöscht; es bleibt nur der Vermerk. Optional (Einstellung je
   Verein, Vorgabe aus) werden grüne Nachweise innerhalb der Frist automatisch anerkannt.
4. **Beitragslauf**: Ermäßigung gilt bei `accepted`, `pending` und `open`; bei `missing` wird
   der normale Beitrag berechnet, mit dem Hinweis „kein Nachweis bis …, normaler Beitrag“ in
   der Rechnungszeile. Die Vorschau zählt „normaler Beitrag mangels Nachweis“, „vorläufig
   ermäßigt“ und „ungeprüfte Nachweise“. Ein späterer Nachweis ändert bereits erstellte
   Rechnungen nicht.
5. **Zu erledigen**: „{n} Nachweise prüfen“ und, wenn zwei Beitragsjahre hintereinander kein
   Nachweis kam, „Ermäßigung beenden?“ (Liste `?stand=zwei-jahre`).

## Mitgliedsantrag

Ist mindestens eine Ermäßigung eingerichtet, bietet das Online-Formular sie an (nur Personen,
passend zur Mitgliedsart). Den Nachweis lädt man auf der Seite des Antrags hoch (höchstens drei
Dateien) oder reicht ihn nach; dann gelten ab Aufnahme die Tage für später Eintretende. Bei der
Aufnahme wird die Ermäßigung ab dem Eintrittstag zugeordnet; hochgeladene Dateien werden
Nachweise für das Beitragsjahr des Eintritts.

## Aufbewahrung

Dateien bis zur Entscheidung (unentschiedene höchstens ein Jahr), persönliche Links bis zum
Ablauf, Erinnerungsvermerke drei Jahre. Der Vermerk (wer, wann, gültig bis, Entscheidung)
bleibt wie die übrigen Mitgliedsdaten. Auskunft enthält `beitragsnachweise.json`.

## Schnittstelle

Verein (`/api/orgs/<id>/`):

- `fee-proofs/discounts/` (GET, POST, PATCH, DELETE; DELETE gibt 409, wenn in Gebrauch)
- `fee-proofs/settings/` (`auto_accept`, `mail_replies`)
- `fee-proofs/?status=open|received|question|accepted|rejected|all&year=`
- `fee-proofs/overview/?year=` bzw. `?stand=zwei-jahre`
- `fee-proofs/<id>/file/` (GET), `fee-proofs/<id>/decide/` (POST `action` accept|reject|question,
  `valid_until`, `kind`, `note`), `fee-proofs/<id>/` (DELETE)
- `members/<id>/fee-discounts/` (Zuordnungen), `members/<id>/fee-proofs/` (GET Stand und
  Nachweise, POST mehrteilig `discount`, `year`, `received_on`, `kind`, `valid_until`,
  `accept`, `file` optional)

Mitgliederbereich und Apps: `GET/POST /api/portal/<Zugang>/fee-proofs/` (POST mehrteilig
`discount`, `year`, `file`, `kind`, `note`). Antwort: `states` (je offenes Jahr: Ermäßigung,
Arten, Frist `due`, letzter Tag `final`, Stand, letzter Nachweis) und `proofs`.

Persönlicher Link: `GET/POST /api/public/fee-proof/<Geheimnis>/`. Mitgliedsantrag:
`POST /api/public/join/application/<Geheimnis>/fee-proof/`.

Dateien: PDF, JPEG, PNG, WebP, HEIC bis 10 MB, mit Virenprüfung.
