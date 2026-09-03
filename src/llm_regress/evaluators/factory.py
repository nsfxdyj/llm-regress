# src/llm_regress/evaluators/factory.py
from __future__ import annotations

from ..models import EvaluatorConfig, TestSuite
from ..providers.base import LLMClient
from .base import Evaluator
from .judge import JudgeEvaluator
from .rules import RULE_EVALUATORS
from .similarity import SimilarityEvaluator


class EvaluatorConfigError(Exception):
    """评测器配置非法（类型未知或参数缺失）。"""


def build_evaluators(
    configs: list[EvaluatorConfig],
    *,
    target_client: LLMClient,
    judge_client: LLMClient,
) -> list[tuple[Evaluator, float]]:
    built: list[tuple[Evaluator, float]] = []
    for cfg in configs:
        try:
            if cfg.type in RULE_EVALUATORS:
                ev = RULE_EVALUATORS[cfg.type](cfg.params)
            elif cfg.type == "similarity":
                ev = SimilarityEvaluator(target_client, cfg.params)
            elif cfg.type == "judge":
                ev = JudgeEvaluator(judge_client, cfg.params)
            else:
                raise EvaluatorConfigError(
                    f"unknown evaluator type: {cfg.type!r} "
                    f"(known: {sorted(RULE_EVALUATORS) + ['similarity', 'judge']})"
                )
        except ValueError as e:
            raise EvaluatorConfigError(f"invalid params for {cfg.type!r}: {e}") from e
        built.append((ev, cfg.weight))
    return built


def validate_suite(
    suite: TestSuite,
    *,
    target_client: LLMClient,
    judge_client: LLMClient,
) -> None:
    """在任何 LLM 调用前构建全部评测器，让配置错误 fail-fast。"""
    for case in suite.cases:
        try:
            build_evaluators(
                case.evaluators, target_client=target_client, judge_client=judge_client
            )
        except EvaluatorConfigError as e:
            raise EvaluatorConfigError(f"case {case.id!r}: {e}") from e
