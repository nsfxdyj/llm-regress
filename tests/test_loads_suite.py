import pytest

from llm_regress.suite_loader import SuiteLoadError, loads_suite

VALID = """
name: demo
target:
  base_url: https://api.deepseek.com
  model: deepseek-chat
cases:
  - id: c1
    input: 你好
"""


def test_loads_valid():
    suite = loads_suite(VALID)
    assert suite.name == "demo" and suite.cases[0].id == "c1"


def test_loads_invalid_yaml():
    with pytest.raises(SuiteLoadError, match="Invalid YAML"):
        loads_suite("name: [unclosed", source="db")


def test_loads_empty_cases():
    with pytest.raises(SuiteLoadError, match="at least one case"):
        loads_suite("name: d\ntarget:\n  base_url: http://x\n  model: m\ncases: []\n")


def test_loads_duplicate_ids():
    with pytest.raises(SuiteLoadError, match="Duplicate case ids"):
        loads_suite(VALID + "  - id: c1\n    input: 重复\n")
