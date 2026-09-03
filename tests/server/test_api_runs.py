import pytest
from fastapi.testclient import TestClient

from llm_regress.providers.fake import FakeLLMClient
from llm_regress.server.app import create_app

VALID_YAML = """
name: demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c1
    input: 问
    evaluators:
      - type: contains
        params: {keywords: ["猫"]}
"""


@pytest.fixture
def client(tmp_path):
    state = {"answer": "这是猫"}

    def fake_factory(suite):
        return FakeLLMClient(default=state["answer"]), FakeLLMClient(default="{}")

    app = create_app(db_path=tmp_path / "t.db", client_factory=fake_factory)
    app.state.run_sync = True  # 测试同步执行
    app.state.fake_state = state
    with TestClient(app) as c:
        yield c


def make_suite(client) -> int:
    pid = client.post("/api/projects", json={"name": "p"}).json()["id"]
    return client.post(
        f"/api/projects/{pid}/suites", json={"name": "s", "yaml_text": VALID_YAML}
    ).json()["id"]


def test_trigger_run_and_fetch_detail(client):
    sid = make_suite(client)
    r = client.post(f"/api/suites/{sid}/runs")
    assert r.status_code == 202
    rid = r.json()["run_id"]
    detail = client.get(f"/api/runs/{rid}").json()
    assert detail["status"] == "done"
    assert detail["result"]["results"][0]["passed"] is True
    assert detail["summary"]["passed"] == 1
    assert detail["comparison"] is None  # 无基线
    assert detail["judge_changed"] is False


def test_run_history_order(client):
    sid = make_suite(client)
    client.post(f"/api/suites/{sid}/runs")
    client.post(f"/api/suites/{sid}/runs")
    runs = client.get(f"/api/suites/{sid}/runs").json()
    assert len(runs) == 2 and runs[0]["id"] > runs[1]["id"]


def test_comparison_after_promote(client):
    sid = make_suite(client)
    rid1 = client.post(f"/api/suites/{sid}/runs").json()["run_id"]
    assert client.post(f"/api/runs/{rid1}/promote").status_code == 200
    # 输出退化后再跑
    client.app.state.fake_state["answer"] = "无关内容"
    rid2 = client.post(f"/api/suites/{sid}/runs").json()["run_id"]
    detail = client.get(f"/api/runs/{rid2}").json()
    assert detail["comparison"]["has_regressions"] is True
    deltas = detail["comparison"]["deltas"]
    assert deltas[0]["case_id"] == "c1" and deltas[0]["change"] == "regression"


def test_run_config_error_marks_error_status(tmp_path):
    def bad_factory(suite):
        from llm_regress.providers.base import ProviderError

        raise ProviderError("Environment variable NOPE is not set")

    app = create_app(db_path=tmp_path / "t.db", client_factory=bad_factory)
    app.state.run_sync = True
    with TestClient(app) as c:
        sid = make_suite(c)
        rid = c.post(f"/api/suites/{sid}/runs").json()["run_id"]
        detail = c.get(f"/api/runs/{rid}").json()
        assert detail["status"] == "error"
        assert "NOPE" in detail["error"]
