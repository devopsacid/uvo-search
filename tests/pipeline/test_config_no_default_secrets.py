"""No settings class may carry a usable credential as its default value.

A weak default means a misconfigured deployment starts successfully with a
guessable password instead of failing loudly. Credentials must come from the
environment or the process must not start.

Note: this inspects the *default values* of the Pydantic fields rather than the
class source text. Scanning the source would false-positive on field *names*
like ``neo4j_password``, which are legitimate; what must never appear is a
usable credential on the right-hand side.
"""

import pytest
from pydantic_core import PydanticUndefined

from uvo_api.config import ApiSettings
from uvo_pipeline.config import PipelineSettings

FORBIDDEN = ("changeme", "secret123", "admin", "hunter2")


@pytest.mark.parametrize("settings_cls", [PipelineSettings, ApiSettings])
def test_no_weak_credential_defaults(settings_cls):
    for name, field in settings_cls.model_fields.items():
        default = field.default
        if default is PydanticUndefined or not isinstance(default, str):
            continue
        lowered = default.lower()
        for token in FORBIDDEN:
            assert token not in lowered, (
                f"{settings_cls.__name__}.{name} defaults to {default!r}, which "
                f"contains the weak credential {token!r}; credentials must be "
                "supplied via the environment"
            )


@pytest.mark.parametrize(
    ("settings_cls", "field_name"),
    [
        (PipelineSettings, "mongodb_uri"),
        (PipelineSettings, "neo4j_password"),
        (ApiSettings, "mongodb_uri"),
    ],
)
def test_credential_fields_are_required(settings_cls, field_name):
    """A credential-bearing field must have no default at all, so a missing
    environment variable raises ValidationError instead of starting weak."""
    field = settings_cls.model_fields[field_name]
    assert field.default is PydanticUndefined and field.default_factory is None, (
        f"{settings_cls.__name__}.{field_name} has a default; it must be required "
        "so that a missing value aborts startup"
    )


def test_compose_has_no_weak_defaults():
    with open("docker-compose.yml", encoding="utf-8") as fh:
        compose = fh.read()
    assert ":-changeme" not in compose, (
        "docker-compose.yml uses ${VAR:-changeme}; use ${VAR:?message} so an "
        "unset variable aborts startup instead of yielding a known password"
    )
