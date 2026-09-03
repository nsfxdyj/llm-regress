import pytest
from fastapi.testclient import TestClient

from llm_regress.server.app import create_app

VALID_YAML = """
name: demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c1
    input: 你好
"""


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=tmp_path / "t.db")
    with TestClient(app) as c:
        yield c


def make_project(client, name="p1"):
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_project_crud(client):
    pid = make_project(client)
    assert any(p["id"] == pid for p in client.get("/api/projects").json())
    r = client.post("/api/projects", json={"name": "p1"})
    assert r.status_code == 422  # 重名
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get("/api/projects").json() == []


def test_suite_create_validates_yaml(client):
    pid = make_project(client)
    bad = client.post(f"/api/projects/{pid}/suites", json={"name": "s", "yaml_text": "not: valid: ["})
    assert bad.status_code == 422
    good = client.post(f"/api/projects/{pid}/suites", json={"name": "s", "yaml_text": VALID_YAML})
    assert good.status_code == 201, good.text
    sid = good.json()["id"]
    assert client.get(f"/api/suites/{sid}").json()["name"] == "s"


def test_suite_update_and_validate_endpoint(client):
    pid = make_project(client)
    sid = client.post(f"/api/projects/{pid}/suites", json={"name": "s", "yaml_text": VALID_YAML}).json()["id"]
    r = client.post(f"/api/suites/{sid}/validate")
    body = r.json()
    assert body["ok"] and body["cases"] == [{"id": "c1", "evaluator_count": 0}]
    bad = client.put(f"/api/suites/{sid}", json={"name": "s", "yaml_text": "cases: []"})
    assert bad.status_code == 422
    # 失败更新不破坏原内容
    assert "demo" in client.get(f"/api/suites/{sid}").json()["yaml_text"]


def test_404s(client):
    assert client.get("/api/suites/999").status_code == 404
    assert client.delete("/api/projects/999").status_code == 404
