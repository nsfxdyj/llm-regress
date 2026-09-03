# tests/test_openai_compat.py
import httpx
import pytest

from llm_regress.models import TargetConfig
from llm_regress.providers.base import ProviderError
from llm_regress.providers.openai_compat import OpenAICompatClient

CONFIG = TargetConfig(base_url="https://api.example.com", model="m1")


def chat_payload(text: str):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"total_tokens": 10},
    }


async def no_sleep(_):
    return None


async def test_complete_success():
    def handler(request):
        assert request.url.path == "/chat/completions"
        return httpx.Response(200, json=chat_payload("回答内容"))

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler))
    resp = await client.complete([{"role": "user", "content": "hi"}])
    assert resp.content == "回答内容"
    assert resp.usage["total_tokens"] == 10


async def test_retry_on_429_respects_retry_after():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(429, headers={"Retry-After": "0.01"}, json={})
        return httpx.Response(200, json=chat_payload("终于成功"))

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler), sleep=no_sleep)
    resp = await client.complete([{"role": "user", "content": "hi"}])
    assert resp.content == "终于成功"
    assert len(attempts) == 3


async def test_retry_after_http_date_falls_back_to_exponential():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 2:
            return httpx.Response(
                429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, json={}
            )
        return httpx.Response(200, json=chat_payload("成功"))

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler), sleep=no_sleep)
    resp = await client.complete([{"role": "user", "content": "hi"}])
    assert resp.content == "成功"
    assert len(attempts) == 2


async def test_non_json_2xx_raises_provider_error():
    def handler(request):
        return httpx.Response(200, text="<html>oops</html>")

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="non-JSON"):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_retry_exhausted_raises_provider_error():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler), sleep=no_sleep)
    with pytest.raises(ProviderError, match="500"):
        await client.complete([{"role": "user", "content": "hi"}])


async def test_400_raises_immediately_without_retry():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": "bad request"})

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler), sleep=no_sleep)
    with pytest.raises(ProviderError, match="400"):
        await client.complete([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


async def test_embed():
    def handler(request):
        assert request.url.path == "/embeddings"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    client = OpenAICompatClient(CONFIG, transport=httpx.MockTransport(handler))
    vec = await client.embed("文本", model="emb-1")
    assert vec == [0.1, 0.2]


def test_missing_api_key_env_raises(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    cfg = TargetConfig(base_url="https://x", model="m", api_key_env="MISSING_KEY")
    with pytest.raises(ProviderError, match="MISSING_KEY"):
        OpenAICompatClient(cfg)
