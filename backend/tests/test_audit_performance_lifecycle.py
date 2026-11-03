"""Mehrwortsuche und Ressourcenfreigabe mit erfundenen Daten."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core import encfields
from core.tenancy import tenant_context
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
            qs = filter_members(member_queryset(org), {"suche": "ERIKA demo.invalid demo.invalid"}, org)
            assert list(qs.values_list("pk", flat=True)) == [member.pk]
        assert len(calls) == 2
        contact_queries = [q for q in queries if 'FROM "members_contactdetails"' in q["sql"]]
        assert len(contact_queries) == 1
        assert not filter_members(member_queryset(org), {"suche": "fremd"}, org).exists()


def test_warmup_closes_failing_iterable_and_main_thread_connections():
    spec = importlib.util.spec_from_file_location("test_gunicorn_warmup", Path(__file__).parents[1] / "gunicorn.conf.py")
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
    spec = importlib.util.spec_from_file_location("test_gunicorn_warmup_close", Path(__file__).parents[1] / "gunicorn.conf.py")
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
