# tests/test_comment.py
import io
from urllib.error import HTTPError, URLError

import pytest
from typer.testing import CliRunner

from llm_regress.github_api import GitHubAPI

from llm_regress import cli
from llm_regress.github_api import COMMENT_MARKER, GitHubAPIError
from llm_regress.models import CaseResult, EvalResult, RunResult

runner = CliRunner()


def make_run(judge_fingerprint: str = "jf-1") -> RunResult:
    return RunResult(
        suite_name="demo",
        target_fingerprint="tf-1",
        judge_fingerprint=judge_fingerprint,
        started_at="2026-09-04T10:00:00",
        results=[
            CaseResult(
                case_id="c1",
                input="问",
                output="这是猫",
                evals=[
                    EvalResult(evaluator="contains", score=1.0, passed=True, detail="ok")
                ],
                score=1.0,
                passed=True,
            )
        ],
    )


def write_run_file(tmp_path, run: RunResult | None = None):
    p = tmp_path / "run.json"
    p.write_text((run or make_run()).model_dump_json(indent=2), encoding="utf-8")
    return p


class FakeTransport:
    """Replacement for GitHubAPI._request; records calls, never networks."""

    def __init__(self, get_response=None, error: GitHubAPIError | None = None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.get_response = [] if get_response is None else get_response
        self.error = error

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.error is not None:
            raise self.error
        if method == "GET":
            return self.get_response
        return {"html_url": "https://github.com/o/n/issues/1#issuecomment-9"}

    def methods(self):
        return [m for m, _, _ in self.calls]

    def last_body(self) -> str:
        return (self.calls[-1][2] or {}).get("body", "")


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")


def invoke(tmp_path, monkeypatch, transport, extra_env=True):
    monkeypatch.setattr(
        "llm_regress.github_api.GitHubAPI._request", transport
    )
    return runner.invoke(
        cli.app,
        [
            "comment",
            "--repo",
            "o/n",
            "--pr",
            "1",
            "--run-file",
            str(write_run_file(tmp_path)),
        ],
    )


def combined_output(result) -> str:
    stderr = getattr(result, "stderr", "") or ""
    return result.output + stderr


def test_posts_new_comment_when_none_exists(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    transport = FakeTransport()
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 0, result.output
    assert transport.methods() == ["GET", "POST"]
    method, path, body = transport.calls[-1]
    assert path == "/repos/o/n/issues/1/comments"
    assert COMMENT_MARKER in body["body"]
    assert "## llm-regress 报告" in body["body"]
    assert "https://github.com/o/n/issues/1#issuecomment-9" in result.output


def test_updates_existing_comment_instead_of_posting(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    transport = FakeTransport(
        get_response=[{"id": 42, "body": f"old report {COMMENT_MARKER}"}]
    )
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 0, result.output
    assert transport.methods() == ["GET", "PATCH"]
    _, path, _ = transport.calls[-1]
    assert path == "/repos/o/n/issues/comments/42"


def test_missing_token_exit_3(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    transport = FakeTransport()
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 3
    assert "GITHUB_TOKEN" in combined_output(result)
    assert transport.calls == []  # no network attempted


def test_api_error_exit_3_with_status(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    transport = FakeTransport(error=GitHubAPIError(422, "Validation Failed"))
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 3
    out = combined_output(result)
    assert "422" in out
    assert "Validation Failed" in out


def test_missing_run_file_exit_3(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("llm_regress.github_api.GitHubAPI._request", FakeTransport())
    result = runner.invoke(
        cli.app,
        ["comment", "--repo", "o/n", "--pr", "1", "--run-file",
         str(tmp_path / "nope.json")],
    )
    assert result.exit_code == 3
    assert "Failed to load run file" in combined_output(result)


def test_corrupt_run_file_exit_3(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "run.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("llm_regress.github_api.GitHubAPI._request", FakeTransport())
    result = runner.invoke(
        cli.app,
        ["comment", "--repo", "o/n", "--pr", "1", "--run-file", str(bad)],
    )
    assert result.exit_code == 3


def test_judge_changed_still_posts_with_warning(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    # Baseline with a different judge fingerprint -> JudgeChangedError.
    baseline = make_run(judge_fingerprint="jf-OLD")
    bp = tmp_path / ".llm-regress" / "baselines"
    bp.mkdir(parents=True)
    (bp / "demo.json").write_text(baseline.model_dump_json(indent=2), encoding="utf-8")

    transport = FakeTransport()
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 0, result.output
    assert transport.methods() == ["GET", "POST"]
    body = transport.last_body()
    assert body.startswith("> ⚠️ Judge changed")
    assert "jf-OLD" in body
    assert COMMENT_MARKER in body


def test_corrupt_baseline_still_posts_with_warning(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    # Baseline file exists but is invalid JSON -> load_baseline raises
    # ValueError (pydantic ValidationError); must degrade, never crash.
    bp = tmp_path / ".llm-regress" / "baselines"
    bp.mkdir(parents=True)
    (bp / "demo.json").write_text("{corrupt", encoding="utf-8")

    transport = FakeTransport()
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 0, result.output
    assert transport.methods() == ["GET", "POST"]
    body = transport.last_body()
    assert body.startswith("> ⚠️ 基线文件损坏，已按无对比模式生成评论")
    assert "## llm-regress 报告" in body
    assert COMMENT_MARKER in body
    assert "Corrupt baseline" in combined_output(result)


def test_unreadable_baseline_still_posts_with_warning(tmp_path, monkeypatch, token):
    monkeypatch.chdir(tmp_path)
    # Baseline path exists but is a directory -> load_baseline raises
    # IsADirectoryError (an OSError). A directory is used instead of chmod 000
    # because permission checks are unreliable when tests run as root.
    bp = tmp_path / ".llm-regress" / "baselines"
    bp.mkdir(parents=True)
    (bp / "demo.json").mkdir()

    transport = FakeTransport()
    result = invoke(tmp_path, monkeypatch, transport)
    assert result.exit_code == 0, result.output
    assert transport.methods() == ["GET", "POST"]
    body = transport.last_body()
    assert body.startswith("> ⚠️ 基线文件损坏，已按无对比模式生成评论")
    assert "## llm-regress 报告" in body
    assert COMMENT_MARKER in body
    assert "Corrupt baseline" in combined_output(result)


def test_request_maps_http_error(monkeypatch):
    """Real GitHubAPI._request error mapping, no network: urlopen stubbed."""
    def raise_http(req, timeout):
        fp = io.BytesIO(b'{"message": "Forbidden"}')
        raise HTTPError(req.full_url, 403, "Forbidden", None, fp)

    monkeypatch.setattr("llm_regress.github_api.urlopen", raise_http)
    with pytest.raises(GitHubAPIError) as excinfo:
        GitHubAPI("tok")._request("GET", "/repos/o/n/issues/1/comments")
    assert excinfo.value.status == 403
    assert "Forbidden" in excinfo.value.body


def test_request_maps_url_error_to_status_zero(monkeypatch):
    def raise_url(req, timeout):
        raise URLError("Name or service not known")

    monkeypatch.setattr("llm_regress.github_api.urlopen", raise_url)
    with pytest.raises(GitHubAPIError) as excinfo:
        GitHubAPI("tok")._request("GET", "/repos/o/n/issues/1/comments")
    assert excinfo.value.status == 0
    assert "Name or service not known" in excinfo.value.body
