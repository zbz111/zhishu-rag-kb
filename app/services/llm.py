"""大模型调用：Ollama（默认，本地免费）与 OpenAI 兼容接口（DeepSeek / 通义 / vLLM）。"""
from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from ..config import settings


class LLMError(RuntimeError):
    pass


# 把 HTTP 状态码翻译成人能看懂的排查提示
_FRIENDLY = {
    401: "API Key 无效或已失效。请更新 .env 里的 OPENAI_API_KEY 后重启服务。",
    403: "API Key 没有该模型的权限。请到控制台确认模型是否已开通。",
    402: "账户余额不足，请充值后重试。",
    404: "模型名不存在。请检查 OPENAI_CHAT_MODEL 是否写对。",
    429: "请求太频繁，被限流了。请稍后再试或降低并发。",
}


def friendly_status(code: int, body: str = "") -> str:
    hint = _FRIENDLY.get(code)
    if hint:
        return f"模型服务返回 {code}：{hint}"
    return f"模型服务返回 {code}：{body[:200]}"


def _ollama_payload(messages: list[dict], stream: bool) -> dict:
    return {
        "model": settings.ollama_chat_model,
        "messages": messages,
        "stream": stream,
        "options": {"temperature": settings.temperature, "num_predict": settings.max_tokens},
    }


def _openai_payload(messages: list[dict], stream: bool) -> dict:
    return {
        "model": settings.openai_chat_model,
        "messages": messages,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "stream": stream,
    }


def chat(messages: list[dict]) -> tuple[str, int]:
    if settings.llm_provider == "openai":
        return _openai_chat(messages)
    return _ollama_chat(messages)


def _ollama_chat(messages: list[dict]) -> tuple[str, int]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=5)) as client:
            resp = client.post(url, json=_ollama_payload(messages, False))
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"模型服务不可用：{exc}") from exc
    content = data.get("message", {}).get("content", "")
    tokens = int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0))
    return content, tokens


def _openai_chat(messages: list[dict]) -> tuple[str, int]:
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=5)) as client:
            resp = client.post(url, headers=headers, json=_openai_payload(messages, False))
            if resp.status_code >= 400:
                raise LLMError(friendly_status(resp.status_code, resp.text))
            data = resp.json()
    except httpx.HTTPError as exc:
        raise LLMError(f"模型服务不可达：{exc}") from exc
    return data["choices"][0]["message"]["content"], int(data.get("usage", {}).get("total_tokens", 0))


def stream_chat(messages: list[dict]) -> Iterator[str]:
    if settings.llm_provider == "openai":
        yield from _openai_stream(messages)
    else:
        yield from _ollama_stream(messages)


def _ollama_stream(messages: list[dict]) -> Iterator[str]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=5)) as client:
            with client.stream("POST", url, json=_ollama_payload(messages, True)) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", "ignore")
                    raise LLMError(f"模型服务返回 {resp.status_code}: {body[:200]}")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if data.get("done"):
                        break
    except httpx.HTTPError as exc:
        raise LLMError(f"模型服务不可用：{exc}") from exc


def _openai_stream(messages: list[dict]) -> Iterator[str]:
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        with httpx.Client(timeout=httpx.Timeout(300, connect=5)) as client:
            with client.stream("POST", url, headers=headers, json=_openai_payload(messages, True)) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", "ignore")
                    raise LLMError(friendly_status(resp.status_code, body))
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        yield delta
    except httpx.HTTPError as exc:
        raise LLMError(f"模型服务不可用：{exc}") from exc


def health() -> dict:
    """启动/健康检查用：确认模型与 embedding 服务可达。"""
    info = {"provider": settings.llm_provider, "chat_model": "", "embed_model": "", "ok": False}
    if settings.llm_provider == "openai":
        info["chat_model"] = settings.openai_chat_model
        info["embed_model"] = settings.openai_embed_model
        info["ok"] = bool(settings.openai_api_key)
        return info
    info["chat_model"] = settings.ollama_chat_model
    info["embed_model"] = settings.ollama_embed_model
    try:
        with httpx.Client(timeout=3) as client:
            resp = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            info["ok"] = resp.status_code == 200
            info["models"] = [m["name"] for m in resp.json().get("models", [])]
    except httpx.HTTPError:
        info["ok"] = False
    return info
