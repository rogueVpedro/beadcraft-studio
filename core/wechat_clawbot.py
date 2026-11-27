"""腾讯官方微信 ClawBot (iLink Bot API v2.4.10) 扫码登录、长轮询监听与 AES-128-ECB 图文收发引擎.

完整支持：
1. 获取微信官方 iLink 登录二维码 (get_bot_qrcode) 并本地渲染高清二维码图片 (Data URL)
2. 扫码状态长轮询 (get_qrcode_status)：兼容 wait / scaned / scaned_but_redirect (IDC 跨区跳转) /
   need_verifycode (手机端数字配对码校验) / expired 自动刷新 / confirmed 持久化凭证
3. 后台长轮询消息监听 (getupdates)：支持接收微信文字、语音转文字 (voice_item.text) 及微信相册发来的原图 (AES-128-ECB 解密)
4. 自动联动拼豆工坊智能体：
   - 收到文字/语音需求 -> 调用大模型 + Tavily 联网检索生成拼豆方案 -> 实时同步刷新桌面画布，并将【文字工时评估 + 高清可打印施工图纸 PNG】直接发回手机微信！
   - 收到手机发来的图片 -> 直接将该图转换为简略/高清/还原三档拼豆图纸 -> 同步刷新桌面画布，并将生成的【高清施工图纸 PNG + 三档预估时长对比】直接发回手机微信！
"""

from __future__ import annotations

import base64
from collections import deque
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote
import uuid

from PIL import Image
import qrcode
import requests

from core.agent import render_bead_preview_thumbnail, run_agent_turn
from core.exporter import export_blueprint_png
from core.generator import generate_all_tiers_summary, load_normalized_rgba

STATE_PATH = Path(__file__).resolve().parent.parent / ".wechat_clawbot_state.json"

FIXED_QR_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
DEFAULT_BOT_TYPE = "3"
CHANNEL_VERSION = "2.4.10"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 10)  # 0x0002040A = 132106
STALE_TOKEN_ERRCODE = -14

# 无损转换 uint64 消息 ID 字段，避免大整数精度丢失
_UINT64_ID_RE = re.compile(r'("(?:message_id|msg_id|svr_id)"\s*:\s*)(-?\d+)')


def parse_ilink_json(raw_text: str) -> Dict[str, Any]:
    safe_text = _UINT64_ID_RE.sub(r'\1"\2"', raw_text)
    return json.loads(safe_text)


def _random_wechat_uin() -> str:
    uint32_val = struct.unpack(">I", os.urandom(4))[0]
    return base64.b64encode(str(uint32_val).encode("utf-8")).decode("ascii")


def _common_headers() -> Dict[str, str]:
    return {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
    }


def _post_headers(token: Optional[str] = None) -> Dict[str, str]:
    hdrs = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
        **_common_headers(),
    }
    if token and token.strip():
        hdrs["Authorization"] = f"Bearer {token.strip()}"
    return hdrs


def _base_info() -> Dict[str, str]:
    return {
        "channel_version": CHANNEL_VERSION,
        "bot_agent": "OpenClaw",
    }


def _direct_or_fallback_request(method: str, url: str, **kwargs) -> requests.Response:
    """微信官方国内域名优先直连（避免全局海外代理导致跨区延迟），直连网络异常时自动回退系统代理."""
    try:
        return requests.request(method, url, proxies={"http": "", "https": ""}, **kwargs)
    except requests.RequestException:
        return requests.request(method, url, **kwargs)


# ---------------------------------------------------------------------------
# AES-128-ECB 媒体加解密工具 (严格对齐官方 aes-ecb.ts & pic-decrypt.ts)
# ---------------------------------------------------------------------------
def aes_ecb_encrypt(plaintext: bytes, key_16: bytes) -> bytes:
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(key_16), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(padded) + enc.finalize()


def aes_ecb_decrypt(ciphertext: bytes, key_16: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key_16), modes.ECB())
    dec = cipher.decryptor()
    padded = dec.update(ciphertext) + dec.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def aes_ecb_padded_size(raw_size: int) -> int:
    return ((raw_size // 16) + 1) * 16


def parse_inbound_aes_key(aes_key_b64: str) -> bytes:
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        ascii_hex = decoded.decode("ascii")
        return bytes.fromhex(ascii_hex)
    raise ValueError(f"Unsupported inbound aes_key length: {len(decoded)}")


def render_qr_png_data_url(qr_content: str) -> str:
    """使用纯本地 qrcode + Pillow 生成高对比度扫码 PNG Data URL."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(qr_content)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="#0F141C", back_color="#FFFFFF").convert("RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# WeChat ClawBot 会话与后台监听管理器
# ---------------------------------------------------------------------------
class WeChatClawBotManager:
    def __init__(
        self,
        store_image_fn: Callable[[Image.Image], str],
        get_image_fn: Callable[[str], Optional[Image.Image]],
        image_to_data_url_fn: Callable[[Image.Image], str],
        broadcast_event_fn: Callable[[str, Dict[str, Any]], None],
    ) -> None:
        self._store_image = store_image_fn
        self._get_image = get_image_fn
        self._image_to_data_url = image_to_data_url_fn
        self._broadcast = broadcast_event_fn

        self._lock = threading.Lock()
        self.state = self._load_state()

        # 登录扫码会话状态
        self.login_session: Optional[Dict[str, Any]] = None
        self._qr_poll_stop = threading.Event()
        self._qr_poll_thread: Optional[threading.Thread] = None

        # 运行期消息监听线程与每用户对话记忆
        self._monitor_stop = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self.monitor_running: bool = False
        self.status_message: str = "未连接微信"
        self.last_error: str = ""
        self.message_count: int = 0

        self._seen_msg_ids: deque[str] = deque(maxlen=256)
        self._user_histories: Dict[str, List[Dict[str, str]]] = {}
        self._user_candidates: Dict[str, List[Dict[str, Any]]] = {}
        self._user_canvas_ctx: Dict[str, Dict[str, Any]] = {}
        self._typing_tickets: Dict[str, str] = {}

        # 若本地已有历史授权 token，自动在后台恢复微信连接
        if self.state.get("bot_token"):
            self.start_monitor_loop()

    # ------------------------------------------------------------------
    # 本地状态读写 (.wechat_clawbot_state.json)
    # ------------------------------------------------------------------
    def _empty_state(self) -> Dict[str, Any]:
        return {
            "bot_token": "",
            "base_url": FIXED_QR_BASE_URL,
            "cdn_base_url": DEFAULT_CDN_BASE_URL,
            "ilink_bot_id": "",
            "ilink_user_id": "",
            "get_updates_buf": "",
            "contexts": {},
            "connected_at": 0,
        }

    def _load_state(self) -> Dict[str, Any]:
        st = self._empty_state()
        if STATE_PATH.exists():
            try:
                saved = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    st.update(saved)
            except Exception:
                pass
        return st

    def _save_state(self) -> None:
        try:
            STATE_PATH.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_public_status(self) -> Dict[str, Any]:
        connected = bool(self.state.get("bot_token"))
        login_info = None
        if self.login_session:
            login_info = {
                "status": self.login_session.get("status", "wait"),
                "message": self.login_session.get("message", ""),
                "qr_data_url": self.login_session.get("qr_data_url", ""),
                "qrcode_url": self.login_session.get("qrcode_url", ""),
                "need_verify_code": self.login_session.get("status") == "need_verifycode",
            }
        return {
            "connected": connected,
            "monitor_running": self.monitor_running,
            "bot_id": self.state.get("ilink_bot_id", ""),
            "user_id": self.state.get("ilink_user_id", ""),
            "status_message": self.status_message if connected else (login_info["message"] if login_info else self.status_message),
            "last_error": self.last_error,
            "message_count": self.message_count,
            "login": login_info,
        }

    # ------------------------------------------------------------------
    # 1. 发起二维码获取与扫码状态轮询
    # ------------------------------------------------------------------
    def _fetch_new_qr(self) -> Dict[str, str]:
        local_tokens = [self.state["bot_token"]] if self.state.get("bot_token") else []
        url = f"{FIXED_QR_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={DEFAULT_BOT_TYPE}"
        resp = _direct_or_fallback_request(
            "POST",
            url,
            data=json.dumps({"local_token_list": local_tokens}),
            headers=_post_headers(),
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        qrcode_val = str(data.get("qrcode") or "").strip()
        qrcode_url = str(data.get("qrcode_img_content") or "").strip()
        if not qrcode_val or not qrcode_url:
            raise RuntimeError(f"未获取到有效微信二维码: {str(data)[:160]}")
        return {
            "qrcode": qrcode_val,
            "qrcode_url": qrcode_url,
            "qr_data_url": render_qr_png_data_url(qrcode_url),
        }

    def start_qr_login(self, force_refresh: bool = False) -> Dict[str, Any]:
        # 若已有新鲜未过期二维码且未要求强制刷新，直接复用
        if (
            not force_refresh
            and self.login_session
            and time.time() - self.login_session.get("started_at", 0) < 240
            and self.login_session.get("status") in ("wait", "scaned", "need_verifycode")
        ):
            return self.get_public_status()

        self._qr_poll_stop.set()
        if self._qr_poll_thread and self._qr_poll_thread.is_alive():
            self._qr_poll_thread.join(timeout=1.0)

        qr_bundle = self._fetch_new_qr()
        self.last_error = ""
        self.login_session = {
            "id": uuid.uuid4().hex[:10],
            "qrcode": qr_bundle["qrcode"],
            "qrcode_url": qr_bundle["qrcode_url"],
            "qr_data_url": qr_bundle["qr_data_url"],
            "poll_base_url": FIXED_QR_BASE_URL,
            "status": "wait",
            "message": "请使用手机微信扫描二维码（需微信 8.0.70+ 支持 ClawBot）",
            "pending_verify_code": None,
            "started_at": time.time(),
            "refresh_count": 0,
        }

        self._qr_poll_stop = threading.Event()
        self._qr_poll_thread = threading.Thread(target=self._qr_poll_worker, daemon=True)
        self._qr_poll_thread.start()
        return self.get_public_status()

    def submit_verify_code(self, code: str) -> Dict[str, Any]:
        if not self.login_session:
            raise ValueError("当前没有进行中的扫码会话")
        self.login_session["pending_verify_code"] = code.strip()
        self.login_session["message"] = "正在提交配对验证码..."
        return self.get_public_status()

    def _qr_poll_worker(self) -> None:
        deadline = time.time() + 480.0
        while not self._qr_poll_stop.is_set() and time.time() < deadline:
            sess = self.login_session
            if not sess:
                return

            base_u = sess["poll_base_url"].rstrip("/")
            endpoint = f"{base_u}/ilink/bot/get_qrcode_status?qrcode={quote(sess['qrcode'], safe='')}"
            if sess.get("pending_verify_code"):
                endpoint += f"&verify_code={quote(sess['pending_verify_code'], safe='')}"

            try:
                resp = _direct_or_fallback_request(
                    "GET",
                    endpoint,
                    headers=_common_headers(),
                    timeout=36,
                )
                if not resp.ok:
                    time.sleep(1.2)
                    continue
                data = resp.json()
            except requests.Timeout:
                continue
            except Exception:
                time.sleep(1.5)
                continue

            st = str(data.get("status") or "wait")
            sess["status"] = st

            if st == "wait":
                sess["message"] = "请使用手机微信扫描二维码连接拼豆工坊"
            elif st == "scaned":
                sess["pending_verify_code"] = None
                sess["message"] = "已扫码！请在手机微信上点击「确认连接」..."
                self._broadcast("wechat_status", self.get_public_status())
            elif st == "scaned_but_redirect":
                r_host = str(data.get("redirect_host") or "").strip()
                if r_host:
                    sess["poll_base_url"] = r_host if r_host.startswith("http") else f"https://{r_host}"
                sess["message"] = "已扫码，正在同步微信节点确认..."
                self._broadcast("wechat_status", self.get_public_status())
                continue
            elif st == "need_verifycode":
                sess["message"] = (
                    "验证码不匹配，请重新输入手机微信上的数字"
                    if sess.get("pending_verify_code")
                    else "请在下方输入手机微信界面显示的配对数字"
                )
                sess["pending_verify_code"] = None
                self._broadcast("wechat_status", self.get_public_status())
                time.sleep(1.0)
                continue
            elif st in ("expired", "verify_code_blocked"):
                sess["refresh_count"] = int(sess.get("refresh_count", 0)) + 1
                if sess["refresh_count"] > 3:
                    sess["message"] = "二维码多次过期，请点击「刷新二维码」重试"
                    self._broadcast("wechat_status", self.get_public_status())
                    return
                try:
                    fresh = self._fetch_new_qr()
                    sess.update(fresh)
                    sess["poll_base_url"] = FIXED_QR_BASE_URL
                    sess["status"] = "wait"
                    sess["message"] = "二维码已自动刷新，请重新使用微信扫描"
                    self._broadcast("wechat_status", self.get_public_status())
                except Exception as exc:
                    sess["message"] = f"自动刷新二维码失败：{exc}"
                    return
            elif st == "binded_redirect":
                sess["message"] = "该微信 ClawBot 已与本机绑定，正在恢复监听..."
                self.login_session = None
                if self.state.get("bot_token"):
                    self.start_monitor_loop()
                self._broadcast("wechat_status", self.get_public_status())
                return
            elif st == "confirmed":
                bot_token = str(data.get("bot_token") or "").strip()
                bot_id = str(data.get("ilink_bot_id") or "").strip()
                base_url = str(data.get("baseurl") or FIXED_QR_BASE_URL).strip()
                user_id = str(data.get("ilink_user_id") or "").strip()

                with self._lock:
                    self.state["bot_token"] = bot_token
                    self.state["ilink_bot_id"] = bot_id
                    self.state["base_url"] = base_url or FIXED_QR_BASE_URL
                    self.state["ilink_user_id"] = user_id
                    self.state["get_updates_buf"] = ""
                    self.state["connected_at"] = int(time.time())
                    self._save_state()

                self.login_session = None
                self.status_message = "微信 ClawBot 已连接 · 实时监听中"
                self.start_monitor_loop()
                self._broadcast("wechat_status", self.get_public_status())
                return

            time.sleep(1.0)

    # ------------------------------------------------------------------
    # 2. 断开连接 / 启停后台 getUpdates 监听循环
    # ------------------------------------------------------------------
    def disconnect(self) -> Dict[str, Any]:
        self._qr_poll_stop.set()
        self._monitor_stop.set()
        self.login_session = None

        token = self.state.get("bot_token")
        base_url = (self.state.get("base_url") or FIXED_QR_BASE_URL).rstrip("/")
        if token:
            try:
                _direct_or_fallback_request(
                    "POST",
                    f"{base_url}/ilink/bot/msg/notifystop",
                    data=json.dumps({"base_info": _base_info()}),
                    headers=_post_headers(token),
                    timeout=5,
                )
            except Exception:
                pass

        with self._lock:
            self.state = self._empty_state()
            self._save_state()

        self.monitor_running = False
        self.status_message = "已断开微信连接"
        self.last_error = ""
        st = self.get_public_status()
        self._broadcast("wechat_status", st)
        return st

    def stop_background_threads(self) -> None:
        """应用窗口退出时平滑停止后台轮询线程，保留本地已授权 bot_token 以便下次启动自动重连."""
        self._qr_poll_stop.set()
        self._monitor_stop.set()

    def start_monitor_loop(self) -> None:
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        if not self.state.get("bot_token"):
            return

        self._monitor_stop = threading.Event()
        self._monitor_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        self._monitor_thread.start()

    def _notify_start(self) -> None:
        token = self.state.get("bot_token")
        base_url = (self.state.get("base_url") or FIXED_QR_BASE_URL).rstrip("/")
        if not token:
            return
        try:
            _direct_or_fallback_request(
                "POST",
                f"{base_url}/ilink/bot/msg/notifystart",
                data=json.dumps({"base_info": _base_info()}),
                headers=_post_headers(token),
                timeout=8,
            )
        except Exception:
            pass

    def _monitor_worker(self) -> None:
        self.monitor_running = True
        self.status_message = "微信 ClawBot 在线 · 手机发消息或发图即可生成拼豆图"
        self._notify_start()
        self._broadcast("wechat_status", self.get_public_status())

        consecutive_failures = 0
        poll_timeout_s = 35.0

        while not self._monitor_stop.is_set():
            token = self.state.get("bot_token")
            if not token:
                break
            base_url = (self.state.get("base_url") or FIXED_QR_BASE_URL).rstrip("/")
            sync_buf = self.state.get("get_updates_buf", "")

            try:
                resp = _direct_or_fallback_request(
                    "POST",
                    f"{base_url}/ilink/bot/getupdates",
                    data=json.dumps({"get_updates_buf": sync_buf, "base_info": _base_info()}),
                    headers=_post_headers(token),
                    timeout=poll_timeout_s + 5.0,
                )
                if not resp.ok:
                    consecutive_failures += 1
                    time.sleep(min(20.0, 2.0 * consecutive_failures))
                    continue

                data = parse_ilink_json(resp.text)
            except requests.Timeout:
                # 长轮询超时属于正常心跳周期，立即进入下一轮
                consecutive_failures = 0
                continue
            except Exception as exc:
                consecutive_failures += 1
                self.last_error = f"网络波动重连中: {exc}"
                time.sleep(3.0 if consecutive_failures < 3 else 15.0)
                continue

            if data.get("longpolling_timeout_ms") and int(data["longpolling_timeout_ms"]) > 0:
                poll_timeout_s = max(10.0, min(90.0, int(data["longpolling_timeout_ms"]) / 1000.0))

            ret = data.get("ret", 0)
            errcode = data.get("errcode", 0)
            if (ret and ret != 0) or (errcode and errcode != 0):
                if ret == STALE_TOKEN_ERRCODE or errcode == STALE_TOKEN_ERRCODE:
                    # 凭证已失效 (-14)，停止轮询避免触发微信风控，提示重新扫码
                    with self._lock:
                        self.state["bot_token"] = ""
                        self._save_state()
                    self.last_error = "微信登录凭证已过期，请重新扫码连接"
                    self.status_message = "登录已过期，请重新扫码"
                    break

                consecutive_failures += 1
                time.sleep(3.0 if consecutive_failures < 3 else 25.0)
                continue

            consecutive_failures = 0
            self.last_error = ""

            new_buf = data.get("get_updates_buf")
            if isinstance(new_buf, str) and new_buf != sync_buf:
                with self._lock:
                    self.state["get_updates_buf"] = new_buf
                    self._save_state()

            for msg in data.get("msgs") or []:
                if self._monitor_stop.is_set():
                    break
                # 仅处理用户发来的入站消息 (MessageType.USER == 1)
                if msg.get("message_type") != 1:
                    continue
                msg_id = str(msg.get("message_id") or "")
                if msg_id and msg_id in self._seen_msg_ids:
                    continue
                if msg_id:
                    self._seen_msg_ids.append(msg_id)

                threading.Thread(target=self._handle_inbound_message, args=(msg,), daemon=True).start()

        self.monitor_running = False
        self._broadcast("wechat_status", self.get_public_status())

    # ------------------------------------------------------------------
    # 3. 发送「对方正在输入...」、发送文本与 AES-128-ECB 加密发送拼豆图纸图片
    # ------------------------------------------------------------------
    def _send_typing(self, to_user_id: str, context_token: str, status: int = 1) -> None:
        token = self.state.get("bot_token")
        base_url = (self.state.get("base_url") or FIXED_QR_BASE_URL).rstrip("/")
        if not token or not to_user_id:
            return
        try:
            ticket = self._typing_tickets.get(to_user_id)
            if not ticket:
                cfg_resp = _direct_or_fallback_request(
                    "POST",
                    f"{base_url}/ilink/bot/getconfig",
                    data=json.dumps(
                        {
                            "ilink_user_id": to_user_id,
                            "context_token": context_token,
                            "base_info": _base_info(),
                        }
                    ),
                    headers=_post_headers(token),
                    timeout=8,
                )
                if cfg_resp.ok:
                    ticket = str(cfg_resp.json().get("typing_ticket") or "")
                    if ticket:
                        self._typing_tickets[to_user_id] = ticket
            if ticket:
                _direct_or_fallback_request(
                    "POST",
                    f"{base_url}/ilink/bot/sendtyping",
                    data=json.dumps(
                        {
                            "ilink_user_id": to_user_id,
                            "typing_ticket": ticket,
                            "status": status,
                            "base_info": _base_info(),
                        }
                    ),
                    headers=_post_headers(token),
                    timeout=8,
                )
        except Exception:
            pass

    def send_text_to_wechat(self, to_user_id: str, text: str, context_token: str = "") -> None:
        token = self.state.get("bot_token")
        base_url = (self.state.get("base_url") or FIXED_QR_BASE_URL).rstrip("/")
        if not token or not text.strip():
            return

        payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": f"beadcraft-{uuid.uuid4().hex[:18]}",
                "message_type": 2,
                "message_state": 2,
                "item_list": [{"type": 1, "text_item": {"text": text}}],
                **({"context_token": context_token} if context_token else {}),
            },
            "base_info": _base_info(),
        }
        resp = _direct_or_fallback_request(
            "POST",
            f"{base_url}/ilink/bot/sendmessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=_post_headers(token),
            timeout=15,
        )
        resp.raise_for_status()

    def send_image_bytes_to_wechat(self, to_user_id: str, png_bytes: bytes, context_token: str = "") -> None:
        """将生成的拼豆高清施工图纸经 AES-128-ECB 加密上传至微信官方 CDN 并投递到聊天窗口."""
        token = self.state.get("bot_token")
        base_url = (self.state.get("base_url") or FIXED_QR_BASE_URL).rstrip("/")
        cdn_base = (self.state.get("cdn_base_url") or DEFAULT_CDN_BASE_URL).rstrip("/")
        if not token or not png_bytes:
            return

        rawsize = len(png_bytes)
        raw_md5 = hashlib.md5(png_bytes).hexdigest()
        cipher_size = aes_ecb_padded_size(rawsize)
        filekey = os.urandom(16).hex()
        aeskey_bytes = os.urandom(16)
        aeskey_hex = aeskey_bytes.hex()

        up_req = {
            "filekey": filekey,
            "media_type": 1,  # UploadMediaType.IMAGE
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": raw_md5,
            "filesize": cipher_size,
            "no_need_thumb": True,
            "aeskey": aeskey_hex,
            "base_info": _base_info(),
        }
        up_resp = _direct_or_fallback_request(
            "POST",
            f"{base_url}/ilink/bot/getuploadurl",
            data=json.dumps(up_req),
            headers=_post_headers(token),
            timeout=15,
        )
        up_resp.raise_for_status()
        up_data = up_resp.json()

        upload_full_url = str(up_data.get("upload_full_url") or "").strip()
        upload_param = str(up_data.get("upload_param") or "").strip()
        if upload_full_url:
            cdn_url = upload_full_url
        elif upload_param:
            cdn_url = f"{cdn_base}/upload?encrypted_query_param={quote(upload_param, safe='')}&filekey={quote(filekey, safe='')}"
        else:
            raise RuntimeError("getUploadUrl 未返回有效上传地址")

        ciphertext = aes_ecb_encrypt(png_bytes, aeskey_bytes)
        cdn_resp = _direct_or_fallback_request(
            "POST",
            cdn_url,
            data=ciphertext,
            headers={"Content-Type": "application/octet-stream"},
            timeout=25,
        )
        cdn_resp.raise_for_status()
        download_param = cdn_resp.headers.get("x-encrypted-param")
        if not download_param:
            raise RuntimeError("微信 CDN 上传响应缺少 x-encrypted-param")

        # 注意：官方 send.ts 中 ImageItem.media.aes_key 是对 32 位 hex 字符串做 UTF-8 base64
        img_msg_payload = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": f"beadcraft-img-{uuid.uuid4().hex[:16]}",
                "message_type": 2,
                "message_state": 2,
                "item_list": [
                    {
                        "type": 2,
                        "image_item": {
                            "media": {
                                "encrypt_query_param": download_param,
                                "aes_key": base64.b64encode(aeskey_hex.encode("ascii")).decode("ascii"),
                                "encrypt_type": 1,
                            },
                            "mid_size": cipher_size,
                        },
                    }
                ],
                **({"context_token": context_token} if context_token else {}),
            },
            "base_info": _base_info(),
        }
        send_resp = _direct_or_fallback_request(
            "POST",
            f"{base_url}/ilink/bot/sendmessage",
            data=json.dumps(img_msg_payload),
            headers=_post_headers(token),
            timeout=15,
        )
        send_resp.raise_for_status()

    def _download_inbound_image(self, image_item: Dict[str, Any]) -> Optional[bytes]:
        """下载并解密用户在手机微信中发来的图片."""
        media = image_item.get("media") or {}
        enc_param = str(media.get("encrypt_query_param") or "").strip()
        full_url = str(media.get("full_url") or "").strip()
        cdn_base = (self.state.get("cdn_base_url") or DEFAULT_CDN_BASE_URL).rstrip("/")

        if full_url:
            dl_url = full_url
        elif enc_param:
            dl_url = f"{cdn_base}/download?encrypted_query_param={quote(enc_param, safe='')}"
        else:
            return None

        resp = _direct_or_fallback_request("GET", dl_url, timeout=20)
        if not resp.ok:
            return None
        raw_bytes = resp.content

        hex_key = str(image_item.get("aeskey") or "").strip()
        b64_key = str(media.get("aes_key") or "").strip()
        if hex_key:
            return aes_ecb_decrypt(raw_bytes, bytes.fromhex(hex_key))
        if b64_key:
            return aes_ecb_decrypt(raw_bytes, parse_inbound_aes_key(b64_key))
        return raw_bytes

    # ------------------------------------------------------------------
    # 4. 处理单条入站微信消息（联动拼豆智能体 + 桌面同步 + 回传图纸）
    # ------------------------------------------------------------------
    def _handle_inbound_message(self, msg: Dict[str, Any]) -> None:
        from_user = str(msg.get("from_user_id") or "").strip()
        ctx_token = str(msg.get("context_token") or "").strip()
        if not from_user:
            return

        if ctx_token:
            with self._lock:
                self.state.setdefault("contexts", {})[from_user] = ctx_token
                self._save_state()
        else:
            ctx_token = self.state.get("contexts", {}).get(from_user, "")

        self.message_count += 1
        self._send_typing(from_user, ctx_token, status=1)

        items = msg.get("item_list") or []
        text_parts: List[str] = []
        inbound_img_bytes: Optional[bytes] = None

        for it in items:
            itype = it.get("type")
            if itype == 1 and it.get("text_item", {}).get("text"):
                text_parts.append(str(it["text_item"]["text"]).strip())
            elif itype == 3 and it.get("voice_item", {}).get("text"):
                # 支持微信语音自动转文字指令！
                text_parts.append(str(it["voice_item"]["text"]).strip())
            elif itype == 2 and it.get("image_item"):
                inbound_img_bytes = self._download_inbound_image(it["image_item"])

        user_ctx = self._user_canvas_ctx.setdefault(
            from_user, {"quality": "hd", "palette_id": "mard_96", "remove_bg": True}
        )

        try:
            # 情况 A：用户在微信直接发来了一张照片/表情包 -> 直接转三档拼豆图并回传高清施工图纸！
            if inbound_img_bytes:
                img = load_normalized_rgba(inbound_img_bytes)
                img_id = self._store_image(img)
                q = user_ctx.get("quality", "hd")
                pal_id = user_ctx.get("palette_id", "mard_96")
                rem_bg = bool(user_ctx.get("remove_bg", False))

                tiers = generate_all_tiers_summary(img_rgba=img, palette_id=pal_id, remove_bg=rem_bg)
                chosen = tiers[q]
                src_url = self._image_to_data_url(img)

                user_ctx["image_id"] = img_id
                s_p = tiers["simple"]
                h_p = tiers["hd"]
                f_p = tiers["faithful"]

                reply_txt = (
                    f"已收到您的图片并生成拼豆图纸（已同步显示在桌面端画布）！\n\n"
                    f"• 简略档 ({s_p['grid_width']}×{s_p['grid_height']})：{s_p['total_beads']}颗 / {s_p['unique_colors']}色 · 约 {s_p['time_estimate']['profiles']['standard']['formatted']}\n"
                    f"• 高清档 ({h_p['grid_width']}×{h_p['grid_height']})：{h_p['total_beads']}颗 / {h_p['unique_colors']}色 · 约 {h_p['time_estimate']['profiles']['standard']['formatted']}\n"
                    f"• 还原档 ({f_p['grid_width']}×{f_p['grid_height']})：{f_p['total_beads']}颗 / {f_p['unique_colors']}色 · 约 {f_p['time_estimate']['profiles']['standard']['formatted']}\n\n"
                    f"下方为您奉上【{chosen['quality_name']}档】带色号高清施工图纸（回复“换成简略”或“开启去背景”可随时重出图）："
                )
                self.send_text_to_wechat(from_user, reply_txt, ctx_token)

                blueprint_bytes = export_blueprint_png(chosen, skill_level="standard", bead_style="code_block")
                self.send_image_bytes_to_wechat(from_user, blueprint_bytes, ctx_token)

                auto_apply = {
                    "image_id": img_id,
                    "source_width": img.size[0],
                    "source_height": img.size[1],
                    "source_data_url": src_url,
                    "tiers": tiers,
                    "active_quality": q,
                    "palette_id": pal_id,
                    "remove_bg": rem_bg,
                }
                rec_card = {
                    "image_id": img_id,
                    "title": "微信发图直转方案",
                    "source_domain": "WeChat 手机传图",
                    "quality": q,
                    "quality_name": chosen["quality_name"],
                    "palette_id": pal_id,
                    "remove_bg": rem_bg,
                    "grid_width": chosen["grid_width"],
                    "grid_height": chosen["grid_height"],
                    "total_beads": chosen["total_beads"],
                    "unique_colors": chosen["unique_colors"],
                    "estimated_time": chosen["time_estimate"]["profiles"]["standard"]["formatted"],
                    "bead_preview_url": render_bead_preview_thumbnail(chosen),
                    "source_thumb_url": src_url,
                }
                self._broadcast(
                    "wechat_sync",
                    {
                        "user_text": "[微信传图] 生成拼豆图纸",
                        "reply": reply_txt,
                        "tool_steps": [{"step": "wechat_image", "label": "收到手机微信图片，已完成三档拼豆转换并回传施工图"}],
                        "recommendations": [rec_card],
                        "auto_apply": auto_apply,
                    },
                )
                return

            # 情况 B：用户在微信发送文字或语音指令 -> 调用桌面 AI 拼豆智能体（大模型 + Tavily 联网推荐）
            prompt_text = " ".join(text_parts).strip()
            if not prompt_text:
                return

            hist = self._user_histories.setdefault(from_user, [])
            hist.append({"role": "user", "content": prompt_text})
            if len(hist) > 10:
                del hist[:-10]

            recent_cands = self._user_candidates.get(from_user, [])
            turn_res = run_agent_turn(
                messages=hist,
                canvas_context=user_ctx,
                recent_candidates=recent_cands,
                store_image_fn=self._store_image,
                get_image_fn=self._get_image,
                image_to_data_url_fn=self._image_to_data_url,
            )

            reply_body = str(turn_res.get("reply") or "")
            # 清理简单 Markdown 加粗符号以便微信纯文本阅读更清爽
            clean_wx_reply = reply_body.replace("**", "").replace("`", "")

            recs = turn_res.get("recommendations") or []
            if recs:
                self._user_candidates[from_user] = recs

            auto_ap = turn_res.get("auto_apply")
            if auto_ap:
                user_ctx["image_id"] = auto_ap["image_id"]
                user_ctx["quality"] = auto_ap["active_quality"]
                user_ctx["palette_id"] = auto_ap["palette_id"]
                user_ctx["remove_bg"] = auto_ap["remove_bg"]

            hist.append({"role": "assistant", "content": reply_body})
            self.send_text_to_wechat(from_user, clean_wx_reply, ctx_token)

            # 若本次生成/更新了拼豆图案，自动把高清带色号施工图纸 PNG 直接发回用户微信！
            if auto_ap and auto_ap.get("tiers"):
                active_q = auto_ap.get("active_quality", "hd")
                pat = auto_ap["tiers"].get(active_q) or next(iter(auto_ap["tiers"].values()))
                blueprint_png = export_blueprint_png(pat, skill_level="standard", bead_style="code_block")
                self.send_image_bytes_to_wechat(from_user, blueprint_png, ctx_token)

            # 实时同步推送到桌面端 UI（聊天面板 + 中央拼豆大画板同步刷新！）
            self._broadcast(
                "wechat_sync",
                {
                    "user_text": f"[微信] {prompt_text}",
                    "reply": reply_body,
                    "tool_steps": turn_res.get("tool_steps") or [],
                    "recommendations": recs,
                    "auto_apply": auto_ap,
                },
            )
        except Exception as exc:
            try:
                self.send_text_to_wechat(from_user, f"生成拼豆图时遇到一点问题：{exc}", ctx_token)
            except Exception:
                pass
        finally:
            self._send_typing(from_user, ctx_token, status=2)
