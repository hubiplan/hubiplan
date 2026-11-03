"""Validation shared by the full import paths (including module tables)."""

from django.core.validators import URLValidator
from django.db import models


def validate_urls(obj):
    """Do not let bulk restoration bypass the URL policy of ordinary forms."""
    validate = URLValidator(schemes=["http", "https"])
    for field in obj._meta.concrete_fields:
        if isinstance(field, models.URLField):
            value = getattr(obj, field.attname)
            if value:
                field.run_validators(value)
                validate(value)


def validate_url_data(model, data):
    """Use the identical policy in the read-only preview, before any file writes."""
    fields = [field for field in model._meta.concrete_fields if isinstance(field, models.URLField)]
    if not fields:
        return
    obj = model()
    for field in fields:
        if field.name in data:
            setattr(obj, field.attname, field.to_python(data[field.name]))
    validate_urls(obj)
