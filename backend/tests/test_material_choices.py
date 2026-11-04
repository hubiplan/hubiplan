import pytest

from .factories import make_member
from .test_materials import material_setup as material_setup

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("query", ["phi", " PHI ", "beisp"])
def test_member_search_matches_name_fragments(material_setup, query):
    org, _, client, base = material_setup
    member = make_member(org, "Philomena", "Beispiel")
    make_member(org, "Erika", "Mustermann")
    response = client.get(base + "choices/", {"kind": "member", "q": query})
    assert response.status_code == 200, response.content
    assert response.json() == {
        "items": [{"id": member.pk, "title": "Beispiel, Philomena"}],
        "more": False,
    }
