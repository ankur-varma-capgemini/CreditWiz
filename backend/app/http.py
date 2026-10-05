"""Calls to the systems the hub reads from, in one place.

Standard library only, so the adapters add no dependency. Every call has a
timeout, and a failure becomes ExternalError naming the service and, when the
service said why, its own short reason (an AADSTS code, a Graph error). Never
the request body, a token or a person's words.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

TIMEOUT_SECONDS = 15.0


class ExternalError(Exception):
    """A connected system did not answer, or answered with an error."""

    def __init__(self, service: str, status: int | None = None, detail: str = ""):
        self.service = service
        self.status = status
        self.detail = detail
        said = f"{service} returned {status}" if status else f"{service} did not respond"
        super().__init__(f"{said}: {detail}" if detail else said)


@dataclass
class Response:
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)

    def json(self):
        return json.loads(self.text) if self.text.strip() else None


def reason(body: str) -> str:
    """The service's own one-line reason, from an Entra, Graph or GraphQL error body."""
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    if isinstance(data.get("error_description"), str):
        # Entra: "AADSTS65001: The user or administrator has not consented ... Trace ID: ..."
        return data["error_description"].split("\r\n")[0].split(" Trace ID")[0][:300]
    error = data.get("error")
    if isinstance(error, dict):
        return f"{error.get('code', '')}: {error.get('message', '')}".strip(": ")[:300]
    if isinstance(error, str):
        return error[:300]
    errors = data.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return str(errors[0].get("message", ""))[:300]
    return ""


def send(
    service: str,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body=None,
    form: dict | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> Response:
    sent = {"Accept": "application/json", "User-Agent": "mufg-ai-hub/0.1", **(headers or {})}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        sent.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        sent["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=sent, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as r:
            return Response(
                r.status,
                r.read().decode("utf-8", "replace"),
                {k.lower(): v for k, v in r.headers.items()},
            )
    except urllib.error.HTTPError as e:
        try:
            said = reason(e.read(4096).decode("utf-8", "replace"))
        except OSError:
            said = ""
        raise ExternalError(service, e.code, said) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ExternalError(service) from None
