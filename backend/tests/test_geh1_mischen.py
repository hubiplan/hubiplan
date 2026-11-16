"""Anonyme Antworten nicht über xmin oder Reihenfolge zuordenbar (Gesamtaudit 15.11., GEH-1).

Teilnahme (mit Mitgliedschaft) und Antwort entstehen in derselben Transaktion und tragen dieselbe
Transaktionsnummer; wer die Datenbank oder eine Sicherung lesen kann, ordnete so jede anonyme
Antwort ihrer Person zu. Jetzt mischt HUBIplan die Antworten offener anonymer Umfragen stündlich
und beim Schließen; das Ergebnis erscheint erst nach dem Schließen. Erfundene Daten.
"""
# ruff: noqa: F811  (Fixtures als Parameter)

import pytest
from django.db import connection, connections

from core.tenancy import rls_bypass
from surveys import services
from surveys.models import Survey, SurveyAnswer

from .test_umfragen import JSON, answer, new_survey, ok, setup, start  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def ohne_broker(settings):
    # Mit echten Transaktionen laufen on_commit-Aufgaben (Bescheid beim Start); ohne Broker
    # im Testaufbau gleich im Prozess ausführen
    settings.CELERY_TASK_ALWAYS_EAGER = True


YESNO = {"kind": "yesno", "text": "Neue Uniformjacken bestellen?"}


def _xmin_matches(survey_id: int) -> int:
    """Zuordnung wie im Bericht: Antwort und Teilnahme mit derselben Transaktionsnummer."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM surveys_surveyparticipation p JOIN surveys_surveyanswer a "
            "ON a.xmin = p.xmin AND a.survey_id = p.survey_id WHERE p.survey_id = %s",
            [survey_id],
        )
        return cursor.fetchone()[0]


def _vote(s, survey, votes):
    client, url = s["portals"]["Anna"]
    q = ok(client.get(url))["surveys"][0]["questions"][0]
    for who, value in votes.items():
        answer(s, who, survey, [{"question": q["id"], "value": value}])


def test_mischen_trennt_antwort_und_teilnahme(setup):
    s = setup
    survey = new_survey(s, [YESNO], names="anonymous", results="after_close")
    start(s, survey)
    _vote(s, survey, {"Anna": "yes", "Bernd": "no", "Carla": "yes", "Dieter": "yes"})
    with rls_bypass():
        # Vorher: alle vier Stimmen zuordenbar
        assert _xmin_matches(survey["id"]) == 4
        obj = Survey.objects.get(pk=survey["id"])
        before = services.result_data(obj, with_names=False)
        assert before["hidden"]  # noch offen: auch die Verwaltung sieht nichts
    assert services.mix_open() == 1
    with rls_bypass():
        assert _xmin_matches(survey["id"]) == 0
        assert SurveyAnswer.objects.filter(survey_id=survey["id"]).count() == 4


def test_zaehlung_vor_und_nach_dem_mischen_gleich(setup):
    s = setup
    survey = new_survey(s, [YESNO], names="anonymous", results="after_close")
    start(s, survey)
    _vote(s, survey, {"Anna": "yes", "Bernd": "no", "Carla": "yes"})
    with rls_bypass():
        obj = Survey.objects.get(pk=survey["id"])
        obj.status = Survey.Status.CLOSED  # nur zum Vergleich der Zählung, ohne Mischen
        before = services.result_data(obj, with_names=False)
        obj.status = Survey.Status.OPEN
        services.mix_answers(obj)
        obj.status = Survey.Status.CLOSED
        after = services.result_data(obj, with_names=False)
    assert before == after
    assert before["questions"][0]["values"]["yes"]["count"] == 2


def test_stimme_zwischen_lesen_und_loeschen_bleibt(setup):
    """Absicherung, falls ein Aufrufer die Umfrage einmal nicht sperrt: Nur die gelesenen Zeilen
    werden neu geschrieben, eine dazwischen gespeicherte Stimme bleibt."""
    from unittest import mock

    s = setup
    survey = new_survey(s, [YESNO], names="anonymous", results="after_close")
    start(s, survey)
    _vote(s, survey, {"Anna": "yes", "Bernd": "no"})
    with rls_bypass():
        obj = Survey.objects.get(pk=survey["id"])
        late = SurveyAnswer.objects.filter(survey=obj).first()
        real_shuffle = services.random.SystemRandom.shuffle

        def shuffle_and_vote(self, rows):
            real_shuffle(self, rows)
            SurveyAnswer.objects.create(
                organization_id=obj.organization_id,
                survey=obj,
                question_id=late.question_id,
                value="yes",
            )

        with mock.patch.object(services.random.SystemRandom, "shuffle", shuffle_and_vote):
            assert services.mix_answers(obj) == 2
        assert SurveyAnswer.objects.filter(survey=obj).count() == 3
        assert SurveyAnswer.objects.filter(survey=obj, value="yes").count() == 2


def test_ergebnis_erst_nach_schliessen_und_mischen(setup):
    s = setup
    survey = new_survey(s, [YESNO], names="anonymous", results="after_close")
    start(s, survey)
    _vote(s, survey, {"Anna": "yes", "Bernd": "no", "Carla": "yes"})
    ok(s["chef"].post(f"{s['url']}{survey['id']}/close/"))
    with rls_bypass():
        assert _xmin_matches(survey["id"]) == 0
    full = ok(s["chef"].get(f"{s['url']}{survey['id']}/"))
    assert full["result"]["questions"][0]["values"]["yes"]["count"] == 2


def test_gesperrte_umfrage_wartet_bis_zum_naechsten_lauf(setup):
    """Stimmt gerade jemand ab (Umfrage gesperrt), überspringt der Stundenlauf sie."""
    s = setup
    survey = new_survey(s, [YESNO], names="anonymous", results="after_close")
    start(s, survey)
    _vote(s, survey, {"Anna": "yes", "Bernd": "no"})
    other = connections.create_connection("default")
    try:
        other.set_autocommit(False)
        with other.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
            cursor.execute("SELECT id FROM surveys_survey WHERE id = %s FOR UPDATE", [survey["id"]])
        assert services.mix_open() == 0
        with rls_bypass():
            assert _xmin_matches(survey["id"]) == 2
    finally:
        other.rollback()
        other.close()
    assert services.mix_open() == 1


def test_umfragen_mit_namen_bleiben_unberuehrt(setup):
    s = setup
    survey = new_survey(s, [YESNO])
    start(s, survey)
    _vote(s, survey, {"Anna": "yes"})
    with rls_bypass():
        ids = set(SurveyAnswer.objects.filter(survey_id=survey["id"]).values_list("pk", flat=True))
    assert services.mix_open() == 0
    with rls_bypass():
        assert (
            set(SurveyAnswer.objects.filter(survey_id=survey["id"]).values_list("pk", flat=True))
            == ids
        )
