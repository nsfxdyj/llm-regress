from fastapi.testclient import TestClient

from llm_regress.providers.fake import FakeLLMClient
from llm_regress.server.app import create_app

YAML = """
name: e2e
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


def test_full_flow(tmp_path):
    state = {"answer": "这是猫"}

    def factory(suite):
        return FakeLLMClient(default=state["answer"]), FakeLLMClient(default="{}")

    app = create_app(db_path=tmp_path / "e2e.db", client_factory=factory)
    app.state.run_sync = True
    with TestClient(app) as c:
        resp = c.post("/api/projects", json={"name": "p"})
        assert resp.status_code == 201
        pid = resp.json()["id"]
        resp = c.post(f"/api/projects/{pid}/suites", json={"name": "s", "yaml_text": YAML})
        assert resp.status_code == 201
        sid = resp.json()["id"]

        resp = c.post(f"/api/suites/{sid}/runs")
        assert resp.status_code == 202
        r1 = resp.json()["run_id"]
        d1 = c.get(f"/api/runs/{r1}").json()
        assert d1["status"] == "done" and d1["summary"]["passed"] == 1

        resp = c.post(f"/api/runs/{r1}/promote")
        assert resp.status_code == 200
        assert c.get(f"/api/suites/{sid}/baseline").json()["baseline_run_id"] == r1

        state["answer"] = "跑题了"
        resp = c.post(f"/api/suites/{sid}/runs")
        assert resp.status_code == 202
        r2 = resp.json()["run_id"]
        d2 = c.get(f"/api/runs/{r2}").json()
        assert d2["comparison"]["has_regressions"] is True
        assert d2["comparison"]["deltas"][0]["change"] == "regression"

        runs = c.get(f"/api/suites/{sid}/runs").json()
        assert len(runs) == 2
