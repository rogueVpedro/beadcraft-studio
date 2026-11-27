"""Tavily 联网搜索（含图片与描述提取）及并发候选图像下载清洗模块."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import io
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from PIL import Image
import requests

from core.agent_config import resolve_requests_proxies

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def tavily_search(
    query: str,
    cfg: Dict[str, Any],
    max_results: int = 6,
    include_images: bool = True,
) -> Dict[str, Any]:
    """调用 Tavily Search API 获取网页摘要与匹配参考图片列表."""
    api_key = str(cfg.get("tavily_api_key", "")).strip()
    if not api_key:
        raise ValueError("尚未配置 Tavily API Key，请在右上角「模型与搜索配置」中填入 tvly-... 密钥")

    base_url = str(cfg.get("tavily_base_url", "https://api.tavily.com")).rstrip("/")
    endpoint = base_url if base_url.endswith("/search") else f"{base_url}/search"
    search_depth = cfg.get("tavily_search_depth", "basic")
    proxies = resolve_requests_proxies(cfg)

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
        "include_images": include_images,
        "include_image_descriptions": include_images,
        "include_answer": True,
        "max_results": max_results,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": USER_AGENT,
    }

    resp = requests.post(endpoint, json=payload, headers=headers, proxies=proxies, timeout=18)
    if resp.status_code in (401, 403):
        raise ValueError("Tavily API Key 无效或额度已用尽，请检查密钥配置")
    if not resp.ok:
        raise RuntimeError(f"Tavily 搜索请求失败 (HTTP {resp.status_code}): {resp.text[:160]}")

    data = resp.json()
    web_results: List[Dict[str, str]] = []
    for item in data.get("results") or []:
        if isinstance(item, dict):
            web_results.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "url": str(item.get("url") or "").strip(),
                    "content": str(item.get("content") or "").strip()[:320],
                }
            )

    image_candidates: List[Dict[str, str]] = []
    for idx, img_item in enumerate(data.get("images") or []):
        if isinstance(img_item, dict):
            u = str(img_item.get("url") or "").strip()
            desc = str(img_item.get("description") or "").strip()
        elif isinstance(img_item, str):
            u = img_item.strip()
            desc = ""
        else:
            continue
        if u.startswith("http"):
            domain = urlparse(u).netloc
            image_candidates.append(
                {
                    "url": u,
                    "title": desc or f"{query} 参考图 #{idx + 1}",
                    "source_domain": domain,
                    "origin": "tavily",
                }
            )

    return {
        "query": query,
        "answer": str(data.get("answer") or "").strip(),
        "results": web_results,
        "images": image_candidates,
    }


def fetch_backup_images(query: str, cfg: Dict[str, Any], limit: int = 6) -> List[Dict[str, str]]:
    """当部分外链图片防盗链无法下载时，补充干净的候选参考图."""
    proxies = resolve_requests_proxies(cfg)
    candidates: List[Dict[str, str]] = []

    try:
        r = requests.get(
            "https://image.so.com/j",
            params={"q": query, "sn": "0", "pn": str(limit)},
            headers={"User-Agent": USER_AGENT, "Referer": "https://image.so.com/"},
            proxies=proxies,
            timeout=6,
        )
        if r.ok:
            j = r.json()
            for item in (j.get("list") or [])[:limit]:
                thumb = str(item.get("thumb") or item.get("img") or "").strip()
                title = str(item.get("title") or "").replace("<em>", "").replace("</em>", "").strip()
                if thumb.startswith("http"):
                    candidates.append(
                        {
                            "url": thumb,
                            "title": title or query,
                            "source_domain": urlparse(str(item.get("link") or thumb)).netloc,
                            "origin": "web_supplement",
                        }
                    )
    except Exception:
        pass

    return candidates


def _download_single_valid_image(item: Dict[str, str], proxies: Dict[str, str] | None) -> Tuple[Dict[str, str], bytes] | None:
    """下载单张候选图并验证尺寸有效（过滤损坏图、1×1 追踪像素或极端横幅广告条）."""
    url = item["url"]
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Referer": referer, "Accept": "image/*,*/*;q=0.8"},
            proxies=proxies,
            timeout=5.5,
        )
        if not resp.ok or len(resp.content) < 800 or len(resp.content) > 12_000_000:
            return None
        img = Image.open(io.BytesIO(resp.content))
        w, h = img.size
        if w < 56 or h < 56:
            return None
        ratio = max(w, h) / float(max(1, min(w, h)))
        if ratio > 3.2:
            return None
        # 统一归一化重编码为干净 PNG 字节流
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, format="PNG")
        return (item, buf.getvalue())
    except Exception:
        return None


def download_valid_candidate_images(
    candidates: List[Dict[str, str]],
    cfg: Dict[str, Any],
    target_count: int = 4,
) -> List[Tuple[Dict[str, str], bytes]]:
    """并发拉取候选图片并保留前 target_count 张高质量可用图像."""
    if not candidates:
        return []

    proxies = resolve_requests_proxies(cfg)
    seen_urls = set()
    unique_cands = []
    for c in candidates:
        u = c.get("url", "")
        if u and u not in seen_urls:
            seen_urls.add(u)
            unique_cands.append(c)
        if len(unique_cands) >= 12:
            break

    valid: List[Tuple[int, Dict[str, str], bytes]] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        fut_map = {
            pool.submit(_download_single_valid_image, cand, proxies): idx
            for idx, cand in enumerate(unique_cands)
        }
        for fut in as_completed(fut_map):
            order_idx = fut_map[fut]
            res = fut.result()
            if res is not None:
                valid.append((order_idx, res[0], res[1]))

    valid.sort(key=lambda x: x[0])
    return [(item, raw) for _, item, raw in valid[:target_count]]
