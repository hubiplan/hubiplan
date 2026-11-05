from core.i18n_source import untranslated_ui


def test_api_fehler_und_auswahlbeschriftungen_ohne_umlaute():
    code = """
class Status(models.TextChoices):
    OPEN = "open", "Offen"
raise ValidationError({"field": "Bitte angeben."})
return_value = Response({"detail": "Fertig.", "code": "done"})
errors["name"] = "Name fehlt."
problems.append(f"Zeile {row}: Fehler")
"""
    assert [line for line, _text in untranslated_ui(code)] == [3, 4, 5, 6, 7]


def test_technische_werte_vereinsdaten_und_angebundene_texte_bleiben_erhalten():
    code = """
class Status(models.TextChoices):
    OPEN = "open", gettext_lazy("Offen")
title = "Eigener Vereinsname"
raise ValidationError({"field": gettext("Bitte angeben.")})
value = Response({"code": "done", "detail": result})
errors["name"] = gettext("Name fehlt.")
"""
    assert untranslated_ui(code) == []
