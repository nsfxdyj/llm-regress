from __future__ import annotations

import json
import re

import jsonschema

from ..models import EvalResult, TestCase


class ContainsEvaluator:
    name = "contains"

    def __init__(self, params: dict):
        keywords = params.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError("contains evaluator requires params.keywords: non-empty list[str]")
        self.keywords = keywords

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        missing = [k for k in self.keywords if k not in output]
        passed = not missing
        score = (len(self.keywords) - len(missing)) / len(self.keywords)
        detail = "all keywords present" if passed else f"missing: {', '.join(missing)}"
        return EvalResult(evaluator=self.name, score=score, passed=passed, detail=detail)


class NotContainsEvaluator:
    name = "not_contains"

    def __init__(self, params: dict):
        keywords = params.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError("not_contains evaluator requires params.keywords: non-empty list[str]")
        self.keywords = keywords

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        hits = [k for k in self.keywords if k in output]
        passed = not hits
        score = (len(self.keywords) - len(hits)) / len(self.keywords)
        detail = "clean" if passed else f"forbidden present: {', '.join(hits)}"
        return EvalResult(evaluator=self.name, score=score, passed=passed, detail=detail)


class JsonValidEvaluator:
    name = "json_valid"

    def __init__(self, params: dict):
        pass

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        try:
            json.loads(output)
            return EvalResult(evaluator=self.name, score=1.0, passed=True, detail="valid JSON")
        except json.JSONDecodeError as e:
            return EvalResult(evaluator=self.name, score=0.0, passed=False, detail=f"invalid JSON: {e}")


class JsonSchemaEvaluator:
    name = "json_schema"

    def __init__(self, params: dict):
        schema = params.get("schema")
        if not isinstance(schema, dict):
            raise ValueError("json_schema evaluator requires params.schema: dict")
        self.schema = schema

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            return EvalResult(evaluator=self.name, score=0.0, passed=False, detail=f"invalid JSON: {e}")
        try:
            jsonschema.validate(data, self.schema)
            return EvalResult(evaluator=self.name, score=1.0, passed=True, detail="schema valid")
        except jsonschema.ValidationError as e:
            return EvalResult(evaluator=self.name, score=0.0, passed=False, detail=f"schema violation: {e.message}")


class LengthEvaluator:
    name = "length"

    def __init__(self, params: dict):
        self.min_chars = params.get("min_chars")
        self.max_chars = params.get("max_chars")
        if self.min_chars is None and self.max_chars is None:
            raise ValueError("length evaluator requires params.min_chars and/or params.max_chars")

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        n = len(output)
        passed = (self.min_chars is None or n >= self.min_chars) and (
            self.max_chars is None or n <= self.max_chars
        )
        return EvalResult(
            evaluator=self.name,
            score=1.0 if passed else 0.0,
            passed=passed,
            detail=f"length={n}, range=[{self.min_chars}, {self.max_chars}]",
        )


class RegexEvaluator:
    name = "regex"

    def __init__(self, params: dict):
        pattern = params.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("regex evaluator requires params.pattern: str")
        try:
            self.pattern = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"invalid regex: {e}") from e
        self.expected = params.get("expected")  # 可选：比对第一个捕获组

    async def evaluate(self, case: TestCase, output: str) -> EvalResult:
        m = self.pattern.search(output)
        if not m:
            return EvalResult(evaluator=self.name, score=0.0, passed=False, detail="pattern not found")
        if self.expected is not None:
            got = m.group(1) if m.groups() else m.group(0)
            passed = got == str(self.expected)
            return EvalResult(
                evaluator=self.name,
                score=1.0 if passed else 0.0,
                passed=passed,
                detail=f"extracted={got!r}, expected={self.expected!r}",
            )
        return EvalResult(evaluator=self.name, score=1.0, passed=True, detail=f"matched: {m.group(0)!r}")


RULE_EVALUATORS: dict[str, type] = {
    "contains": ContainsEvaluator,
    "not_contains": NotContainsEvaluator,
    "json_valid": JsonValidEvaluator,
    "json_schema": JsonSchemaEvaluator,
    "length": LengthEvaluator,
    "regex": RegexEvaluator,
}
