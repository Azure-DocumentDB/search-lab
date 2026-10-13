"""Strict backend-only environment contract. No dotenv, endpoint overrides or TLS bypass."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


class LabError(Exception):
    """Only sanitized operator-facing messages; never wrap provider exceptions."""


HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.(?:global\.)?mongocluster\.cosmos\.azure\.com", re.ASCII)
AOAI = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.openai\.azure\.com", re.ASCII)
DATABASE = re.compile(r"searchlab_disposable_[a-z0-9_]{1,40}", re.ASCII)
COLLECTION = "catalog_v1"
DIMENSIONS = 1536
MODEL = "text-embedding-3-small"
API_VERSION = "2024-10-21"


def validate_uri(raw):
    try:
        if not raw or any(ord(x) < 33 or ord(x) == 127 for x in raw) or re.search(r"%(?![\da-fA-F]{2})", raw):
            raise ValueError
        u = urlsplit(raw)
        if (
            u.scheme != "mongodb+srv"
            or not HOST.fullmatch(u.hostname or "")
            or u.port is not None
            or u.path not in ("", "/")
            or u.fragment
            or "#" in raw
            or not u.username
            or not u.password
        ):
            raise ValueError
        for v in (unquote(u.username), unquote(u.password)):
            if not v or any(ord(x) < 32 or ord(x) == 127 for x in v):
                raise ValueError
        allowed = {
            "tls": {"true"},
            "ssl": {"true"},
            "retrywrites": {"false"},
            "authsource": {"admin"},
            "authmechanism": {"scram-sha-256"},
            "tlsinsecure": {"false"},
            "tlsallowinvalidcertificates": {"false"},
            "tlsallowinvalidhostnames": {"false"},
        }
        seen = set()
        for k, v in parse_qsl(u.query, strict_parsing=True, keep_blank_values=True):
            k = k.lower()
            if k in seen or k not in allowed or v.lower() not in allowed[k]:
                raise ValueError
            seen.add(k)
        return raw
    except (ValueError, TypeError):
        raise LabError(
            "Rejected database URI: public Azure SRV with verified TLS and native authentication required."
        ) from None


def validate_endpoint(raw):
    try:
        u = urlsplit(raw)
        if (
            u.scheme != "https"
            or not AOAI.fullmatch(u.hostname or "")
            or u.port not in (None, 443)
            or u.username
            or u.password
            or u.path not in ("", "/")
            or u.query
            or u.fragment
            or any(ord(x) < 33 for x in raw)
        ):
            raise ValueError
        return f"https://{u.hostname}"
    except (ValueError, TypeError):
        raise LabError(
            "Embedding endpoint must be a public https://RESOURCE.openai.azure.com endpoint on port 443."
        ) from None


@dataclass(frozen=True)
class Config:
    database: str
    endpoint: str = field(repr=False)
    deployment: str
    model_version: str
    auth_mode: str = "oidc"
    host: str = field(default="", repr=False)
    uri: str = field(default="", repr=False)
    username: str = field(default="", repr=False)
    api_key: str = field(default="", repr=False)
    paid: bool = False
    max_calls: int = 0
    consent: str = ""
    state_dir: Path = Path(".state")

    def validate(self, writes=False):
        if not DATABASE.fullmatch(self.database):
            raise LabError("Set an explicit MONGO_DATABASE=searchlab_disposable_RUN_ID.")
        validate_endpoint(self.endpoint)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.deployment) or self.model_version != "1":
            raise LabError("Set the text-embedding-3-small deployment and AZURE_OPENAI_MODEL_VERSION=1.")
        if self.auth_mode == "oidc":
            if not HOST.fullmatch(self.host) or self.uri or any(ord(c) < 32 for c in self.username):
                raise LabError("OIDC requires Azure MONGO_HOST and no MONGO_CONNECTION_STRING.")
        elif self.auth_mode == "connection-string":
            validate_uri(self.uri)
            if self.host or self.username:
                raise LabError("Unset OIDC host and username for native authentication.")
        else:
            raise LabError("MONGO_AUTH_MODE must be oidc or connection-string.")
        if not 0 <= self.max_calls <= 20:
            raise LabError("SEARCH_LAB_MAX_EMBEDDING_CALLS must be 0–20 (persistent lifetime cap).")
        if writes and self.consent != f"{self.database}/{COLLECTION}":
            raise LabError("Seed requires SEARCH_LAB_WRITE_CONSENT matching the exact database/catalog_v1.")
        return self


def load_config(env=None):
    e = os.environ if env is None else env
    try:
        if e.get("SEARCH_LAB_ALLOW_PAID_EMBEDDINGS", "false") not in ("true", "false"):
            raise ValueError
        c = Config(
            database=e.get("MONGO_DATABASE", ""),
            endpoint=validate_endpoint(e.get("AZURE_OPENAI_ENDPOINT", "")),
            deployment=e.get("AZURE_OPENAI_DEPLOYMENT", ""),
            model_version=e.get("AZURE_OPENAI_MODEL_VERSION", ""),
            auth_mode=e.get("MONGO_AUTH_MODE", "oidc"),
            host=e.get("MONGO_HOST", ""),
            uri=e.get("MONGO_CONNECTION_STRING", ""),
            username=e.get("MONGO_OIDC_USERNAME", ""),
            api_key=e.get("AZURE_OPENAI_API_KEY", ""),
            paid=e.get("SEARCH_LAB_ALLOW_PAID_EMBEDDINGS") == "true",
            max_calls=int(e.get("SEARCH_LAB_MAX_EMBEDDING_CALLS", "0")),
            consent=e.get("SEARCH_LAB_WRITE_CONSENT", ""),
            state_dir=Path(e.get("SEARCH_LAB_STATE_DIR", ".state")),
        )
        return c.validate()
    except (ValueError, TypeError):
        raise LabError("Invalid boolean or numeric configuration.") from None
