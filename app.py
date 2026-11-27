"""拼豆工坊 (BeadCraft Studio) 桌面应用主入口.

集成本地高速图形计算引擎、AI 拼豆对话智能体（支持自定义大模型 + Tavily 联网图文搜索推荐）
以及独立 Windows 桌面应用窗口（Edge App Mode 独立窗口 + SSE 会话守卫）。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter, deque
import ctypes
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
import webbrowser
from typing import Any, Dict, Set

# 确保本地 127.0.0.1 回环通信永不经过系统代理，同时保留外网大模型与 Tavily 请求按需使用系统代理的能力
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

# 修复 pythonw.exe 无控制台模式下 stdout/stderr 为 None 导致 uvicorn 日志初始化报错的问题
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PIL import Image
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
import uvicorn

from core.agent import run_agent_turn
from core.agent_config import (
    get_public_agent_config,
    load_agent_config,
    save_agent_config,
)
from core.estimator import estimate_assembly_time
from core.exporter import export_blueprint_png, export_bom_xlsx
from core.generator import (
    QUALITY_PRESETS,
    generate_all_tiers_summary,
    generate_bead_pattern,
    load_normalized_rgba,
)
from core.llm_client import test_llm_connectivity
from core.palettes import get_palette, list_palettes_meta
from core.samples import SAMPLE_ITEMS, build_sample_png
from core.search_client import tavily_search
from core.wechat_clawbot import WeChatClawBotManager

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
RUNTIME_DIR = BASE_DIR / ".studio_webview_v2"

# 内存图像会话缓存（保留最近 36 张原图与智能体推荐候选图）
IMAGE_STORE: Dict[str, Image.Image] = {}

# 桌面窗口活跃会话与 SSE 实时事件广播队列
ACTIVE_CLIENTS: Set[str] = set()
CLIENT_QUEUES_LOCK = threading.Lock()
CLIENT_EVENT_QUEUES: Dict[str, deque[str]] = {}
CLIENT_CONNECTED_ONCE: bool = False
LAST_ACTIVITY_TIME: float = time.time()
WINDOW_CLOSE_BEACON_AT: float = 0.0
SHUTDOWN_EVENT = threading.Event()


def _broadcast_sse_event(event_name: str, payload: Dict[str, Any]) -> None:
    frame = f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    with CLIENT_QUEUES_LOCK:
        for q in CLIENT_EVENT_QUEUES.values():
            if len(q) < 64:
                q.append(frame)


def _touch_activity() -> None:
    global CLIENT_CONNECTED_ONCE, LAST_ACTIVITY_TIME, WINDOW_CLOSE_BEACON_AT
    CLIENT_CONNECTED_ONCE = True
    LAST_ACTIVITY_TIME = time.time()
    WINDOW_CLOSE_BEACON_AT = 0.0


def _store_image(img: Image.Image) -> str:
    while len(IMAGE_STORE) >= 36:
        oldest_key = next(iter(IMAGE_STORE))
        IMAGE_STORE.pop(oldest_key, None)
    img_id = uuid.uuid4().hex[:12]
    IMAGE_STORE[img_id] = img
    return img_id


def _get_image(img_id: str) -> Image.Image | None:
    return IMAGE_STORE.get(img_id)


def _image_to_data_url(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# 微信 ClawBot 扫码连接与图文联动单例管理器
WECHAT_BOT = WeChatClawBotManager(
    store_image_fn=_store_image,
    get_image_fn=_get_image,
    image_to_data_url_fn=_image_to_data_url,
    broadcast_event_fn=_broadcast_sse_event,
)


# ---------------------------------------------------------------------------
# HTTP API 路由
# ---------------------------------------------------------------------------
async def homepage(request: Request) -> Response:
    _touch_activity()
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    return Response(html, media_type="text/html; charset=utf-8")


async def favicon_ico(request: Request) -> Response:
    ico_path = BASE_DIR / "launcher" / "app.ico"
    if ico_path.exists():
        return Response(ico_path.read_bytes(), media_type="image/x-icon")
    return Response(status_code=404)


async def api_health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "app": "beadcraft_studio"})


async def api_init(request: Request) -> JSONResponse:
    _touch_activity()
    return JSONResponse(
        {
            "palettes": list_palettes_meta(),
            "qualities": list(QUALITY_PRESETS.values()),
            "samples": SAMPLE_ITEMS,
            "agent": get_public_agent_config(),
            "wechat": WECHAT_BOT.get_public_status(),
        }
    )


async def api_load_sample(request: Request) -> JSONResponse:
    _touch_activity()
    body = await request.json()
    sample_id = body.get("sample_id", "orange_cat")
    palette_id = body.get("palette_id", "mard_96")
    remove_bg = bool(body.get("remove_bg", False))
    bg_tolerance = float(body.get("bg_tolerance", 18.5))

    png_bytes = build_sample_png(sample_id)
    img = load_normalized_rgba(png_bytes)
    img_id = _store_image(img)

    tiers = generate_all_tiers_summary(
        img_rgba=img,
        palette_id=palette_id,
        remove_bg=remove_bg,
        bg_tolerance=bg_tolerance,
    )
    return JSONResponse(
        {
            "image_id": img_id,
            "source_width": img.size[0],
            "source_height": img.size[1],
            "source_data_url": _image_to_data_url(img),
            "tiers": tiers,
        }
    )


async def api_upload(request: Request) -> JSONResponse:
    _touch_activity()
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        return JSONResponse({"error": "未收到上传图片文件"}, status_code=400)

    raw_bytes = await upload.read()
    try:
        img = load_normalized_rgba(raw_bytes)
    except Exception as exc:
        return JSONResponse({"error": f"不支持的图片格式: {exc}"}, status_code=400)

    palette_id = str(form.get("palette_id", "mard_96"))
    remove_bg = str(form.get("remove_bg", "0")) == "1"
    bg_tolerance = float(form.get("bg_tolerance", "18.5"))

    img_id = _store_image(img)
    tiers = generate_all_tiers_summary(
        img_rgba=img,
        palette_id=palette_id,
        remove_bg=remove_bg,
        bg_tolerance=bg_tolerance,
    )
    return JSONResponse(
        {
            "image_id": img_id,
            "source_width": img.size[0],
            "source_height": img.size[1],
            "source_data_url": _image_to_data_url(img),
            "tiers": tiers,
        }
    )


async def api_recompute(request: Request) -> JSONResponse:
    _touch_activity()
    body = await request.json()
    img_id = body.get("image_id")
    img = IMAGE_STORE.get(img_id)
    if img is None:
        return JSONResponse({"error": "原图会话已过期，请重新导入图片"}, status_code=404)

    palette_id = body.get("palette_id", "mard_96")
    remove_bg = bool(body.get("remove_bg", False))
    bg_tolerance = float(body.get("bg_tolerance", 18.5))
    only_quality = body.get("only_quality")
    custom_max_side = body.get("custom_max_side")

    if only_quality and custom_max_side is not None:
        pat = generate_bead_pattern(
            img_rgba=img,
            quality=only_quality,
            palette_id=palette_id,
            remove_bg=remove_bg,
            custom_max_side=int(custom_max_side),
            bg_tolerance=bg_tolerance,
        )
        return JSONResponse({"tiers": {only_quality: pat}})

    tiers = generate_all_tiers_summary(
        img_rgba=img,
        palette_id=palette_id,
        remove_bg=remove_bg,
        bg_tolerance=bg_tolerance,
    )
    return JSONResponse({"tiers": tiers})


async def api_reestimate(request: Request) -> JSONResponse:
    _touch_activity()
    body = await request.json()
    grid = body["grid"]
    palette_id = body.get("palette_id", "mard_96")
    palette = get_palette(palette_id)

    usage = Counter()
    for row in grid:
        for val in row:
            if val >= 0:
                usage[val] += 1

    total_beads = sum(usage.values())
    bom = []
    for p_idx, count in usage.most_common():
        cinfo = palette.colors[p_idx]
        bom.append(
            {
                "palette_index": p_idx,
                "code": cinfo["code"],
                "name": cinfo["name"],
                "hex": cinfo["hex"],
                "text_color": cinfo["text_color"],
                "count": count,
                "percentage": round((count / max(1, total_beads)) * 100.0, 1),
            }
        )

    time_estimate = estimate_assembly_time(grid=grid, unique_colors=len(bom))
    eff_w = time_estimate.get("effective_size", {}).get("width", len(grid[0]) if grid else 0)
    eff_h = time_estimate.get("effective_size", {}).get("height", len(grid))

    return JSONResponse(
        {
            "total_beads": total_beads,
            "unique_colors": len(bom),
            "bom": bom,
            "physical_size_cm": {
                "mini_26mm": {"width": round(eff_w * 0.26, 1), "height": round(eff_h * 0.26, 1)},
                "standard_50mm": {"width": round(eff_w * 0.50, 1), "height": round(eff_h * 0.50, 1)},
            },
            "time_estimate": time_estimate,
        }
    )


# ---------------------------------------------------------------------------
# AI 拼豆对话智能体与配置 API
# ---------------------------------------------------------------------------
async def api_agent_get_config(request: Request) -> JSONResponse:
    _touch_activity()
    return JSONResponse(get_public_agent_config())


async def api_agent_save_config(request: Request) -> JSONResponse:
    _touch_activity()
    body = await request.json()
    save_agent_config(body)
    return JSONResponse(get_public_agent_config())


async def api_agent_test(request: Request) -> JSONResponse:
    """在不强制保存或保存前测试大模型 / Tavily 连通性."""
    _touch_activity()
    body = await request.json()
    target = body.get("target", "llm")
    merged_cfg = load_agent_config()

    for k, v in body.items():
        if k == "target":
            continue
        if k in ("api_key", "tavily_api_key") and (not v or str(v).startswith("****")):
            continue
        merged_cfg[k] = v

    try:
        if target == "tavily":
            res = await asyncio.to_thread(tavily_search, "皮卡丘 像素画", merged_cfg, 2, True)
            return JSONResponse(
                {
                    "ok": True,
                    "message": f"Tavily 搜索连通正常（返回 {len(res['results'])} 条网页与 {len(res['images'])} 张参考图）",
                }
            )
        reply = await asyncio.to_thread(test_llm_connectivity, merged_cfg)
        return JSONResponse({"ok": True, "message": f"模型响应正常：{reply}"})
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


async def api_agent_chat(request: Request) -> JSONResponse:
    _touch_activity()
    body = await request.json()
    messages = body.get("messages") or []
    canvas_context = body.get("canvas_context") or {}
    recent_candidates = body.get("recent_candidates") or []

    try:
        result = await asyncio.to_thread(
            run_agent_turn,
            messages,
            canvas_context,
            recent_candidates,
            _store_image,
            _get_image,
            _image_to_data_url,
        )
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_agent_apply_candidate(request: Request) -> JSONResponse:
    """将推荐卡片中的任意候选图一键生成全套三档拼豆图纸并加载到主画板."""
    _touch_activity()
    body = await request.json()
    img_id = body.get("image_id")
    img = IMAGE_STORE.get(img_id)
    if img is None:
        return JSONResponse({"error": "该候选图像缓存已过期，请重新向助手发起检索"}, status_code=404)

    palette_id = body.get("palette_id", "mard_96")
    remove_bg = bool(body.get("remove_bg", True))
    active_quality = body.get("quality", "hd")

    tiers = await asyncio.to_thread(
        generate_all_tiers_summary,
        img,
        palette_id,
        remove_bg,
    )
    return JSONResponse(
        {
            "image_id": img_id,
            "source_width": img.size[0],
            "source_height": img.size[1],
            "source_data_url": _image_to_data_url(img),
            "tiers": tiers,
            "active_quality": active_quality,
            "palette_id": palette_id,
            "remove_bg": remove_bg,
        }
    )


# ---------------------------------------------------------------------------
# 微信 ClawBot 扫码连接与状态管理 API
# ---------------------------------------------------------------------------
async def api_wechat_status(request: Request) -> JSONResponse:
    _touch_activity()
    return JSONResponse(WECHAT_BOT.get_public_status())


async def api_wechat_login_qr(request: Request) -> JSONResponse:
    _touch_activity()
    try:
        body = await request.json()
    except Exception:
        body = {}
    force = bool(body.get("force", False))
    try:
        status = await asyncio.to_thread(WECHAT_BOT.start_qr_login, force)
        return JSONResponse(status)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_wechat_verify_code(request: Request) -> JSONResponse:
    _touch_activity()
    body = await request.json()
    code = str(body.get("code") or "").strip()
    if not code:
        return JSONResponse({"error": "请输入手机微信界面显示的配对数字"}, status_code=400)
    try:
        status = WECHAT_BOT.submit_verify_code(code)
        return JSONResponse(status)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


async def api_wechat_disconnect(request: Request) -> JSONResponse:
    _touch_activity()
    status = await asyncio.to_thread(WECHAT_BOT.disconnect)
    return JSONResponse(status)


async def api_export_png(request: Request) -> Response:
    _touch_activity()
    body = await request.json()
    pattern = body["pattern"]
    skill_level = body.get("skill_level", "standard")
    bead_style = body.get("bead_style", "code_block")
    png_bytes = export_blueprint_png(pattern=pattern, skill_level=skill_level, bead_style=bead_style)
    return Response(png_bytes, media_type="image/png")


async def api_export_xlsx(request: Request) -> Response:
    _touch_activity()
    body = await request.json()
    pattern = body["pattern"]
    xlsx_bytes = export_bom_xlsx(pattern=pattern)
    return Response(
        xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


async def api_session_stream(request: Request) -> StreamingResponse:
    client_id = uuid.uuid4().hex[:10]
    client_queue: deque[str] = deque()
    ACTIVE_CLIENTS.add(client_id)
    with CLIENT_QUEUES_LOCK:
        CLIENT_EVENT_QUEUES[client_id] = client_queue
    _touch_activity()

    async def event_generator():
        global LAST_ACTIVITY_TIME
        ticks = 0
        try:
            yield "retry: 1000\ndata: connected\n\n"
            while not SHUTDOWN_EVENT.is_set():
                if await request.is_disconnected():
                    break
                pending_frames = []
                with CLIENT_QUEUES_LOCK:
                    while client_queue:
                        pending_frames.append(client_queue.popleft())
                for frame in pending_frames:
                    LAST_ACTIVITY_TIME = time.time()
                    yield frame

                await asyncio.sleep(0.25)
                ticks += 1
                if ticks >= 8:
                    ticks = 0
                    LAST_ACTIVITY_TIME = time.time()
                    yield ": keepalive\n\n"
        finally:
            ACTIVE_CLIENTS.discard(client_id)
            with CLIENT_QUEUES_LOCK:
                CLIENT_EVENT_QUEUES.pop(client_id, None)
            LAST_ACTIVITY_TIME = time.time()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def api_heartbeat(request: Request) -> JSONResponse:
    _touch_activity()
    return JSONResponse({"ok": True})


async def api_window_closed(request: Request) -> JSONResponse:
    global WINDOW_CLOSE_BEACON_AT
    WINDOW_CLOSE_BEACON_AT = time.time()
    return JSONResponse({"closing": True})


starlette_app = Starlette(
    routes=[
        Route("/", homepage),
        Route("/favicon.ico", favicon_ico),
        Route("/api/health", api_health),
        Route("/api/init", api_init),
        Route("/api/load_sample", api_load_sample, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/recompute", api_recompute, methods=["POST"]),
        Route("/api/reestimate", api_reestimate, methods=["POST"]),
        Route("/api/agent/config", api_agent_get_config, methods=["GET"]),
        Route("/api/agent/config", api_agent_save_config, methods=["POST"]),
        Route("/api/agent/test", api_agent_test, methods=["POST"]),
        Route("/api/agent/chat", api_agent_chat, methods=["POST"]),
        Route("/api/agent/apply_candidate", api_agent_apply_candidate, methods=["POST"]),
        Route("/api/wechat/status", api_wechat_status, methods=["GET"]),
        Route("/api/wechat/login_qr", api_wechat_login_qr, methods=["POST"]),
        Route("/api/wechat/verify_code", api_wechat_verify_code, methods=["POST"]),
        Route("/api/wechat/disconnect", api_wechat_disconnect, methods=["POST"]),
        Route("/api/export/png", api_export_png, methods=["POST"]),
        Route("/api/export/xlsx", api_export_xlsx, methods=["POST"]),
        Route("/api/session_stream", api_session_stream),
        Route("/api/heartbeat", api_heartbeat, methods=["POST"]),
        Route("/api/window_closed", api_window_closed, methods=["POST"]),
        Mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui"),
    ]
)


# ---------------------------------------------------------------------------
# 桌面窗口宿主生命周期管理
# ---------------------------------------------------------------------------
def _pick_local_port(preferred: int = 18680) -> int:
    for candidate in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", candidate))
                return int(s.getsockname()[1])
        except OSError:
            continue
    raise RuntimeError("无法分配本地监听端口")


def _is_port_already_running_studio(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.35) as sock:
            sock.sendall(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            resp = sock.recv(512).decode("utf-8", errors="ignore")
            return "beadcraft_studio" in resp
    except OSError:
        return False


def _wait_tcp_listening(port: int, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.35):
                return True
        except OSError:
            time.sleep(0.06)
    return False


def _find_chromium_app_binary() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _open_app_window(url: str) -> None:
    browser_bin = _find_chromium_app_binary()
    if browser_bin:
        RUNTIME_DIR.mkdir(exist_ok=True)
        cmd = [
            browser_bin,
            f"--app={url}",
            f"--user-data-dir={RUNTIME_DIR}",
            "--window-size=1440,900",
            "--no-proxy-server",
            "--proxy-bypass-list=<-loopback>",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ]
        subprocess.Popen(cmd)
    else:
        webbrowser.open(url)


def launch_desktop_app(port: int = 0) -> None:
    preferred_port = port if port > 0 else 18680
    if _is_port_already_running_studio(preferred_port):
        _open_app_window(f"http://127.0.0.1:{preferred_port}")
        return

    actual_port = _pick_local_port(preferred_port)
    url = f"http://127.0.0.1:{actual_port}"

    config = uvicorn.Config(
        starlette_app,
        host="127.0.0.1",
        port=actual_port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not _wait_tcp_listening(actual_port, timeout_s=10.0):
        raise RuntimeError("拼豆工坊本地图形计算服务启动超时")

    boot_time = time.time()
    _open_app_window(url)

    zero_clients_since: float | None = None

    while not SHUTDOWN_EVENT.is_set():
        time.sleep(0.4)
        now = time.time()

        if not CLIENT_CONNECTED_ONCE:
            if now - boot_time > 60.0:
                break
            continue

        if len(ACTIVE_CLIENTS) > 0:
            zero_clients_since = None
            continue

        if zero_clients_since is None:
            zero_clients_since = now
            continue

        idle_disconnected = now - zero_clients_since
        since_last_touch = now - LAST_ACTIVITY_TIME

        if WINDOW_CLOSE_BEACON_AT > 0 and idle_disconnected >= 2.5 and since_last_touch >= 2.0:
            break

        if idle_disconnected >= 10.0 and since_last_touch >= 10.0:
            break

    SHUTDOWN_EVENT.set()
    WECHAT_BOT.stop_background_threads()
    server.should_exit = True
    time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser(description="拼豆工坊 BeadCraft Studio")
    parser.add_argument("--headless", action="store_true", help="仅启动后台服务（用于自动化测试或调试）")
    parser.add_argument("--port", type=int, default=0, help="指定监听端口")
    args = parser.parse_args()

    if args.headless:
        port = args.port if args.port > 0 else 18680
        uvicorn.run(starlette_app, host="127.0.0.1", port=port, log_level="info")
    else:
        try:
            launch_desktop_app(port=args.port)
        except Exception as exc:
            RUNTIME_DIR.mkdir(exist_ok=True)
            (RUNTIME_DIR / "crash.log").write_text(traceback.format_exc(), encoding="utf-8")
            ctypes.windll.user32.MessageBoxW(
                0,
                f"拼豆工坊启动遇到问题：\n{exc}",
                "拼豆工坊错误提示",
                0x10,
            )


if __name__ == "__main__":
    main()
