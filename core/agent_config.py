"""智能体模型与联网搜索配置管理模块 (.agent_config.json 本地持久化，已加入 .gitignore)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

CONFIG_PATH = Path(__file__).resolve().parent.parent / ".agent_config.json"

LLM_PRESETS: List[Dict[str, str]] = [
    {
        "id": "deepseek",
        "name": "DeepSeek (官方)",
        "protocol": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    {
        "id": "qwen",
        "name": "通义千问 (阿里云百炼)",
        "protocol": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 (SiliconFlow)",
        "protocol": "openai",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "Qwen/Qwen2.5-72B-Instruct",
    },
    {
        "id": "kimi",
        "name": "Kimi (Moonshot)",
        "protocol": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
    },
    {
        "id": "zhipu",
        "name": "智谱清言 (GLM)",
        "protocol": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
    },
    {
        "id": "openai",
        "name": "OpenAI / 通用中转兼容",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com",
        "default_model": "gemini-2.5-flash",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-3-5-sonnet-latest",
    },
    {
        "id": "ollama",
        "name": "Ollama 本地模型 (免Key)",
        "protocol": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_model": "qwen2.5:14b",
    },
]

DEFAULT_AGENT_CONFIG: Dict[str, Any] = {
    "preset_id": "deepseek",
    "protocol": "openai",           # openai | gemini | anthropic
    "base_url": "https://api.deepseek.com/v1",
    "api_key": os.environ.get("OPENAI_API_KEY", ""),
    "model": "deepseek-chat",
    "temperature": 0.4,
    "tavily_api_key": os.environ.get("TAVILY_API_KEY", ""),
    "tavily_base_url": "https://api.tavily.com",
    "tavily_search_depth": "basic",  # basic | advanced
    "enable_backup_image_search": True,
    "proxy_mode": "system",          # system | none | custom
    "custom_proxy": "http://127.0.0.1:7890",
}


def load_agent_config() -> Dict[str, Any]:
    cfg = dict(DEFAULT_AGENT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_agent_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    current = load_agent_config()
    for key in DEFAULT_AGENT_CONFIG:
        if key not in updates:
            continue
        val = updates[key]
        # 若前端传回掩码占位符，保留已保存的真实密钥不覆盖
        if key in ("api_key", "tavily_api_key") and isinstance(val, str) and val.startswith("****"):
            continue
        current[key] = val

    CONFIG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****" + secret[-2:]
    return f"****{secret[-4:]}"


def get_public_agent_config() -> Dict[str, Any]:
    """返回脱敏后的前端展示配置及状态标志."""
    cfg = load_agent_config()
    is_local_ollama = "127.0.0.1:11434" in cfg.get("base_url", "") or "localhost:11434" in cfg.get("base_url", "")
    llm_ready = bool(cfg.get("api_key", "").strip()) or is_local_ollama
    tavily_ready = bool(cfg.get("tavily_api_key", "").strip())

    return {
        "preset_id": cfg["preset_id"],
        "protocol": cfg["protocol"],
        "base_url": cfg["base_url"],
        "api_key_masked": mask_secret(cfg.get("api_key", "")),
        "has_api_key": bool(cfg.get("api_key", "").strip()),
        "model": cfg["model"],
        "temperature": cfg["temperature"],
        "tavily_api_key_masked": mask_secret(cfg.get("tavily_api_key", "")),
        "has_tavily_key": tavily_ready,
        "tavily_base_url": cfg["tavily_base_url"],
        "tavily_search_depth": cfg["tavily_search_depth"],
        "enable_backup_image_search": bool(cfg.get("enable_backup_image_search", True)),
        "proxy_mode": cfg.get("proxy_mode", "system"),
        "custom_proxy": cfg.get("custom_proxy", ""),
        "llm_ready": llm_ready,
        "tavily_ready": tavily_ready,
        "presets": LLM_PRESETS,
    }


def resolve_requests_proxies(cfg: Dict[str, Any]) -> Dict[str, str] | None:
    """根据用户配置的代理策略生成 requests 的 proxies 参数."""
    mode = cfg.get("proxy_mode", "system")
    if mode == "none":
        return {"http": "", "https": ""}
    if mode == "custom":
        p = str(cfg.get("custom_proxy", "")).strip()
        if p:
            return {"http": p, "https": p}
    # mode == "system": None 让 requests 自动读取 Windows 注册表系统代理
    return None
