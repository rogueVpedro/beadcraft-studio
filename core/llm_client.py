"""多协议大模型统一调用客户端（支持 OpenAI 兼容 / Google Gemini / Anthropic Claude）."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import requests

from core.agent_config import resolve_requests_proxies


def normalize_openai_chat_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if not url:
        url = "https://api.openai.com/v1"
    if url.endswith("/chat/completions"):
        return url
    # 智谱 /paas/v4、火山 /api/v3 或标准 /v1 均直接追加 /chat/completions
    if re.search(r"/v\d+$", url):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def strip_thinking_blocks(text: str) -> str:
    """剥离 DeepSeek-R1 / QwQ 等推理模型的 <think>...</think> 思考块."""
    return re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()


def extract_json_object(text: str) -> Dict[str, Any] | None:
    """从模型输出文本中稳健提取第一个合法 JSON 对象."""
    cleaned = strip_thinking_blocks(text)
    # 优先提取 ```json ... ``` 代码块
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", cleaned, re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # 回退扫描最外层花括号
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = cleaned[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass
    return None


def call_llm_chat(
    messages: List[Dict[str, str]],
    cfg: Dict[str, Any],
    temperature: float | None = None,
    max_tokens: int = 1800,
) -> str:
    """统一调用用户配置的大模型并返回文本回复."""
    protocol = str(cfg.get("protocol") or "openai").lower()
    api_key = str(cfg.get("api_key") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip()
    model = str(cfg.get("model") or "").strip()
    temp = float(temperature if temperature is not None else cfg.get("temperature", 0.4))
    proxies = resolve_requests_proxies(cfg)

    is_local = "127.0.0.1" in base_url or "localhost" in base_url
    if not api_key and not is_local:
        raise ValueError("尚未配置大模型 API Key，请点击「配置模型与搜索」填入您的密钥")
    if not model:
        raise ValueError("模型名称不能为空，请在配置中指定模型 ID（例如 deepseek-chat 或 gpt-4o-mini）")

    if protocol == "gemini":
        b_url = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        endpoint = f"{b_url}/v1beta/models/{model}:generateContent"
        sys_parts = [m["content"] for m in messages if m["role"] == "system"]
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        payload: Dict[str, Any] = {
            "contents": contents or [{"role": "user", "parts": [{"text": "你好"}]}],
            "generationConfig": {"temperature": temp, "maxOutputTokens": max_tokens},
        }
        if sys_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(sys_parts)}]}

        resp = requests.post(
            endpoint,
            params={"key": api_key},
            json=payload,
            headers={"Content-Type": "application/json"},
            proxies=proxies,
            timeout=40,
        )
        if not resp.ok:
            raise RuntimeError(f"Gemini 接口错误 (HTTP {resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return strip_thinking_blocks(raw_text)
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Gemini 返回结构异常: {str(data)[:180]}") from exc

    if protocol == "anthropic":
        b_url = (base_url or "https://api.anthropic.com").rstrip("/")
        endpoint = b_url if b_url.endswith("/messages") else (f"{b_url}/messages" if b_url.endswith("/v1") else f"{b_url}/v1/messages")
        sys_text = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conv = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temp,
            "messages": conv or [{"role": "user", "content": "Hello"}],
        }
        if sys_text:
            payload["system"] = sys_text

        resp = requests.post(
            endpoint,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            proxies=proxies,
            timeout=40,
        )
        if not resp.ok:
            raise RuntimeError(f"Claude 接口错误 (HTTP {resp.status_code}): {resp.text[:200]}")
        data = resp.json()
        blocks = data.get("content") or []
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        return strip_thinking_blocks("\n".join(texts))

    # 默认 OpenAI 兼容协议 (DeepSeek / 通义千问 / 硅基流动 / Kimi / GLM / OpenAI / Ollama)
    endpoint = normalize_openai_chat_url(base_url)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temp,
        "max_tokens": max_tokens,
    }
    resp = requests.post(endpoint, json=payload, headers=headers, proxies=proxies, timeout=45)
    if resp.status_code in (401, 403):
        raise ValueError(f"大模型 API Key 鉴权失败 (HTTP {resp.status_code})，请核对密钥与服务商地址")
    if not resp.ok:
        raise RuntimeError(f"大模型调用失败 (HTTP {resp.status_code}): {resp.text[:220]}")

    data = resp.json()
    try:
        content = data["choices"][0]["message"].get("content") or ""
        return strip_thinking_blocks(str(content))
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"模型响应格式异常: {str(data)[:180]}") from exc


def test_llm_connectivity(cfg: Dict[str, Any]) -> str:
    reply = call_llm_chat(
        messages=[{"role": "user", "content": "请仅回复“连接成功”四个字。"}],
        cfg=cfg,
        temperature=0.1,
        max_tokens=32,
    )
    return reply[:40] or "OK"
