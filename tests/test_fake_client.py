# tests/test_fake_client.py
from llm_regress.providers.fake import FakeLLMClient


async def test_complete_returns_mapped_response():
    client = FakeLLMClient(responses={"你好": "你好呀"}, default="fallback")
    r1 = await client.complete([{"role": "user", "content": "你好"}])
    r2 = await client.complete([{"role": "user", "content": "别的问题"}])
    assert r1.content == "你好呀"
    assert r2.content == "fallback"
    assert len(client.calls) == 2
    assert client.calls[0]["temperature"] == 0.0


async def test_embed_is_deterministic_and_distinct():
    client = FakeLLMClient()
    a1 = await client.embed("文本A")
    a2 = await client.embed("文本A")
    b = await client.embed("文本B")
    assert a1 == a2
    assert a1 != b
    assert len(a1) == 16
