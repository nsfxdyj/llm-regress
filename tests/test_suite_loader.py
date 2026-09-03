import pytest

from llm_regress.suite_loader import SuiteLoadError, load_suite


def write(tmp_path, text: str):
    p = tmp_path / "suite.yaml"
    p.write_text(text, encoding="utf-8")
    return p


VALID = """
name: demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c1
    input: 你好
    evaluators:
      - type: contains
        params: {keywords: ["你"]}
"""


def test_load_valid_suite(tmp_path):
    suite = load_suite(write(tmp_path, VALID))
    assert suite.name == "demo"
    assert suite.cases[0].evaluators[0].type == "contains"


def test_missing_file(tmp_path):
    with pytest.raises(SuiteLoadError, match="not found"):
        load_suite(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    with pytest.raises(SuiteLoadError, match="Invalid YAML"):
        load_suite(write(tmp_path, "name: [unclosed"))


def test_empty_cases(tmp_path):
    with pytest.raises(SuiteLoadError, match="at least one case"):
        load_suite(
            write(
                tmp_path,
                "name: d\ntarget:\n  base_url: http://x\n  model: m\ncases: []\n",
            )
        )


def test_duplicate_case_ids(tmp_path):
    text = VALID + "  - id: c1\n    input: 重复\n"
    with pytest.raises(SuiteLoadError, match="Duplicate case ids"):
        load_suite(write(tmp_path, text))
