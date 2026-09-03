from __future__ import annotations

from pathlib import Path

import yaml

from .models import TestSuite


class SuiteLoadError(Exception):
    """用例集内容加载或校验失败。"""


def _validate_data(data: object, source: str) -> TestSuite:
    if not isinstance(data, dict):
        raise SuiteLoadError(f"Suite {source} must be a YAML mapping")
    try:
        suite = TestSuite.model_validate(data)
    except Exception as e:
        raise SuiteLoadError(f"Suite validation failed in {source}: {e}") from e
    if not suite.cases:
        raise SuiteLoadError("Suite must contain at least one case")
    ids = [c.id for c in suite.cases]
    if len(ids) != len(set(ids)):
        raise SuiteLoadError(f"Duplicate case ids found: {sorted({i for i in ids if ids.count(i) > 1})}")
    return suite


def loads_suite(text: str, *, source: str = "<string>") -> TestSuite:
    """从字符串解析用例集（DB / API 场景）。"""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SuiteLoadError(f"Invalid YAML in {source}: {e}") from e
    return _validate_data(data, source)


def load_suite(path: str | Path) -> TestSuite:
    p = Path(path)
    if not p.exists():
        raise SuiteLoadError(f"Suite file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise SuiteLoadError(f"Cannot read suite file {p}: {e}") from e
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SuiteLoadError(f"Invalid YAML in {p}: {e}") from e
    return _validate_data(data, str(p))
