"""Operator-local UI, or explicitly IP-restricted Azure App Service hosting."""

import ipaddress
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import LabError, load_config
from .dataset import CATEGORIES, REGIONS, fixtures
from .service import Lab

STATIC = Path(__file__).parent / "static"


def hosting():
    cloud = os.environ.get("SEARCH_LAB_HOSTING", "local")
    if cloud == "local":
        return False, None, []
    host = os.environ.get("WEBSITE_HOSTNAME", "")
    ips = os.environ.get("SEARCH_LAB_OPERATOR_IPS", "")
    if (
        cloud != "appservice"
        or not re.fullmatch(r"[a-z0-9-]+\.azurewebsites\.net", host)
        or os.environ.get("SEARCH_LAB_IP_RESTRICTIONS_CONFIRMED") != "true"
        or not ips
    ):
        raise LabError("Cloud hosting requires exact Azure hostname and explicit operator-IP restriction confirmation.")
    try:
        networks = [ipaddress.ip_network(ip.strip(), strict=True) for ip in ips.split(",")]
        if any(n.prefixlen < (32 if n.version == 4 else 128) for n in networks):
            raise ValueError
    except ValueError:
        raise LabError("Use explicit single operator IP addresses, never broad networks.") from None
    return True, host, networks


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=600)
    category: Literal["outdoors", "office", "kitchen", "travel"] | None = None
    region: Literal["north", "south"] | None = None
    k: int = Field(default=3, ge=1, le=10)
    index: Literal["ivf"] = "ivf"


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: Literal["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8"]
    k: int = Field(default=3, ge=1, le=10)
    repeats: int = Field(default=3, ge=2, le=5)


def create_app(lab_factory=None):
    lock = threading.Lock()
    state = {"lab": None}
    factory = lab_factory or (lambda: Lab(load_config()))
    cloud, hostname, _networks = hosting()

    @asynccontextmanager
    async def lifespan(app):
        yield
        if state["lab"] is not None:
            state["lab"].close()

    app = FastAPI(
        title="Managed Azure DocumentDB Search Lab", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=[hostname] if cloud else ["localhost", "127.0.0.1", "[::1]"]
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        try:
            # Cloud ingress must separately enforce App Service access restrictions.
            # Do NOT trust user-supplied X-Forwarded-For; platform restrictions are the boundary.
            local = bool(request.client) and ipaddress.ip_address(request.client.host).is_loopback
        except ValueError:
            local = False
        if not cloud and not local:
            return JSONResponse({"detail": "Operator loopback access only."}, status_code=403)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            expected = f"https://{hostname}" if cloud else f"{request.url.scheme}://{request.headers.get('host', '')}"
            if (
                (origin and origin != expected)
                or request.headers.get("x-search-lab") != "same-origin"
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse({"detail": "Same-origin operator request required."}, status_code=403)
            try:
                if int(request.headers.get("content-length", "0")) > 4096:
                    raise ValueError
            except ValueError:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 4096:
                    return JSONResponse({"detail": "Request too large."}, status_code=413)
            # Cache the bounded body for downstream FastAPI validation.
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; img-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
        return response

    def run(operation):
        if not lock.acquire(blocking=False):
            raise HTTPException(429, "Another bounded operation is running; wait for it to finish.")
        try:
            if state["lab"] is None:
                state["lab"] = factory()
            return operation(state["lab"])
        except LabError as e:
            raise HTTPException(503, str(e)) from None
        except Exception:
            raise HTTPException(
                503,
                "Managed Azure request failed. Check operator configuration, permissions and index readiness; no static fallback.",
            ) from None
        finally:
            lock.release()

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    def config():
        _, queries = fixtures()
        return {
            "queries": queries,
            "categories": CATEGORIES,
            "regions": REGIONS,
            "indexes": ["ivf"],
            "operator_scope": "Operator-local or explicitly IP-restricted application; not a public service.",
        }

    @app.get("/api/status")
    def status():
        return run(lambda lab: (lab.ready(), {"ready": True, "dataset_version": lab.version})[1])

    @app.post("/api/search")
    def search(body: SearchRequest):
        if not body.text.strip():
            raise HTTPException(422, "Query must contain non-whitespace text.")
        return run(
            lambda lab: lab.search(
                body.text.strip(),
                {k: v for k, v in {"category": body.category, "region": body.region}.items() if v is not None},
                body.k,
            )
        )

    @app.post("/api/evaluate-case")
    def evaluate(body: EvaluationRequest):
        return run(lambda lab: lab.evaluate_case(body.case_id, body.k, body.repeats))

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
