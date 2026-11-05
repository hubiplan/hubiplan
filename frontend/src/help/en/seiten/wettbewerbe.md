---
key: page.competitions
titel: Competitions
bereich: wettbewerbe
modul: competitions
rechte: [competitions.manage, competitions.results]
routen: [/wettbewerbe, /wettbewerbe/statistik]
stichworte: [shooting, bird shooting, ranking, shoot-off, result]
---

## Statistics

Open **Competitions** › **Statistics** for participation, achievements and performance across
all members. Select a member for their personal statistics. The same view is available in
the member file under **Competitions**. The member area shows only your own data under
**My results**.

Filter by year, competition type and scoring conditions. Average rings, rings per counted
shot and best results refer to the same recorded conditions. Different conditions have
separate averages; select a row to see the corresponding progress. Averages include the
number of valid results. The overall view also shows the equally weighted average of
personal member averages.

Only final results count. Missing values are not zero. Each person counts once per
competition; wins and podium finishes count per individual standing. Team achievements
are not counted as personal wins. Chart values are also available as a table. Expand
**All starts and awards** to see ongoing competitions as well.

Here you set up your own shooting competitions with individual and team scoring, record results and decide ties in a shoot-off. Bird shooting with prizes and external competitions where you only enter your places also belong here. Provisional results only become fixed when marked final.

Stand mode stores private data for the verified account or complete stand credential, for at most twelve hours and never beyond the credential's expiry. Without reception, the same stand remains available in the same browser tab. An explicit server access denial ends offline access. Signing out or switching accounts removes this browser's stand cache. Send outstanding entries before signing out; signing out asks before discarding them. Revoked or expired access also removes unsent entries. The old cache without account binding is removed on first opening this version; a notice appears if it contained unsent entries. Browser storage does not replace a backup.

### Names on the website

Under **Setup** → **Extent on the website**, **prize places with names** publishes
individual places up to the number of **prize places** configured for each scoring.
Two prize places show places 1 and 2; five prize places show places 1 to 5.
This also applies to the results block on the home page and to external competitions.
The results page shows the latest published competition directly;
older competitions can be opened through links.
Zero prize places show no individual places. Tied prize places are shown in full;
existing consent and objections still apply. Unit and team rankings remain visible.

### Personal results for connected clubs

Under **Evaluation** → **Result approval for connected clubs**, administrators with both
competition and peering management rights may explicitly assign otherwise unassigned
guest starters to an active downstream connection. Changes are audited and also
possible after completion; scores and places stay unchanged. An empty selection
revokes the local assignment. A starter already assigned to a unit uses that stable
assignment. Club names alone never authorize personal result sharing. The connection
must also allow the own-starters packet. Changes propagate on the next peering sync;
already received copies cannot reliably be recalled remotely.

Name lists use a fixed alphabetical order: accented letters are placed with their base letter. Identical names keep their relative order when paging through the list.

Live tables show an error and **Reload** even when the first request fails. Previously loaded rankings remain visible with a notice identifying the earlier state until updating succeeds.
