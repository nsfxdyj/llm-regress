# src/llm_regress/github_api.py
"""Minimal GitHub REST client for the ``comment`` command.

stdlib-only (urllib) — zero new dependencies. All HTTP goes through the
single ``GitHubAPI._request`` method so tests can monkeypatch it; no test
ever touches the network.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMMENT_MARKER = "<!-- llm-regress-comment -->"

API_VERSION = "2022-11-28"


class GitHubAPIError(Exception):
    """Non-2xx response (or transport failure, status 0) from GitHub."""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"GitHub API error {status}: {body[:500]}")


class GitHubAPI:
    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict | None = None) -> Any:
        """One HTTP call. Monkeypatch this seam in tests.

        Non-2xx responses surface as :class:`GitHubAPIError` (urllib raises
        ``HTTPError`` for them); DNS/TLS failures surface as status 0.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", API_VERSION)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
        except HTTPError as e:
            raise GitHubAPIError(e.code, e.read().decode("utf-8", "replace")) from e
        except URLError as e:
            raise GitHubAPIError(0, str(e.reason)) from e
        return json.loads(text) if text else {}

    def list_comments(self, repo: str, pr: int) -> list[dict]:
        return self._request(
            "GET", f"/repos/{repo}/issues/{pr}/comments?per_page=100"
        )

    def create_comment(self, repo: str, pr: int, body: str) -> dict:
        return self._request(
            "POST", f"/repos/{repo}/issues/{pr}/comments", {"body": body}
        )

    def update_comment(self, repo: str, comment_id: int, body: str) -> dict:
        return self._request(
            "PATCH", f"/repos/{repo}/issues/comments/{comment_id}", {"body": body}
        )


def find_bot_comment(comments: list[dict]) -> int | None:
    """Return the id of an existing llm-regress comment, else None.

    Idempotency anchor: any comment whose body contains ``COMMENT_MARKER``.
    """
    for c in comments:
        if COMMENT_MARKER in (c.get("body") or ""):
            return c.get("id")
    return None
