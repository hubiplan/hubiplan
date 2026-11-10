"""Mehrwortsuche und Ressourcenfreigabe mit erfundenen Daten."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core import encfields
from core.tenancy import tenant_context
from members import personsearch, views
from members.personsearch import name_ids_many
from members.views import filter_members, member_queryset

from .factories import make_member, make_org
from .test_rls import as_app_role


@pytest.mark.django_db
def test_search_decrypts_visible_emails_once_for_all_words():
    org = make_org("Suchverein")
    member = make_member(org, "Erika", "Muster", email="erika@demo.invalid")
    make_member(org, "Otto", "Anders", email="otto@demo.invalid")
    other = make_org("Fremdverein")
    make_member(other, "Fremd", "Muster", email="fremd@demo.invalid")
    original = encfields.decrypt_text
    calls = []

    def decrypt(value, field):
        if field.model._meta.label_lower == "members.contactdetails" and field.name == "email":
            calls.append(value)
        return original(value, field)

    with as_app_role(), tenant_context(org.pk), patch.object(encfields, "decrypt_text", decrypt):
        with CaptureQueriesContext(connection) as queries:
            qs = filter_members(
                member_queryset(org), {"suche": "ERIKA @demo.invalid @DEMO.invalid"}, org
            )
            assert list(qs.values_list("pk", flat=True)) == [member.pk]
        assert len(calls) == 2
        # Ohne @ keine Adresse entschlüsseln (Gesamtaudit 10.11. P01, Fachfrage 8)
        calls.clear()
        assert not filter_members(member_queryset(org), {"suche": "demo.invalid"}, org).exists()
        assert calls == []
        contact_queries = [q for q in queries if 'FROM "members_contactdetails"' in q["sql"]]
        assert len(contact_queries) == 1
        assert not filter_members(member_queryset(org), {"suche": "fremd"}, org).exists()


@pytest.mark.django_db
def test_name_search_preserves_central_unicode_case_semantics():
    org = make_org("Unicode Suchverein")
    member = make_member(org, "İpek", "Muster", email="ipek@example.invalid")
    with as_app_role(), tenant_context(org.pk):
        found = filter_members(member_queryset(org), {"suche": "İpek İPEK"}, org)
        assert list(found.values_list("pk", flat=True)) == [member.pk]


@pytest.mark.django_db
def test_name_batch_reads_and_normalizes_allowed_candidates_once_for_all_words():
    org = make_org("Zentrale Namenssuche")
    member = make_member(org, "Anna", "Müller")
    other = make_member(org, "Bernd", "Anders")
    hidden = make_member(make_org("Fremdverein"), "Anna", "Müller")
    with (
        as_app_role(),
        tenant_context(org.pk),
        patch.object(personsearch, "normalize", wraps=personsearch.normalize) as normalize,
    ):
        with CaptureQueriesContext(connection) as queries:
            matches = name_ids_many(
                member_queryset(org), ["ANNA", "Mu\u0308ller", "anders", "ANNA"]
            )
        assert matches == {"ANNA": {member.pk}, "Mu\u0308ller": {member.pk}, "anders": {other.pk}}
        # Namen sind CharFields; die Batch-Regel spart hier wiederholtes Lesen
        # und Normalisieren, keine vermeintliche Namensentschlüsselung.
        assert normalize.call_count == 7  # drei eindeutige Wörter, vier Namenswerte
        for value in ("Anna", "Müller", "Bernd", "Anders"):
            assert sum(call.args == (value,) for call in normalize.call_args_list) == 1
        assert len(queries) == 1
        assert hidden.pk not in set().union(*matches.values())


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("fails", [False, True])
def test_member_list_preserves_inherited_jit_setting_and_rls(api, orgs, board_a, fails):
    def jit():
        with connection.cursor() as cursor:
            cursor.execute("SHOW jit")
            return cursor.fetchone()[0]

    before = jit()
    original = views.member_rows
    observed = []

    def rows(page, org):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('jit'), current_setting('app.org_id'), "
                "current_setting('app.bypass_rls')"
            )
            observed.append(cursor.fetchone())
        if fails:
            raise RuntimeError("synthetic list error")
        return original(page, org)

    client = api(board_a)
    with as_app_role(), patch.object(views, "member_rows", rows):
        if fails:
            with pytest.raises(RuntimeError, match="synthetic list error"):
                client.get(f"/api/orgs/{orgs['a'].pk}/members/")
        else:
            response = client.get(f"/api/orgs/{orgs['a'].pk}/members/")
            assert response.status_code == 200, response.content
    assert observed == [(before, str(orgs["a"].pk), "off")]
    assert jit() == before


def test_warmup_closes_failing_iterable_and_main_thread_connections():
    spec = importlib.util.spec_from_file_location(
        "test_gunicorn_warmup", Path(__file__).parents[1] / "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bodies = []

    class Body:
        closed = False

        def __iter__(self):
            raise RuntimeError("synthetic iterator failure")

        def close(self):
            self.closed = True

    def app(environ, start_response):
        body = Body()
        bodies.append(body)
        return body

    with patch("django.db.connections.close_all") as close:
        module.warm_up(app, Mock())
    assert len(bodies) == len(module.WARMUP_PATHS)
    assert all(body.closed for body in bodies)
    close.assert_called_once_with()


def test_warmup_close_failure_does_not_skip_other_paths_or_connections():
    spec = importlib.util.spec_from_file_location(
        "test_gunicorn_warmup_close", Path(__file__).parents[1] / "gunicorn.conf.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    body = Mock()
    body.__iter__ = Mock(return_value=iter([b"ok"]))
    body.close.side_effect = RuntimeError("synthetic close failure")
    app = Mock(return_value=body)
    with patch("django.db.connections.close_all") as close:
        module.warm_up(app, Mock())
    assert app.call_count == len(module.WARMUP_PATHS)
    assert body.close.call_count == len(module.WARMUP_PATHS)
    close.assert_called_once_with()
