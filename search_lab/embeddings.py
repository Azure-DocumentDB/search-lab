"""Real Azure OpenAI embeddings: persistent precharged budget, cache, no retry or redirect."""

import fcntl
import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import certifi
import httpx
from azure.identity import AzureCliCredential

from .config import API_VERSION, DIMENSIONS, MODEL, LabError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def vector(value):
    if (
        not isinstance(value, list)
        or len(value) != DIMENSIONS
        or any(type(x) not in (int, float) or not math.isfinite(x) for x in value)
        or not 0 < math.hypot(*value) < math.inf
    ):
        raise LabError("Embedding must be a finite, nonzero 1536-dimensional vector.")
    return [float(x) for x in value]


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".pending-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(value, f, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Embeddings:
    def __init__(self, config, transport=None):
        self.c = config.validate()
        self.transport = transport
        self.identity = {
            "endpoint": self.c.endpoint,
            "deployment": self.c.deployment,
            "model": MODEL,
            "version": self.c.model_version,
            "dimensions": DIMENSIONS,
            "api": API_VERSION,
        }
        self.space = digest(self.identity)
        self.root = Path(self.c.state_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def locked(self):
        with (self.root / "embedding.lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read(self):
        path = self.root / "embeddings.json"
        if not path.exists():
            return {"space": self.space, "vectors": {}}
        try:
            cache = json.loads(path.read_text())
            if cache["space"] != self.space or not isinstance(cache["vectors"], dict):
                raise ValueError
            for v in cache["vectors"].values():
                vector(v)
            return cache
        except (ValueError, KeyError, TypeError):
            raise LabError(
                "Embedding cache is incompatible or invalid; use a new state directory and database."
            ) from None

    def get(self, texts, allow_new=True):
        if not texts or len(texts) > 24 or any(not isinstance(t, str) or not 1 <= len(t) <= 600 for t in texts):
            raise LabError("Embedding batch is limited to 24 texts, each 1–600 characters.")
        with self.locked():
            cache = self.read()
            missing = list(dict.fromkeys(t for t in texts if digest(t) not in cache["vectors"]))
            if missing:
                if not allow_new:
                    raise LabError("Dataset embeddings not materialized. Run the explicit scoped --seed command first.")
                if not self.c.paid:
                    raise LabError(
                        "Uncached query: paid embeddings disabled. Enable explicit consent and bounded call cap."
                    )
                ledger = self.root / "embedding-budget.json"
                if cache["vectors"] and not ledger.exists():
                    raise LabError(
                        "Embedding cache exists without its budget ledger; restore the intact state directory."
                    )
                try:
                    used = json.loads(ledger.read_text())["attempted_calls"] if ledger.exists() else 0
                    if type(used) is not int or used < 0:
                        raise ValueError
                except (ValueError, KeyError, TypeError):
                    raise LabError("Embedding budget ledger is invalid; no call attempted.") from None
                if used >= self.c.max_calls:
                    raise LabError("Persistent embedding call cap reached. Review the ledger before raising the cap.")
                # A failed/ambiguous call still consumes budget, including process crashes. No retries.
                atomic_json(ledger, {"attempted_calls": used + 1})
                values = self.request(missing)
                for t, v in zip(missing, values, strict=True):
                    cache["vectors"][digest(t)] = vector(v)
                atomic_json(self.root / "embeddings.json", cache)
            return [cache["vectors"][digest(t)] for t in texts]

    def request(self, texts):
        credential = None
        try:
            headers = {"Content-Type": "application/json"}
            if self.c.api_key:
                headers["api-key"] = self.c.api_key
            else:
                credential = AzureCliCredential(process_timeout=10)
                headers["Authorization"] = (
                    "Bearer " + credential.get_token("https://cognitiveservices.azure.com/.default").token
                )
            url = f"{self.c.endpoint}/openai/deployments/{self.c.deployment}/embeddings"
            with httpx.Client(
                timeout=30, follow_redirects=False, trust_env=False, verify=certifi.where(), transport=self.transport
            ) as client:
                response = client.post(
                    url,
                    params={"api-version": API_VERSION},
                    headers=headers,
                    json={"input": texts, "dimensions": DIMENSIONS, "encoding_format": "float"},
                )
            if response.status_code == 429:
                retry = response.headers.get("Retry-After", "")
                if retry.isascii() and retry.isdigit() and len(retry) <= 6:
                    raise LabError(
                        f"Azure OpenAI throttled the call; no retry. Wait at least {int(retry)} seconds (Retry-After)."
                    )
                raise LabError(
                    "Azure OpenAI throttled the call; no retry. Consult provider Retry-After before another attempt."
                )
            if response.status_code != 200:
                raise LabError(
                    "Azure OpenAI request failed; no retry. Verify endpoint, deployment, permission and quota."
                )
            body = response.json()
            if body.get("model") != MODEL:
                raise LabError("Azure OpenAI returned a different model; no embeddings saved.")
            rows = sorted(body["data"], key=lambda x: x["index"])
            if [x["index"] for x in rows] != list(range(len(texts))):
                raise LabError("Azure OpenAI returned an incomplete embedding batch.")
            return [vector(x["embedding"]) for x in rows]
        except LabError:
            raise
        except Exception:
            raise LabError("Embedding request failed or returned invalid data; no retries or fallback.") from None
        finally:
            if credential:
                credential.close()
