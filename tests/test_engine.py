"""拼豆工坊核心算法、路由处理器与图纸导出完整自动化测试套件."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw
from starlette.requests import Request

from app import (
    api_export_png,
    api_export_xlsx,
    api_init,
    api_load_sample,
    api_reestimate,
    homepage,
)
from core.generator import generate_all_tiers_summary, generate_bead_pattern, load_normalized_rgba
from core.palettes import get_palette
from core.samples import SAMPLE_ITEMS, build_sample_png


def _run_coro_sync(coro):
    """无需创建事件循环套接字对即可同步驱动纯内存 ASGI 协程."""
    try:
        while True:
            coro.send(None)
    except StopIteration as stop:
        return stop.value


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
    assert white_code == "H01", f"Expected H01 for white, got {white_code}"
    assert black_code == "H02", f"Expected H02 for black, got {black_code}"
    assert red_code.startswith("F"), f"Expected F-series for crimson red, got {red_code}"
    print("[PASS] 1/4 拼豆色卡 CIELAB 感知匹配准确")


def test_three_qualities_bead_count_and_time_monotonicity() -> None:
    for sample in SAMPLE_ITEMS:
        png = build_sample_png(sample["id"])
        img = load_normalized_rgba(png)
        tiers = generate_all_tiers_summary(img, palette_id="master_144", remove_bg=False)

        b_simple = tiers["simple"]["total_beads"]
        b_hd = tiers["hd"]["total_beads"]
        b_faithful = tiers["faithful"]["total_beads"]
        assert 0 < b_simple < b_hd < b_faithful, f"Bead counts not monotonic: {b_simple}, {b_hd}, {b_faithful}"

        t_simple = tiers["simple"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        t_hd = tiers["hd"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        t_faithful = tiers["faithful"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        assert t_simple < t_hd < t_faithful, f"Times not monotonic: {t_simple}, {t_hd}, {t_faithful}"

        f_s = tiers["simple"]["time_estimate"]["profiles"]["standard"]["formatted"]
        f_h = tiers["hd"]["time_estimate"]["profiles"]["standard"]["formatted"]
        f_f = tiers["faithful"]["time_estimate"]["profiles"]["standard"]["formatted"]
        print(
            f"  - 示例[{sample['name']}]: "
            f"简略({b_simple}颗/{tiers['simple']['unique_colors']}色, {f_s}) | "
            f"高清({b_hd}颗/{tiers['hd']['unique_colors']}色, {f_h}) | "
            f"还原({b_faithful}颗/{tiers['faithful']['unique_colors']}色, {f_f})"
        )

        pro_s = tiers["hd"]["time_estimate"]["profiles"]["pro"]["total_seconds"]
        std_s = tiers["hd"]["time_estimate"]["profiles"]["standard"]["total_seconds"]
        beg_s = tiers["hd"]["time_estimate"]["profiles"]["beginner"]["total_seconds"]
        assert pro_s < std_s < beg_s
    print("[PASS] 2/4 三档画质(简略/高清/还原)豆数梯度与拼豆时长预估全部验证通过")


def test_non_square_aspect_ratios_and_background_removal() -> None:
    wide_img = Image.new("RGBA", (640, 360), (250, 250, 250, 255))
    draw = ImageDraw.Draw(wide_img)
    draw.ellipse([200, 60, 440, 300], fill=(56, 189, 248, 255))
    draw.ellipse([260, 120, 300, 160], fill=(255, 255, 255, 255))

    pat_full = generate_bead_pattern(wide_img, quality="faithful", remove_bg=False)
    assert pat_full["grid_width"] == 100 and pat_full["grid_height"] == 56
    assert pat_full["total_beads"] == 100 * 56

    pat_nobg = generate_bead_pattern(wide_img, quality="hd", remove_bg=True)
    assert pat_nobg["total_beads"] < pat_nobg["grid_width"] * pat_nobg["grid_height"]
    codes_present = {item["code"] for item in pat_nobg["bom"]}
    assert "H01" in codes_present, "Interior white highlight inside subject must be preserved!"
    print("[PASS] 3/4 非正方形比例适配与智能背景抠除(保留内部高光)验证通过")


def test_routes_and_exports() -> None:
    resp_home = _run_coro_sync(homepage(_make_json_request("GET", "/")))
    assert resp_home.status_code == 200 and "拼豆工坊" in resp_home.body.decode("utf-8")

    resp_init = _run_coro_sync(api_init(_make_json_request("GET", "/api/init")))
    assert resp_init.status_code == 200
    assert len(json.loads(resp_init.body)["palettes"]) == 3

    resp_sample = _run_coro_sync(
        api_load_sample(
            _make_json_request("POST", "/api/load_sample", {"sample_id": "sunset_fuji", "palette_id": "mard_96"})
        )
    )
    assert resp_sample.status_code == 200
    payload = json.loads(resp_sample.body)
    hd_pat = payload["tiers"]["hd"]

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
    assert resp_xlsx.status_code == 200
    assert len(resp_xlsx.body) > 2000 and resp_xlsx.body[:2] == b"PK"

    print(f"[PASS] 4/4 API 路由、高清施工图纸导出({out_img.size[0]}x{out_img.size[1]}px)与 Excel 采购表导出验证通过")


if __name__ == "__main__":
    test_palette_perceptual_matching()
    test_three_qualities_bead_count_and_time_monotonicity()
    test_non_square_aspect_ratios_and_background_removal()
    test_routes_and_exports()
    print("ALL ENGINE & API TESTS PASSED SUCCESSFULLY!")
