"""拼豆工坊核心算法、AI 对话智能体（自定义大模型 + Tavily 联网推荐）与导出完整测试套件."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw
from starlette.requests import Request

from app import (
    _get_image,
    _image_to_data_url,
    _store_image,
    api_agent_apply_candidate,
    api_export_png,
    api_export_xlsx,
    api_init,
    api_load_sample,
    api_reestimate,
    api_wechat_login_qr,
    api_wechat_status,
    homepage,
)
from core.agent import run_agent_turn
from core.agent_config import CONFIG_PATH, get_public_agent_config, save_agent_config
from core.generator import generate_all_tiers_summary, generate_bead_pattern, load_normalized_rgba
from core.llm_client import extract_json_object, normalize_openai_chat_url
from core.palettes import get_palette
from core.samples import SAMPLE_ITEMS, build_sample_png
from core.wechat_clawbot import (
    STATE_PATH as WECHAT_STATE_PATH,
    WeChatClawBotManager,
    aes_ecb_decrypt,
    aes_ecb_encrypt,
    aes_ecb_padded_size,
    parse_ilink_json,
    parse_inbound_aes_key,
    render_qr_png_data_url,
)


def _run_coro_sync(coro):
    return asyncio.run(coro)


def _make_json_request(method: str, path: str, payload: dict | None = None) -> Request:
    raw = json.dumps(payload).encode("utf-8") if payload is not None else b""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"content-type", b"application/json")],
    }
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def test_palette_perceptual_matching() -> None:
    pal = get_palette("mard_96")
    white_code = pal.colors[pal.match_rgb(252, 252, 252)]["code"]
    black_code = pal.colors[pal.match_rgb(20, 20, 24)]["code"]
    red_code = pal.colors[pal.match_rgb(220, 38, 38)]["code"]
    assert white_code == "H01"
    assert black_code == "H02"
    assert red_code.startswith("F")
    print("[PASS] 1/6 拼豆色卡 CIELAB 感知匹配与 WCAG 对比度准确")


def test_three_qualities_bead_count_and_time_monotonicity() -> None:
    for sample in SAMPLE_ITEMS:
        png = build_sample_png(sample["id"])
        img = load_normalized_rgba(png)
        tiers = generate_all_tiers_summary(img, palette_id="master_144", remove_bg=False)

        b_simple = tiers["simple"]["total_beads"]
        b_hd = tiers["hd"]["total_beads"]
        b_faithful = tiers["faithful"]["total_beads"]
        assert 0 < b_simple < b_hd < b_faithful

        t_simple = tiers["simple"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        t_hd = tiers["hd"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        t_faithful = tiers["faithful"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        assert t_simple < t_hd < t_faithful
    print("[PASS] 2/6 三档画质(简略/高清/还原)豆数梯度与拼豆时长预估验证通过")


def test_non_square_aspect_ratios_and_background_removal() -> None:
    wide_img = Image.new("RGBA", (640, 360), (250, 250, 250, 255))
    draw = ImageDraw.Draw(wide_img)
    draw.ellipse([200, 60, 440, 300], fill=(56, 189, 248, 255))
    draw.ellipse([260, 120, 300, 160], fill=(255, 255, 255, 255))

    pat_full = generate_bead_pattern(wide_img, quality="faithful", remove_bg=False)
    assert pat_full["grid_width"] == 100 and pat_full["grid_height"] == 56

    pat_nobg = generate_bead_pattern(wide_img, quality="hd", remove_bg=True)
    assert pat_nobg["total_beads"] < pat_nobg["grid_width"] * pat_nobg["grid_height"]
    codes_present = {item["code"] for item in pat_nobg["bom"]}
    assert "H01" in codes_present
    print("[PASS] 3/6 非正方形比例适配与智能背景抠除(保留内部高光)验证通过")


def test_llm_helpers_and_secret_masking() -> None:
    assert normalize_openai_chat_url("https://api.deepseek.com") == "https://api.deepseek.com/v1/chat/completions"
    assert normalize_openai_chat_url("https://api.deepseek.com/v1") == "https://api.deepseek.com/v1/chat/completions"
    assert (
        normalize_openai_chat_url("https://open.bigmodel.cn/api/paas/v4")
        == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    )

    reasoning_out = '<think>用户想要1小时拼完的挂件，应选 simple</think>\n```json\n{"action":"search_recommend","quality":"simple"}\n```'
    parsed = extract_json_object(reasoning_out)
    assert parsed is not None and parsed["quality"] == "simple"

    backup_raw = CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else None
    try:
        save_agent_config({"api_key": "sk-secret9988", "tavily_api_key": "tvly-secret7766", "model": "deepseek-chat"})
        pub = get_public_agent_config()
        assert pub["api_key_masked"] == "****9988"
        assert pub["tavily_api_key_masked"] == "****7766"
        assert pub["llm_ready"] is True and pub["tavily_ready"] is True

        # 验证 ****keep 不会覆盖真实密钥
        updated = save_agent_config({"api_key": "****keep", "tavily_api_key": "****keep", "model": "qwen-plus"})
        assert updated["api_key"] == "sk-secret9988"
        assert updated["tavily_api_key"] == "tvly-secret7766"
        assert updated["model"] == "qwen-plus"
    finally:
        if backup_raw is not None:
            CONFIG_PATH.write_text(backup_raw, encoding="utf-8")
        elif CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
    print("[PASS] 4/6 多协议地址归一化、推理思考块解析与密钥脱敏持久化验证通过")


def test_agent_react_search_svg_and_adjust() -> None:
    sample_a = build_sample_png("orange_cat")
    sample_b = build_sample_png("magic_mushroom")

    fake_cfg = {
        "protocol": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "sk-mock",
        "model": "deepseek-chat",
        "tavily_api_key": "tvly-mock",
        "tavily_base_url": "https://api.tavily.com",
        "tavily_search_depth": "basic",
        "enable_backup_image_search": False,
        "proxy_mode": "none",
    }

    plan_json = json.dumps(
        {
            "action": "search_recommend",
            "search_query": "可爱橘猫 像素 拼豆 挂件",
            "backup_query": "cute cat pixel art",
            "quality": "simple",
            "palette_id": "mard_96",
            "remove_bg": True,
            "max_minutes_hint": 60,
            "auto_apply_best": True,
        }
    )

    fake_tavily = {
        "query": "可爱橘猫 像素 拼豆 挂件",
        "answer": "橘猫和小蘑菇是非常受欢迎的新手小挂件拼豆题材。",
        "results": [{"title": "新手拼豆挂件合集", "url": "https://example.com/1", "content": "32格以内约45分钟即可完成"}],
        "images": [
            {"url": "https://example.com/cat.png", "title": "萌系橘猫挂件", "source_domain": "example.com", "origin": "tavily"},
            {"url": "https://example.com/mush.png", "title": "森林红蘑菇徽章", "source_domain": "example.com", "origin": "tavily"},
        ],
    }

    fake_downloaded = [
        (fake_tavily["images"][0], sample_a),
        (fake_tavily["images"][1], sample_b),
    ]

    with (
        patch("core.agent.load_agent_config", return_value=fake_cfg),
        patch("core.agent.call_llm_chat", side_effect=[plan_json, "已为您挑选两款 1 小时内可完成的萌系挂件方案！"]),
        patch("core.agent.tavily_search", return_value=fake_tavily),
        patch("core.agent.download_valid_candidate_images", return_value=fake_downloaded),
    ):
        res = run_agent_turn(
            messages=[{"role": "user", "content": "帮我找一个1小时内能拼完的可爱挂件拼豆图"}],
            canvas_context={"quality": "hd", "palette_id": "mard_96", "remove_bg": False},
            recent_candidates=[],
            store_image_fn=_store_image,
            get_image_fn=_get_image,
            image_to_data_url_fn=_image_to_data_url,
        )
        assert len(res["recommendations"]) == 2
        assert res["auto_apply"] is not None
        assert res["auto_apply"]["active_quality"] == "simple"
        assert res["recommendations"][0]["bead_preview_url"].startswith("data:image/png;base64,")

        # 测试点击推荐卡片一键切换上板 API
        second_id = res["recommendations"][1]["image_id"]
        apply_resp = _run_coro_sync(
            api_agent_apply_candidate(
                _make_json_request(
                    "POST",
                    "/api/agent/apply_candidate",
                    {"image_id": second_id, "quality": "hd", "palette_id": "mard_96", "remove_bg": True},
                )
            )
        )
        assert apply_resp.status_code == 200
        applied_data = json.loads(apply_resp.body)
        assert "simple" in applied_data["tiers"] and "hd" in applied_data["tiers"]

    # 测试原创 SVG 矢量绘制转拼豆分支
    svg_plan = json.dumps(
        {
            "action": "draw_svg",
            "title": "像素红心徽章",
            "svg": "<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'><rect width='256' height='256' fill='#FFFFFF'/><circle cx='128' cy='128' r='86' fill='#EF4444' stroke='#18181B' stroke-width='10'/></svg>",
            "quality": "simple",
            "palette_id": "mard_96",
            "remove_bg": True,
        }
    )
    with (
        patch("core.agent.load_agent_config", return_value=fake_cfg),
        patch("core.agent.call_llm_chat", return_value=svg_plan),
    ):
        res_svg = run_agent_turn(
            messages=[{"role": "user", "content": "原创画一个红心圆章"}],
            canvas_context={"quality": "simple", "palette_id": "mard_96", "remove_bg": True},
            recent_candidates=[],
            store_image_fn=_store_image,
            get_image_fn=_get_image,
            image_to_data_url_fn=_image_to_data_url,
        )
        assert len(res_svg["recommendations"]) == 1
        assert res_svg["auto_apply"]["tiers"]["simple"]["total_beads"] > 50

    print("[PASS] 5/6 AI 对话智能体(Tavily 联网搜图推荐 + 候选上板 + 原创 SVG 转拼豆)全链路验证通过")


def test_routes_and_exports() -> None:
    resp_home = _run_coro_sync(homepage(_make_json_request("GET", "/")))
    assert resp_home.status_code == 200 and "AI 对话找图" in resp_home.body.decode("utf-8")

    resp_init = _run_coro_sync(api_init(_make_json_request("GET", "/api/init")))
    assert resp_init.status_code == 200
    init_json = json.loads(resp_init.body)
    assert len(init_json["palettes"]) == 3 and "agent" in init_json

    resp_sample = _run_coro_sync(
        api_load_sample(
            _make_json_request("POST", "/api/load_sample", {"sample_id": "sunset_fuji", "palette_id": "mard_96"})
        )
    )
    assert resp_sample.status_code == 200
    hd_pat = json.loads(resp_sample.body)["tiers"]["hd"]

    resp_re = _run_coro_sync(
        api_reestimate(_make_json_request("POST", "/api/reestimate", {"grid": hd_pat["grid"], "palette_id": "mard_96"}))
    )
    assert resp_re.status_code == 200

    resp_png = _run_coro_sync(
        api_export_png(
            _make_json_request(
                "POST",
                "/api/export/png",
                {"pattern": hd_pat, "skill_level": "standard", "bead_style": "code_block"},
            )
        )
    )
    assert resp_png.status_code == 200
    out_img = Image.open(io.BytesIO(resp_png.body))
    assert out_img.size[0] >= 960 and out_img.size[1] > 800

    resp_xlsx = _run_coro_sync(
        api_export_xlsx(_make_json_request("POST", "/api/export/xlsx", {"pattern": hd_pat}))
    )
    assert resp_xlsx.status_code == 200 and resp_xlsx.body[:2] == b"PK"
    print(f"[PASS] 6/7 HTTP 路由、高清图纸导出({out_img.size[0]}x{out_img.size[1]}px)与 Excel 导出验证通过")


def test_wechat_clawbot_crypto_qr_and_inbound_flow() -> None:
    # 1. 验证 AES-128-ECB 加解密与两种入站 aes_key 编码格式兼容
    key16 = os.urandom(16)
    raw_payload = build_sample_png("magic_mushroom")
    enc_bytes = aes_ecb_encrypt(raw_payload, key16)
    assert len(enc_bytes) == aes_ecb_padded_size(len(raw_payload))
    assert aes_ecb_decrypt(enc_bytes, key16) == raw_payload

    b64_raw = base64.b64encode(key16).decode("ascii")
    b64_hex = base64.b64encode(key16.hex().encode("ascii")).decode("ascii")
    assert parse_inbound_aes_key(b64_raw) == key16
    assert parse_inbound_aes_key(b64_hex) == key16

    # 2. 验证 uint64 消息 ID 无损字符串转换与本地高清二维码渲染
    parsed_msg = parse_ilink_json('{"ret":0,"msgs":[{"message_id":7491827364519283745,"message_type":1}]}')
    assert parsed_msg["msgs"][0]["message_id"] == "7491827364519283745"

    qr_url = render_qr_png_data_url("https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=mock_token")
    assert qr_url.startswith("data:image/png;base64,")
    qr_img = Image.open(io.BytesIO(base64.b64decode(qr_url.split(",", 1)[1])))
    assert qr_img.size[0] > 120 and qr_img.size[1] > 120

    # 3. 验证 HTTP 扫码状态接口与入站图文消息联动桌面画布 + 回传施工图纸
    st_resp = _run_coro_sync(api_wechat_status(_make_json_request("GET", "/api/wechat/status")))
    assert st_resp.status_code == 200 and "connected" in json.loads(st_resp.body)

    fake_qr_bundle = {
        "qrcode": "mock_qr_id",
        "qrcode_url": "https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=mock_qr_id",
        "qr_data_url": qr_url,
    }
    with (
        patch("app.WECHAT_BOT._fetch_new_qr", return_value=fake_qr_bundle),
        patch("app.WECHAT_BOT._qr_poll_worker", return_value=None),
    ):
        qr_resp = _run_coro_sync(api_wechat_login_qr(_make_json_request("POST", "/api/wechat/login_qr", {"force": True})))
        assert qr_resp.status_code == 200
        qr_json = json.loads(qr_resp.body)
        assert qr_json["login"]["qr_data_url"].startswith("data:image/png;base64,")

    backup_wx_state = WECHAT_STATE_PATH.read_text(encoding="utf-8") if WECHAT_STATE_PATH.exists() else None
    try:
        if WECHAT_STATE_PATH.exists():
            WECHAT_STATE_PATH.unlink()

        events: list[tuple[str, dict]] = []
        sent_texts: list[str] = []
        sent_pngs: list[bytes] = []

        mgr = WeChatClawBotManager(
            store_image_fn=_store_image,
            get_image_fn=_get_image,
            image_to_data_url_fn=_image_to_data_url,
            broadcast_event_fn=lambda ev, data: events.append((ev, data)),
        )
        mgr.state["bot_token"] = "mock_bot_token"

        cat_img = load_normalized_rgba(build_sample_png("orange_cat"))
        cat_id = _store_image(cat_img)
        cat_tiers = generate_all_tiers_summary(cat_img, palette_id="mard_96", remove_bg=True)
        fake_turn = {
            "reply": "**推荐方案**：为您生成萌系橘猫小挂件，约 38 分钟可拼完！",
            "tool_steps": [{"step": "search", "label": "Tavily 检索完成"}],
            "recommendations": [{"image_id": cat_id, "title": "橘猫挂件"}],
            "auto_apply": {
                "image_id": cat_id,
                "source_width": cat_img.size[0],
                "source_height": cat_img.size[1],
                "source_data_url": _image_to_data_url(cat_img),
                "tiers": cat_tiers,
                "active_quality": "simple",
                "palette_id": "mard_96",
                "remove_bg": True,
            },
        }

        with (
            patch.object(mgr, "_send_typing", return_value=None),
            patch.object(mgr, "send_text_to_wechat", side_effect=lambda u, t, c="": sent_texts.append(t)),
            patch.object(mgr, "send_image_bytes_to_wechat", side_effect=lambda u, b, c="": sent_pngs.append(b)),
            patch("core.wechat_clawbot.run_agent_turn", return_value=fake_turn),
        ):
            # 测试微信语音转文字消息入站 -> 智能体回复 + 高清图纸 PNG 回传 + 桌面端 SSE 同步
            mgr._handle_inbound_message(
                {
                    "from_user_id": "wx_user_001@im.wechat",
                    "context_token": "ctx_abc",
                    "message_type": 1,
                    "item_list": [{"type": 3, "voice_item": {"text": "帮我找个橘猫小挂件拼豆图"}}],
                }
            )
            assert len(sent_texts) == 1 and "**" not in sent_texts[0]
            assert len(sent_pngs) == 1
            bp_img = Image.open(io.BytesIO(sent_pngs[0]))
            assert bp_img.size[0] >= 960
            assert any(ev == "wechat_sync" and data["user_text"].startswith("[微信]") for ev, data in events)

            # 测试微信相册原图入站 -> 直接转三档拼豆并回传带色号施工图
            sent_texts.clear()
            sent_pngs.clear()
            events.clear()
            with patch.object(mgr, "_download_inbound_image", return_value=raw_payload):
                mgr._handle_inbound_message(
                    {
                        "from_user_id": "wx_user_001@im.wechat",
                        "context_token": "ctx_abc",
                        "message_type": 1,
                        "item_list": [{"type": 2, "image_item": {"media": {"encrypt_query_param": "enc_mock"}}}],
                    }
                )
            assert len(sent_texts) == 1 and "简略档" in sent_texts[0] and "高清档" in sent_texts[0]
            assert len(sent_pngs) == 1
            assert any(ev == "wechat_sync" and data["user_text"] == "[微信传图] 生成拼豆图纸" for ev, data in events)
    finally:
        if backup_wx_state is not None:
            WECHAT_STATE_PATH.write_text(backup_wx_state, encoding="utf-8")
        elif WECHAT_STATE_PATH.exists():
            WECHAT_STATE_PATH.unlink()

    print("[PASS] 7/7 微信 ClawBot (AES-128-ECB 加解密 + 二维码渲染 + 图文/语音双向联动桌面画布) 验证通过")


if __name__ == "__main__":
    test_palette_perceptual_matching()
    test_three_qualities_bead_count_and_time_monotonicity()
    test_non_square_aspect_ratios_and_background_removal()
    test_llm_helpers_and_secret_masking()
    test_agent_react_search_svg_and_adjust()
    test_routes_and_exports()
    test_wechat_clawbot_crypto_qr_and_inbound_flow()
    print("ALL ENGINE, AGENT, WECHAT CLAWBOT & API TESTS PASSED SUCCESSFULLY!")
