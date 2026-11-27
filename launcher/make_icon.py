"""使用 rubber-hose-ui 官方内核 (core.js) 与手绘赛璐璐水彩拼豆图层合成 Windows 多尺寸桌面图标 (.ico & .png).

遵循 rubber-hose-ui SKILL.md 规范：
1. 主体为无四肢的 1930s 手绘水彩赛璐璐管状融合豆图层 (bead_layer.webp)
2. 四肢、四指白手套 (palm / knuckle)、大头皮鞋 (shoe) 与放射墨水线 (ticks) 由官方 RubberHose 内核代码装配
3. 针对 ≥32px 桌面/资源管理器大图标展示完整全身欢呼造型，针对 16px/24px 任务栏小图标自动切换特写大脸版，确保全尺寸锐利可读
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import struct
import subprocess

from PIL import Image

LAUNCHER_DIR = Path(__file__).resolve().parent
PROJECT_DIR = LAUNCHER_DIR.parent
UI_RH_DIR = PROJECT_DIR / "ui" / "rubber-hose"
CORE_SKILL_JS = Path(r"C:\Users\zzc\.gemini\config\skills\rubber-hose-ui\core.js")


def _find_browser() -> str:
    for p in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ):
        if os.path.exists(p):
            return p
    raise FileNotFoundError("未找到 Edge 或 Chrome 用于离屏渲染 Rubber Hose 图标")


def _encode_png_bytes(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _encode_bmp_dib_bytes(im: Image.Image) -> bytes:
    """将 RGBA 图像编码为 Windows PE RT_ICON 标准 32-bit BGRA BITMAPINFOHEADER + 1-bit AND 掩码格式."""
    rgba = im.convert("RGBA")
    w, h = rgba.size
    raw = rgba.tobytes()

    # BITMAPINFOHEADER (40 bytes): 高度必须填写为 h * 2 (XOR 位图 + AND 掩码)
    xor_size = w * h * 4
    and_row_bytes = ((w + 31) // 32) * 4
    and_size = and_row_bytes * h
    bih = struct.pack(
        "<IIIHHIIIIII",
        40,          # biSize
        w,           # biWidth
        h * 2,       # biHeight (bottom-up XOR + AND)
        1,           # biPlanes
        32,          # biBitCount
        0,           # biCompression (BI_RGB)
        xor_size + and_size,
        0,
        0,
        0,
        0,
    )

    xor_buf = bytearray(xor_size)
    and_buf = bytearray(and_size)
    dst_pos = 0
    for y in range(h - 1, -1, -1):
        row_start = y * w * 4
        and_row_start = (h - 1 - y) * and_row_bytes
        for x in range(w):
            px = row_start + x * 4
            r, g, b, a = raw[px], raw[px + 1], raw[px + 2], raw[px + 3]
            xor_buf[dst_pos] = b
            xor_buf[dst_pos + 1] = g
            xor_buf[dst_pos + 2] = r
            xor_buf[dst_pos + 3] = a
            dst_pos += 4
            if a < 64:
                and_buf[and_row_start + (x >> 3)] |= 0x80 >> (x & 7)

    return bih + bytes(xor_buf) + bytes(and_buf)


def save_multi_master_ico(out_ico: Path, full_master: Image.Image, small_master: Image.Image) -> None:
    """严格遵循微软官方 PE 图标规范：256px 采用 PNG 压缩流，≤128px 全部采用原生 32-bit BGRA DIB，确保资源管理器详细信息(16px)与大图标(256px)全视图立即识别."""
    sizes = [256, 128, 64, 48, 32, 24, 16]
    entries_meta: list[tuple[int, bytes]] = []
    for sz in sizes:
        src = small_master if sz <= 24 else full_master
        resized = src.resize((sz, sz), Image.Resampling.LANCZOS)
        frame_bytes = _encode_png_bytes(resized) if sz >= 256 else _encode_bmp_dib_bytes(resized)
        entries_meta.append((sz, frame_bytes))

    header = struct.pack("<HHH", 0, 1, len(entries_meta))
    offset = 6 + 16 * len(entries_meta)
    dir_entries = bytearray()
    payloads = bytearray()

    for sz, png_data in entries_meta:
        w_byte = 0 if sz >= 256 else sz
        h_byte = 0 if sz >= 256 else sz
        dir_entries.extend(
            struct.pack(
                "<BBBBHHII",
                w_byte,
                h_byte,
                0,
                0,
                1,
                32,
                len(png_data),
                offset,
            )
        )
        payloads.extend(png_data)
        offset += len(png_data)

    out_ico.write_bytes(bytes(header) + bytes(dir_entries) + bytes(payloads))


def build_rubber_hose_icons(preview_sheet_out: Path | None = None) -> None:
    layer_webp = LAUNCHER_DIR / "bead_layer.webp"
    paper_jpg = UI_RH_DIR / "paper.jpg"
    if not layer_webp.exists():
        raise FileNotFoundError(f"缺少手绘拼豆主体图层: {layer_webp}")

    # 优先使用已安装的全局 skill core.js；若其他机器未装全局 skill，则自动从项目内置 tabs.js 提取共享内核
    core_script_tag = (
        f'<script src="{CORE_SKILL_JS.as_uri()}"></script>'
        if CORE_SKILL_JS.exists()
        else f'<script src="{(UI_RH_DIR / "tabs.js").as_uri()}"></script>'
    )

    bead_b64 = "data:image/webp;base64," + base64.b64encode(layer_webp.read_bytes()).decode("ascii")
    paper_b64 = "data:image/jpeg;base64," + base64.b64encode(paper_jpg.read_bytes()).decode("ascii")

    html_code = f"""<!doctype html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;background:transparent">
<canvas id="cFull" width="1024" height="1024"></canvas>
<canvas id="cSmall" width="1024" height="1024"></canvas>
{core_script_tag}
<script>
window.RENDER_DONE = false;
(async () => {{
  const fx = window.RubberHose;
  const {{ INK, TAU, art, addArt, place, arm, reach, hand, leg, ticks }} = fx;
  addArt({{ 'bead-body': '{bead_b64}', 'paper-tex': '{paper_b64}' }});

  const keys = ['bead-body', 'paper-tex', 'palm', 'glove', 'fist', 'knuckle', 'shoe'];
  for (let tries = 0; tries < 80; tries++) {{
    if (keys.every((k) => fx.ready(art(k)))) break;
    await new Promise((r) => setTimeout(r, 25));
  }}

  function drawBadgeBackdrop(g, S, pad, rad, borderW) {{
    const inner = S - pad * 2;
    const cx = S / 2, cy = S / 2;

    g.save();
    g.beginPath();
    g.roundRect(pad, pad, inner, inner, rad);
    g.clip();

    g.fillStyle = '#f5dfb2';
    g.fillRect(0, 0, S, S);

    // 1930s 复古赛璐璐放射背景光芒
    const rays = 16;
    for (let i = 0; i < rays; i++) {{
      if (i % 2 === 0) continue;
      const a0 = (i / rays) * TAU - 0.12;
      const a1 = ((i + 1) / rays) * TAU - 0.12;
      g.fillStyle = 'rgba(104, 146, 163, 0.54)';
      g.beginPath();
      g.moveTo(cx, cy + 8);
      g.arc(cx, cy + 8, S * 0.85, a0, a1);
      g.closePath();
      g.fill();
    }}

    // 暖棕木质舞台地面弧线（留足底部鞋底安全边距）
    g.fillStyle = '#d99b66';
    g.beginPath();
    g.ellipse(cx, pad + inner * 0.94, inner * 0.72, inner * 0.25, 0, Math.PI, TAU);
    g.fill();
    g.strokeStyle = INK;
    g.lineWidth = borderW * 0.5;
    g.beginPath();
    g.ellipse(cx, pad + inner * 0.94, inner * 0.72, inner * 0.25, 0, Math.PI * 1.07, TAU * 0.965);
    g.stroke();

    const pImg = art('paper-tex');
    if (fx.ready(pImg)) {{
      g.save();
      g.globalCompositeOperation = 'multiply';
      g.globalAlpha = 0.42;
      g.drawImage(pImg, 0, 0, S, S);
      g.restore();
    }}

    g.strokeStyle = 'rgba(255, 249, 232, 0.8)';
    g.lineWidth = borderW * 0.88;
    g.beginPath();
    g.roundRect(pad + borderW * 0.75, pad + borderW * 0.75, inner - borderW * 1.5, inner - borderW * 1.5, Math.max(8, rad - borderW * 0.6));
    g.stroke();

    g.restore();

    g.strokeStyle = INK;
    g.lineWidth = borderW;
    g.lineJoin = 'round';
    g.lineCap = 'round';
    g.beginPath();
    g.roundRect(pad, pad, inner, inner, rad);
    g.stroke();
  }}

  function drawMiniBead(g, x, y, r, fillHex, rot) {{
    g.save();
    g.translate(x, y);
    g.rotate(rot);
    g.fillStyle = fillHex;
    g.strokeStyle = INK;
    g.lineWidth = 2.8;
    g.beginPath();
    g.arc(0, 0, r, 0, TAU);
    g.fill();
    g.stroke();
    g.fillStyle = '#fbe7c0';
    g.beginPath();
    g.arc(0, 0, r * 0.36, 0, TAU);
    g.fill();
    g.stroke();
    g.restore();
  }}

  // 1. 全身版桌面图标母版 (≥32px)
  {{
    const c = document.getElementById('cFull');
    const g = c.getContext('2d');
    const scale = 1024 / 300;
    g.setTransform(scale, 0, 0, scale, 0, 0);
    g.clearRect(0, 0, 300, 300);
    g.lineJoin = 'round';
    g.lineCap = 'round';
    g.imageSmoothingQuality = 'high';

    drawBadgeBackdrop(g, 300, 12, 62, 8.5);
    drawMiniBead(g, 56, 60, 14.5, '#f0b02c', -0.2);
    drawMiniBead(g, 242, 190, 12.5, '#34d399', 0.25);

    const body = art('bead-body');
    const BW = 132;
    const BH = BW * body.naturalHeight / body.naturalWidth;
    const CX = 145;
    const bodyBottom = 198;
    const bodyCY = bodyBottom - BH * 0.5;
    const FLOOR = 248;

    // 鞋底地面墨影
    g.fillStyle = 'rgba(37, 29, 22, 0.22)';
    g.beginPath();
    g.ellipse(CX + 2, FLOOR - 3, 66, 10, 0, 0, TAU);
    g.fill();

    // 双腿从豆体内部伸出并精确裁切进黄色大皮鞋开口
    leg(g, CX - 23, bodyBottom - 22, CX - 33, FLOOR - 7, -6, {{ dir: -1, w: 46, lw: 8.0, rot: 0.05 }});
    leg(g, CX + 23, bodyBottom - 22, CX + 36, FLOOR - 7, 6, {{ dir: 1, w: 46, lw: 8.0, rot: -0.07 }});

    // 右侧挥手橡皮管手臂 + 指尖外围放射动势线（绝不压到白手套指尖）
    arm(g, 'palm', CX + BW * 0.28, bodyCY + 2, 232, 98, 14, {{ w: 40, lw: 8.0, turn: -0.18 }});
    ticks(g, 232, 92, 4, 30, 39, -Math.PI * 0.82, -Math.PI * 0.14, 2.8, 3);

    // 左侧叉腰弯臂：外扩弧度清晰露出黑色橡皮管弯折，再落回腰侧手背手套
    const hipX = CX - BW * 0.44;
    const hipY = bodyCY + 24;
    const hipAng = reach(g, CX - BW * 0.34, bodyCY - 20, hipX, hipY, -44, {{ w: 38, lw: 8.0, turn: 0.65 }});

    // 手绘水彩赛璐璐拼豆主体覆盖四肢根部
    place(g, body, CX, bodyBottom, BW, {{ ay: 1, rot: -0.025 }});

    // 补上前景叉腰白手套
    hand(g, 'knuckle', hipX, hipY, hipAng, 38, 1);
  }}

  // 2. 微缩任务栏版母版 (16x16 & 24x24)
  {{
    const c = document.getElementById('cSmall');
    const g = c.getContext('2d');
    const scale = 1024 / 300;
    g.setTransform(scale, 0, 0, scale, 0, 0);
    g.clearRect(0, 0, 300, 300);
    g.lineJoin = 'round';
    g.lineCap = 'round';
    g.imageSmoothingQuality = 'high';

    drawBadgeBackdrop(g, 300, 10, 68, 12);
    const body = art('bead-body');
    place(g, body, 150, 258, 214, {{ ay: 1 }});
  }}

  window.RENDER_DONE = true;
}})();
</script></body></html>
"""

    tmp_html = LAUNCHER_DIR / "_tmp_icon_render.html"
    tmp_html.write_text(html_code, encoding="utf-8")

    node_js = r"""
    const { spawn } = require('node:child_process');
    const fs = require('node:fs');
    const path = require('node:path');
    const os = require('node:os');
    (async () => {
      const port = 19361;
      const prof = fs.mkdtempSync(path.join(os.tmpdir(), 'rhico-'));
      const proc = spawn(process.env.BROWSER_BIN, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, '--allow-file-access-from-files', '--no-first-run', 'about:blank'], { stdio: 'ignore' });
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      let targets;
      for (let i = 0; i < 50 && !targets?.some?.((t) => t.type === 'page'); i++) {
        try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch {}
        await sleep(120);
      }
      const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
      await new Promise((r) => ws.addEventListener('open', r, { once: true }));
      let id = 0; const pending = new Map();
      ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
      const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, (m) => res(m.result)); ws.send(JSON.stringify({ id: i, method, params })); });
      const evalJs = async (expression) => (await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result?.value;

      await send('Runtime.enable'); await send('Page.enable');
      await send('Page.navigate', { url: process.env.HTML_URI });
      for (let i = 0; i < 60; i++) {
        if (await evalJs('window.RENDER_DONE === true')) break;
        await sleep(100);
      }
      const f = await evalJs("document.getElementById('cFull').toDataURL('image/png')");
      const s = await evalJs("document.getElementById('cSmall').toDataURL('image/png')");
      process.stdout.write(JSON.stringify({ full: f.split(',')[1], small: s.split(',')[1] }));
      ws.close(); proc.kill(); process.exit(0);
    })();
    """

    env = os.environ.copy()
    env["BROWSER_BIN"] = _find_browser()
    env["HTML_URI"] = tmp_html.as_uri()
    try:
        proc = subprocess.run(["node", "-e", node_js], env=env, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)
        import json

        payload = json.loads(proc.stdout)
    finally:
        tmp_html.unlink(missing_ok=True)

    full_im = Image.open(io.BytesIO(base64.b64decode(payload["full"]))).convert("RGBA")
    small_im = Image.open(io.BytesIO(base64.b64decode(payload["small"]))).convert("RGBA")

    # 保存 UI 256px 透明 PNG 图标与多尺寸 Windows 原生 app.ico
    UI_RH_DIR.mkdir(parents=True, exist_ok=True)
    app_png = UI_RH_DIR / "app-icon.png"
    full_im.resize((256, 256), Image.Resampling.LANCZOS).save(app_png, format="PNG", optimize=True)

    app_ico = LAUNCHER_DIR / "app.ico"
    save_multi_master_ico(app_ico, full_im, small_im)
    print(f"Saved {app_png} and {app_ico} ({app_ico.stat().st_size} bytes)")

    if preview_sheet_out is not None:
        from PIL import ImageDraw

        sheet = Image.new("RGBA", (920, 560), (236, 215, 172, 255))
        dr = ImageDraw.Draw(sheet)
        dr.rectangle([520, 0, 920, 560], fill=(30, 34, 42, 255))
        sheet.alpha_composite(full_im.resize((480, 480), Image.Resampling.LANCZOS), (20, 40))
        y_cursor = 32
        for sz in (128, 64, 48, 32, 24, 16):
            src = small_im if sz <= 24 else full_im
            ic = src.resize((sz, sz), Image.Resampling.LANCZOS)
            dr.rounded_rectangle([545, y_cursor - 6, 710, y_cursor + max(sz, 28) + 6], radius=8, fill=(246, 238, 220, 255))
            sheet.alpha_composite(ic, (560, y_cursor))
            sheet.alpha_composite(ic, (750, y_cursor))
            y_cursor += max(sz, 28) + 22
        sheet.save(preview_sheet_out)


if __name__ == "__main__":
    build_rubber_hose_icons()
