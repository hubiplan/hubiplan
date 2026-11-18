# Kopie an den zweiten Ort (rsync über SSH); wird von backup.sh eingebunden und von
# scripts/pruefe-zweitort.sh mit einem Ersatz für rsync geprüft.
#
# BACKUP_REMOTE_ANHAENGEND=1 (Gesamtaudit 15.11., OPS-06): nie --delete übergeben. Für ein
# Ziel, das den Zugang auf „rrsync -wo -no-del“ beschränkt; dort würde --delete abgewiesen.
# Ohne den Schalter bleibt alles wie bisher: --delete, wenn backup.sh es vorgibt, und dann
# höchstens einmal am Tag ein HINWEIS in backup.log. Der Hinweis ist kein Fehler: Er ändert
# weder den Rückgabewert noch den Backup-Stand (run.sh wertet nur FEHLER aus).

# $1 Backup-Ordner, $2 Ziel (BACKUP_REMOTE), $3 "--delete" oder leer, $4 SSH-Befehl für rsync -e
zweitort_kopieren() {
    zweitort_loeschen=$3
    if [ "${BACKUP_REMOTE_ANHAENGEND:-0}" = 1 ]; then
        zweitort_loeschen=""
    elif [ -n "$zweitort_loeschen" ]; then
        zweitort_hinweis "$1"
    fi
    # shellcheck disable=SC2086 # leer oder genau eine Option
    rsync -a $zweitort_loeschen -e "$4" \
        --include='*.enc' --include='*.enc.hmac' --include='*.age' --include='*.age.hmac' \
        --include='datenschluessel_*.sha256' --include='datenschluessel_*.sha256.hmac' \
        --include='datenschluessel.sha256' --include='datenschluessel.sha256.hmac' \
        --include='*.receipt' --include='*.receipt.hmac' \
        --include='restore-test.log' --include='loeschliste.jsonl' --include='kettenkoepfe.log' \
        --exclude='*' "$1/" "$2"
}

# Höchstens einmal am Tag; Merker .zweitort-hinweis geht nicht mit an den zweiten Ort
zweitort_hinweis() {
    zweitort_heute=$(date +%F)
    [ "$(cat "$1/.zweitort-hinweis" 2>/dev/null)" != "$zweitort_heute" ] || return 0
    echo "$zweitort_heute" > "$1/.zweitort-hinweis" 2>/dev/null || true
    echo "$(date '+%F %T') HINWEIS: Zweiter Ort wird mit --delete abgeglichen; wer den Server übernimmt, kann dort auch löschen. Anhängend: BACKUP_REMOTE_ANHAENGEND=1 mit rrsync am Ziel (docs/betrieb.md)" \
        >> "$1/backup.log" 2>/dev/null || true
}
