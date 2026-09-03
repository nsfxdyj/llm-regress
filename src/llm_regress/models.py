from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EvaluatorConfig(BaseModel):
    type: str
    weight: float = 1.0
    params: dict = Field(default_factory=dict)


class TargetConfig(BaseModel):
    provider: str = "openai-compatible"
    base_url: str
    api_key_env: str | None = None
    model: str


class TestCase(BaseModel):
    id: str
    input: str
    expected: str | None = None
    evaluators: list[EvaluatorConfig] = Field(default_factory=list)
    pass_threshold: float = 0.8


class TestSuite(BaseModel):
    name: str
    target: TargetConfig
    judge: TargetConfig | None = None
    cases: list[TestCase]


class EvalResult(BaseModel):
    evaluator: str
    score: float  # 0.0 - 1.0
    passed: bool
    detail: str = ""
    raw: str | None = None  # 裁判原始输出等可审计内容


class CaseStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class CaseResult(BaseModel):
    case_id: str
    status: CaseStatus = CaseStatus.OK
    input: str | None = None  # 用例输入快照，供 HTML 等报告展示；旧 JSON 缺省兼容
    expected: str | None = None  # 期望输出快照（如有）
    output: str = ""
    evals: list[EvalResult] = Field(default_factory=list)
    score: float = 0.0
    passed: bool = False
    error: str | None = None
    usage: dict = Field(default_factory=dict)


class RunResult(BaseModel):
    suite_name: str
    target_fingerprint: str
    judge_fingerprint: str | None = None
    started_at: str
    results: list[CaseResult]
