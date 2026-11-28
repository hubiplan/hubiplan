"""Organisationseinheiten: ein Baum von Einheiten unter der Plattform.

Jede Einheit ist eine ``Organization``. Wie sie heißt (z. B. „Verein“, „Zug“),
legt sie selbst fest (``label``-Felder). Technisch gibt es noch drei Arten
(``type``): Einheiten mit eigenem Datenbereich (``federation``, ``club``) und
Untereinheiten (``unit``, früher „Abteilung“), deren Daten im Bereich der
Einheit ``organization`` liegen.
"""

from .fields import (
    DEFAULT_CHILD_LABELS,
    DEFAULT_LABELS,
    MAX_LOGO_BYTES,
    SHORT_NAME_MAX,
    WORKSPACE_MODULES,
    DatePrecision,
    FiscalYearFields,
    ShortNameMixin,
    ThemeFields,
    brand_icon_path,
    default_jubilee_years,
    default_unit_jubilee_years,
    founding_year_validators,
    homepage_image_path,
    logo_dark_path,
    logo_path,
    validate_logo,
)
from .imprint import Imprint, InstanceAddress, SocialLink, new_imprint_key
from .organization import (
    DELETION_SHORTEN_GRACE_DAYS,
    Department,
    DepartmentManager,
    DepartmentRole,
    DepartmentRoleManager,
    Organization,
)
from .platform import PlatformSettings
from .reports import CspReport, DecoyHit, HelpFeedback, HelpSearchMiss

__all__ = [
    "CspReport",
    "DEFAULT_CHILD_LABELS",
    "DEFAULT_LABELS",
    "DELETION_SHORTEN_GRACE_DAYS",
    "DatePrecision",
    "DecoyHit",
    "Department",
    "DepartmentManager",
    "DepartmentRole",
    "DepartmentRoleManager",
    "FiscalYearFields",
    "HelpFeedback",
    "HelpSearchMiss",
    "Imprint",
    "InstanceAddress",
    "MAX_LOGO_BYTES",
    "Organization",
    "PlatformSettings",
    "SHORT_NAME_MAX",
    "ShortNameMixin",
    "SocialLink",
    "ThemeFields",
    "WORKSPACE_MODULES",
    "brand_icon_path",
    "default_jubilee_years",
    "default_unit_jubilee_years",
    "founding_year_validators",
    "homepage_image_path",
    "logo_dark_path",
    "logo_path",
    "new_imprint_key",
    "validate_logo",
]
