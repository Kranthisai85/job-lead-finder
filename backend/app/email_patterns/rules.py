from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class NameParts:
    first: str
    last: str

    @property
    def first_initial(self) -> str:
        return self.first[:1]

    @property
    def last_initial(self) -> str:
        return self.last[:1] if self.last else ""


PatternBuilder = Callable[[NameParts, str], str | None]


@dataclass(frozen=True)
class PatternRule:
    pattern_name: str
    template: str
    builder: PatternBuilder
    base_confidence: float


def _firstname(parts: NameParts, domain: str) -> str | None:
    if not parts.first:
        return None
    return f"{parts.first}@{domain}"


def _lastname(parts: NameParts, domain: str) -> str | None:
    if not parts.last:
        return None
    return f"{parts.last}@{domain}"


def _first_dot_last(parts: NameParts, domain: str) -> str | None:
    if not parts.first or not parts.last:
        return None
    return f"{parts.first}.{parts.last}@{domain}"


def _first_underscore_last(parts: NameParts, domain: str) -> str | None:
    if not parts.first or not parts.last:
        return None
    return f"{parts.first}_{parts.last}@{domain}"


def _firstlast(parts: NameParts, domain: str) -> str | None:
    if not parts.first or not parts.last:
        return None
    return f"{parts.first}{parts.last}@{domain}"


def _flast(parts: NameParts, domain: str) -> str | None:
    if not parts.first or not parts.last:
        return None
    return f"{parts.first_initial}{parts.last}@{domain}"


def _firstl(parts: NameParts, domain: str) -> str | None:
    if not parts.first or not parts.last:
        return None
    return f"{parts.first}{parts.last_initial}@{domain}"


def _f_dot_lastname(parts: NameParts, domain: str) -> str | None:
    if not parts.first or not parts.last:
        return None
    return f"{parts.first_initial}.{parts.last}@{domain}"


def _initial_dot_lastname(parts: NameParts, domain: str) -> str | None:
    return _f_dot_lastname(parts, domain)


PATTERN_RULES: tuple[PatternRule, ...] = (
    PatternRule("firstname", "firstname@", _firstname, 0.55),
    PatternRule("lastname", "lastname@", _lastname, 0.5),
    PatternRule("first.last", "first.last@", _first_dot_last, 0.7),
    PatternRule("first_last", "first_last@", _first_underscore_last, 0.6),
    PatternRule("firstlast", "firstlast@", _firstlast, 0.65),
    PatternRule("flast", "flast@", _flast, 0.68),
    PatternRule("firstl", "firstl@", _firstl, 0.58),
    PatternRule("f.lastname", "f.lastname@", _f_dot_lastname, 0.72),
    PatternRule("initial.lastname", "initial.lastname@", _initial_dot_lastname, 0.72),
)

GENERIC_LOCAL_PARTS = {
    "support",
    "hello",
    "contact",
    "admin",
    "info",
    "jobs",
    "careers",
    "team",
    "sales",
    "hr",
    "marketing",
}


def normalize_name_token(value: str | None) -> str:
    if not value:
        return ""
    cleaned = "".join(char for char in value.strip().lower() if char.isalnum())
    return cleaned


def split_contact_name(
    *,
    full_name: str | None,
    first_name: str | None,
    last_name: str | None,
) -> NameParts | None:
    first = normalize_name_token(first_name)
    last = normalize_name_token(last_name)

    if not first and full_name:
        tokens = [normalize_name_token(token) for token in full_name.split()]
        tokens = [token for token in tokens if token]
        if len(tokens) == 1:
            first = tokens[0]
        elif len(tokens) >= 2:
            first = tokens[0]
            last = tokens[-1]

    if not first:
        return None
    return NameParts(first=first, last=last)
