"""拼豆工坊对话智能体 (BeadCraft ReAct Agent).

核心能力：
1. 自然语言意图规划：识别用户想要的图案主题、风格、目标用豆档位（简略/高清/还原）、期望时长上限、是否智能去背与色卡偏好
2. Tavily 联网检索推荐 (search_recommend)：调用 Tavily 搜索网页背景知识与参考图片，并发下载候选图并实时转换为拼豆图纸，
   测算每款候选方案的用豆颗数、色号数与预计制作时长，自动筛选最优推荐卡片并同步上板
3. AI 原创矢量绘图转拼豆 (draw_svg)：当用户希望直接原创生成图案（或未配置搜索密钥时），由大模型编写干净 SVG 插画并光栅化为三档拼豆图纸
4. 对话式画板调参 (adjust_canvas)：支持“换成第 2 个方案”、“切到简略模式并开启去背景”等自然语言操控
"""

from __future__ import annotations

import base64
import io
from typing import Any, Callable, Dict, List

import fitz  # PyMuPDF: 高速 SVG 矢量光栅化
from PIL import Image, ImageDraw

from core.agent_config import load_agent_config
from core.generator import (
    generate_all_tiers_summary,
    generate_bead_pattern,
    load_normalized_rgba,
)
from core.llm_client import call_llm_chat, extract_json_object
from core.search_client import (
    download_valid_candidate_images,
    fetch_backup_images,
    tavily_search,
)

PLANNER_SYSTEM_PROMPT = """你是「拼豆工坊 (BeadCraft Studio)」内置的 AI 拼豆设计智能体规划器。
请根据用户的自然语言描述与当前画布上下文，输出一个严格的 JSON 动作指令（不要输出除 JSON 以外的多余解释）。

可用动作类型 (`action`) 共 4 种：

1. `"search_recommend"` —— 用户想寻找特定角色、IP、动物、物品、表情包、节日礼物的拼豆图，或让你推荐符合条件（如“1小时内拼完”、“可爱风挂件”、“适合摆件”）的拼豆图（优先使用此动作联网搜图推荐！）：
{
  "action": "search_recommend",
  "search_query": "针对图片清晰度优化的中文或双语搜索词，尽量加上 像素画 / 卡通插画 / 拼豆 / 白底 等有利于转拼豆的修饰词，例如：皮卡丘 可爱 像素画 插画 白底",
  "backup_query": "英文或精简备选检索词，例如：cute pikachu pixel art sprite",
  "quality": "simple 或 hd 或 faithful（挂件/钥匙扣/新手/简单/1小时内 -> simple；摆件/适中/高清/2-3小时 -> hd；大幅装饰画/超清/照片还原 -> faithful）",
  "palette_id": "mard_96 或 perler_58 或 master_144（默认 mard_96；新手少色选 perler_58；还原渐变选 master_144）",
  "remove_bg": true 或 false（挂件、单个角色、贴纸、纯色底主体建议设为 true；满幅风景画设为 false）,
  "max_minutes_hint": 期望时长上限分钟数（整数，若用户未提及填 null）,
  "auto_apply_best": true
}

2. `"draw_svg"` —— 用户明确要求“原创绘制/直接画一个简单徽章图标/不搜网图”，或要求创作抽象几何像素徽章：
{
  "action": "draw_svg",
  "title": "作品简短标题",
  "svg": "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320' viewBox='0 0 320 320'>...使用鲜明饱满的几何色块、清晰深色轮廓线与可爱高光绘制完整主体，背景若需抠除请用纯白 #FFFFFF 或透明...</svg>",
  "quality": "simple 或 hd 或 faithful",
  "palette_id": "mard_96",
  "remove_bg": true
}

3. `"adjust_canvas"` —— 用户针对当前已加载画布或上一轮推荐的候选方案提出修改（如“把第 2 个方案加载到画布”、“改成简略模式”、“把背景抠掉”、“长边改成 45 颗”）：
{
  "action": "adjust_canvas",
  "candidate_index": 若用户指定第几个候选方案则填 1 开始的序号，否则填 null,
  "quality": "simple 或 hd 或 faithful",
  "palette_id": "mard_96 或 perler_58 或 master_144",
  "remove_bg": true 或 false,
  "custom_max_side": 若用户指定具体颗数则填整数(18~128)，否则填 null,
  "reply": "简短友好的中文确认回复"
}

4. `"chat_only"` —— 用户仅询问拼豆手工技巧（如怎么贴美纹纸、熨斗温度多少、2.6mm和5mm区别）而无需生成新图：
{
  "action": "chat_only",
  "reply": "专业、亲切、条理清晰的中文解答"
}
"""


def render_bead_preview_thumbnail(pattern: Dict[str, Any], thumb_px: int = 210) -> str:
    """将拼豆矩阵渲染为精致的圆环拼豆缩略预览图 (base64 Data URL)，供推荐卡片直观展示."""
    grid = pattern["grid"]
    gw = pattern["grid_width"]
    gh = pattern["grid_height"]
    lookup = pattern["palette_lookup"]

    cell = max(3, min(12, thumb_px // max(1, max(gw, gh))))
    img_w = gw * cell + 8
    img_h = gh * cell + 8
    canvas = Image.new("RGBA", (img_w, img_h), (24, 30, 42, 255))
    draw = ImageDraw.Draw(canvas)

    for r in range(gh):
        row = grid[r]
        y0 = 4 + r * cell
        for c in range(gw):
            val = row[c]
            if val < 0:
                continue
            x0 = 4 + c * cell
            hc = lookup[str(val)]["hex"]
            rgb = (int(hc[1:3], 16), int(hc[3:5], 16), int(hc[5:7], 16), 255)
            if cell >= 5:
                draw.ellipse([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=rgb)
                if cell >= 7:
                    hr = max(1, cell // 5)
                    cx, cy = x0 + cell // 2, y0 + cell // 2
                    draw.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=(24, 30, 42, 255))
            else:
                draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=rgb)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _rasterize_svg_to_png_bytes(svg_code: str) -> bytes:
    doc = fitz.open(stream=svg_code.encode("utf-8"), filetype="svg")
    page = doc[0]
    rect = page.rect
    scale = 360.0 / max(1.0, max(rect.width, rect.height))
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, alpha=True)
    return pix.tobytes("png")


def _heuristic_fallback_plan(user_text: str, canvas_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """当大模型未输出标准 JSON 或仅配置了 Tavily 搜索时的稳健启发式意图兜底."""
    txt = user_text.strip()
    quality = canvas_ctx.get("quality", "hd")
    if any(k in txt for k in ("简略", "挂件", "钥匙扣", "简单", "小号", "新手", "快", "半小时", "1小时", "一小时")):
        quality = "simple"
    elif any(k in txt for k in ("还原", "大师", "超清", "大幅", "装饰画", "精细")):
        quality = "faithful"
    elif any(k in txt for k in ("高清", "摆件", "标准")):
        quality = "hd"

    remove_bg = True
    if any(k in txt for k in ("风景", "晚霞", "海边", "背景保留", "满幅", "壁纸")):
        remove_bg = False

    return {
        "action": "search_recommend",
        "search_query": f"{txt} 可爱 卡通 插画 像素 拼豆",
        "backup_query": f"{txt} pixel art cute illustration",
        "quality": quality,
        "palette_id": canvas_ctx.get("palette_id", "mard_96"),
        "remove_bg": remove_bg,
        "max_minutes_hint": 60 if "1小时" in txt or "一小时" in txt else None,
        "auto_apply_best": True,
    }


def _synthesize_recommendation_reply(
    user_prompt: str,
    candidates_meta: List[Dict[str, Any]],
    web_snippets: List[Dict[str, str]],
    tavily_answer: str,
    cfg: Dict[str, Any],
    llm_ready: bool,
) -> str:
    """结合真实测算出的各候选拼豆数与时长，让大模型生成贴心且有依据的推荐说明."""
    if not candidates_meta:
        return "未能从检索结果中找到清晰的可用参考图片。建议换一个更具体的角色名或风格描述再试一次（或让我直接为您原创绘制徽章图案）。"

    if not llm_ready:
        top = candidates_meta[0]
        lines = [
            f"已通过 Tavily 联网检索并为您生成 **{len(candidates_meta)} 款拼豆推荐方案**（已自动将 **方案 1** 加载到中央画布）："
        ]
        for idx, c in enumerate(candidates_meta, start=1):
            lines.append(
                f"- **方案 {idx}（{c['title'][:22]}）**：{c['quality_name']}档 `{c['grid_width']}×{c['grid_height']}` · **{c['total_beads']} 颗豆**（{c['unique_colors']} 色）· 预估 **{c['estimated_time']}**"
            )
        lines.append("\n点击任意推荐卡片上的「加载到画布」即可一键切换全套三档图纸。")
        return "\n".join(lines)

    cand_summary = "\n".join(
        f"方案{i+1}: 标题={c['title']} | 档位={c['quality_name']}({c['grid_width']}x{c['grid_height']}) | "
        f"用豆={c['total_beads']}颗 | 色号={c['unique_colors']}种 | 预估时长(日常玩家)={c['estimated_time']} | 散点率={c['scattered_ratio']}%"
        for i, c in enumerate(candidates_meta)
    )
    web_ctx = "\n".join(f"- {w['title']}: {w['content'][:120]}" for w in web_snippets[:3])

    synth_messages = [
        {
            "role": "system",
            "content": (
                "你是拼豆工坊的贴心手作顾问。系统已完成联网搜图并将候选图转换成了真实的拼豆图纸（方案1已自动加载到画布）。"
                "请用简洁、自然、有温度的中文（不超过 160 字）向用户推荐这几款方案，重点结合真实的【用豆颗数、色号数与预估拼豆时长】说明哪款最贴合他的需求，并提示可点击卡片随时切换。"
                "不要使用标题井号，不要编造与下方实测数据不符的数字。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"用户需求：{user_prompt}\n\n"
                f"Tavily 联网背景摘要：{tavily_answer[:200]}\n{web_ctx}\n\n"
                f"实测生成的候选拼豆方案：\n{cand_summary}"
            ),
        },
    ]
    try:
        return call_llm_chat(synth_messages, cfg=cfg, temperature=0.5, max_tokens=450)
    except Exception:
        top = candidates_meta[0]
        return (
            f"已结合联网搜索为您筛选出 {len(candidates_meta)} 款拼豆方案！首推方案 1（{top['quality_name']}模式共 "
            f"{top['total_beads']} 颗拼豆、{top['unique_colors']} 种色号，预估耗时约 {top['estimated_time']}），已自动为您铺设到中央画布，也可点击下方其他卡片一键切换。"
        )


def run_agent_turn(
    messages: List[Dict[str, str]],
    canvas_context: Dict[str, Any],
    recent_candidates: List[Dict[str, Any]],
    store_image_fn: Callable[[Image.Image], str],
    get_image_fn: Callable[[str], Image.Image | None],
    image_to_data_url_fn: Callable[[Image.Image], str],
) -> Dict[str, Any]:
    """执行单轮对话智能体推理、联网检索与拼豆图纸推荐生成."""
    cfg = load_agent_config()
    base_url = str(cfg.get("base_url", ""))
    is_local_ollama = "127.0.0.1:11434" in base_url or "localhost:11434" in base_url
    llm_ready = bool(str(cfg.get("api_key", "")).strip()) or is_local_ollama
    tavily_ready = bool(str(cfg.get("tavily_api_key", "")).strip())

    if not llm_ready and not tavily_ready:
        return {
            "needs_config": True,
            "reply": "欢迎使用 AI 拼豆灵感智能体！请先点击右上角「配置模型与搜索」，填入您的大模型 API Key（支持 DeepSeek / 通义千问 / Kimi / OpenAI / Gemini / Ollama 等）与 Tavily 联网搜索 Key，即可一句话为您搜图并生成拼豆方案。",
            "tool_steps": [],
            "recommendations": [],
            "auto_apply": None,
        }

    user_last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "").strip()
    tool_steps: List[Dict[str, str]] = []

    # 1. 意图理解与动作规划
    plan: Dict[str, Any] | None = None
    if llm_ready:
        ctx_desc = (
            f"当前画布状态: 档位={canvas_context.get('quality', 'hd')}, 色卡={canvas_context.get('palette_id', 'mard_96')}, "
            f"去背景={canvas_context.get('remove_bg', False)}; "
            f"近期候选方案数={len(recent_candidates)}"
        )
        plan_msgs = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT + f"\n\n[{ctx_desc}]"},
            *messages[-6:],
        ]
        raw_plan = call_llm_chat(plan_msgs, cfg=cfg, temperature=0.2, max_tokens=900)
        plan = extract_json_object(raw_plan)
        if plan is None:
            # 若模型直接输出了纯文本回答且不像搜图请求，直接作为回复返回
            if not any(w in user_last for w in ("推荐", "生成", "找", "搜", "拼", "画", "图", "想要", "来个", "做个")):
                return {
                    "reply": raw_plan,
                    "tool_steps": [],
                    "recommendations": [],
                    "auto_apply": None,
                }
            plan = _heuristic_fallback_plan(user_last, canvas_context)
        else:
            tool_steps.append(
                {
                    "step": "intent_plan",
                    "label": f"智能体规划：{plan.get('action')} · 目标档位 {plan.get('quality', 'hd')}",
                }
            )
    else:
        plan = _heuristic_fallback_plan(user_last, canvas_context)
        tool_steps.append({"step": "intent_plan", "label": "未配置大模型，启用启发式规则 + Tavily 联网检索模式"})

    action = str(plan.get("action") or "search_recommend")

    # 动作分支 A: 纯聊天答疑
    if action == "chat_only":
        return {
            "reply": str(plan.get("reply") or "请问有什么拼豆制作问题我可以帮您？"),
            "tool_steps": tool_steps,
            "recommendations": [],
            "auto_apply": None,
        }

    # 动作分支 B: 调整当前画板或切换某个历史推荐候选
    if action == "adjust_canvas":
        cand_idx = plan.get("candidate_index")
        target_img_id = canvas_context.get("image_id")
        if isinstance(cand_idx, int) and 1 <= cand_idx <= len(recent_candidates):
            target_img_id = recent_candidates[cand_idx - 1]["image_id"]

        target_img = get_image_fn(target_img_id) if target_img_id else None
        q = str(plan.get("quality") or canvas_context.get("quality") or "hd")
        if q not in ("simple", "hd", "faithful"):
            q = "hd"
        pal_id = str(plan.get("palette_id") or canvas_context.get("palette_id") or "mard_96")
        rem_bg = bool(plan.get("remove_bg", canvas_context.get("remove_bg", False)))
        c_side = plan.get("custom_max_side")

        auto_apply = None
        if target_img is not None:
            tiers = generate_all_tiers_summary(img_rgba=target_img, palette_id=pal_id, remove_bg=rem_bg)
            if isinstance(c_side, int) and 18 <= c_side <= 128:
                tiers[q] = generate_bead_pattern(
                    img_rgba=target_img,
                    quality=q,
                    palette_id=pal_id,
                    remove_bg=rem_bg,
                    custom_max_side=c_side,
                )
            auto_apply = {
                "image_id": target_img_id,
                "source_width": target_img.size[0],
                "source_height": target_img.size[1],
                "source_data_url": image_to_data_url_fn(target_img),
                "tiers": tiers,
                "active_quality": q,
                "palette_id": pal_id,
                "remove_bg": rem_bg,
            }
            tool_steps.append({"step": "adjust_canvas", "label": f"已按要求更新画板为 {tiers[q]['quality_name']} 模式"})

        return {
            "reply": str(plan.get("reply") or "已为您同步调整画板参数并重新测算拼豆工时！"),
            "tool_steps": tool_steps,
            "recommendations": [],
            "auto_apply": auto_apply,
        }

    # 若用户请求搜图但尚未填 Tavily Key，且大模型可用 -> 自动优雅切换为大模型原创 SVG 绘制拼豆图案！
    if action == "search_recommend" and not tavily_ready and llm_ready:
        tool_steps.append(
            {
                "step": "fallback_svg",
                "label": "未检测到 Tavily 搜索密钥，已自动切换为大模型原创矢量绘制生成拼豆图",
            }
        )
        svg_prompt = [
            {
                "role": "system",
                "content": (
                    "请根据用户的描述创作一幅色彩饱满、轮廓清晰、适合转换成拼豆像素画的居中卡通插画，仅输出一段完整的 "
                    "<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320' viewBox='0 0 320 320'>...</svg> 代码，背景使用纯白 #FFFFFF。"
                ),
            },
            {"role": "user", "content": user_last},
        ]
        svg_raw = call_llm_chat(svg_prompt, cfg=cfg, temperature=0.5, max_tokens=1800)
        start_svg = svg_raw.find("<svg")
        end_svg = svg_raw.rfind("</svg>")
        if start_svg != -1 and end_svg != -1:
            plan["svg"] = svg_raw[start_svg : end_svg + 6]
            plan["title"] = f"AI 原创 · {user_last[:14]}"
            action = "draw_svg"

    # 动作分支 C: 大模型原创 SVG 插画转拼豆图
    if action == "draw_svg":
        svg_code = str(plan.get("svg") or "").strip()
        if "<svg" not in svg_code:
            raise RuntimeError("模型未能生成有效的矢量插画代码，请重试或配置 Tavily 搜索密钥直接联网找图")

        png_bytes = _rasterize_svg_to_png_bytes(svg_code)
        img = load_normalized_rgba(png_bytes)
        img_id = store_image_fn(img)

        q = str(plan.get("quality") or "hd")
        if q not in ("simple", "hd", "faithful"):
            q = "hd"
        pal_id = str(plan.get("palette_id") or canvas_context.get("palette_id") or "mard_96")
        rem_bg = bool(plan.get("remove_bg", True))

        tiers = generate_all_tiers_summary(img_rgba=img, palette_id=pal_id, remove_bg=rem_bg)
        chosen = tiers[q]
        est_str = chosen["time_estimate"]["profiles"]["standard"]["formatted"]
        preview_url = render_bead_preview_thumbnail(chosen)
        src_url = image_to_data_url_fn(img)
        title = str(plan.get("title") or "AI 原创拼豆图案")

        rec_card = {
            "image_id": img_id,
            "title": title,
            "source_domain": "AI 原创矢量绘制",
            "quality": q,
            "quality_name": chosen["quality_name"],
            "palette_id": pal_id,
            "remove_bg": rem_bg,
            "grid_width": chosen["grid_width"],
            "grid_height": chosen["grid_height"],
            "total_beads": chosen["total_beads"],
            "unique_colors": chosen["unique_colors"],
            "estimated_time": est_str,
            "scattered_ratio": chosen["time_estimate"]["spatial_stats"]["scattered_ratio"],
            "bead_preview_url": preview_url,
            "source_thumb_url": src_url,
        }
        tool_steps.append(
            {
                "step": "svg_to_bead",
                "label": f"已完成原创绘制并生成三档拼豆图纸（{chosen['quality_name']}档 {chosen['total_beads']} 颗 · 约 {est_str}）",
            }
        )
        note_suffix = "" if tavily_ready else "（提示：若在右上角填入 Tavily API Key，还可以直接联网检索全网角色原图推荐拼豆方案！）"
        return {
            "reply": f"已为您原创绘制「{title}」并转换为拼豆图纸！当前按 **{chosen['quality_name']}模式**（`{chosen['grid_width']}×{chosen['grid_height']}` 格，共 **{chosen['total_beads']} 颗豆** / {chosen['unique_colors']} 色）预估制作时长约 **{est_str}**，已同步铺设至中央工作台。{note_suffix}",
            "tool_steps": tool_steps,
            "recommendations": [rec_card],
            "auto_apply": {
                "image_id": img_id,
                "source_width": img.size[0],
                "source_height": img.size[1],
                "source_data_url": src_url,
                "tiers": tiers,
                "active_quality": q,
                "palette_id": pal_id,
                "remove_bg": rem_bg,
            },
        }

    # 动作分支 D: Tavily 联网图文搜索 + 并发下载清洗 + 拼豆量化与工时排序推荐
    query = str(plan.get("search_query") or user_last).strip()
    backup_query = str(plan.get("backup_query") or query).strip()
    q = str(plan.get("quality") or "hd")
    if q not in ("simple", "hd", "faithful"):
        q = "hd"
    pal_id = str(plan.get("palette_id") or canvas_context.get("palette_id") or "mard_96")
    rem_bg = bool(plan.get("remove_bg", True))
    max_min_hint = plan.get("max_minutes_hint")

    tav_res = tavily_search(query=query, cfg=cfg, max_results=6, include_images=True)
    raw_candidates = list(tav_res["images"])
    tool_steps.append(
        {
            "step": "tavily_search",
            "label": f"Tavily 联网检索「{query}」：命中 {len(tav_res['results'])} 条网页资料与 {len(raw_candidates)} 张候选图",
        }
    )

    # 若首轮图片较少且提供了备选检索词，补充一次检索
    if len(raw_candidates) < 4 and backup_query and backup_query != query:
        try:
            tav_res2 = tavily_search(query=backup_query, cfg=cfg, max_results=5, include_images=True)
            raw_candidates.extend(tav_res2["images"])
        except Exception:
            pass

    if cfg.get("enable_backup_image_search", True) and len(raw_candidates) < 6:
        raw_candidates.extend(fetch_backup_images(query, cfg=cfg, limit=6))

    downloaded = download_valid_candidate_images(raw_candidates, cfg=cfg, target_count=4)
    if not downloaded and cfg.get("enable_backup_image_search", True):
        extra = fetch_backup_images(backup_query, cfg=cfg, limit=8)
        downloaded = download_valid_candidate_images(extra, cfg=cfg, target_count=4)

    recommendations: List[Dict[str, Any]] = []
    scored_items: List[tuple[float, Image.Image, Dict[str, Any]]] = []

    for meta_item, png_bytes in downloaded:
        try:
            img = load_normalized_rgba(png_bytes)
            pat = generate_bead_pattern(img_rgba=img, quality=q, palette_id=pal_id, remove_bg=rem_bg)
            # 过滤纯空白或单色无效图
            if pat["total_beads"] < 25 or pat["unique_colors"] < 2:
                continue

            img_id = store_image_fn(img)
            std_prof = pat["time_estimate"]["profiles"]["standard"]
            est_min = std_prof["total_minutes"]

            # 贴合度打分：若用户指定了期望分钟数，越接近目标且散点率越低排名越靠前
            scatter_penalty = pat["time_estimate"]["spatial_stats"]["scattered_ratio"] * 0.4
            time_penalty = abs(est_min - max_min_hint) * 0.8 if isinstance(max_min_hint, (int, float)) else 0.0
            rank_score = time_penalty + scatter_penalty

            card = {
                "image_id": img_id,
                "title": meta_item.get("title") or query,
                "source_domain": meta_item.get("source_domain") or "Web",
                "quality": q,
                "quality_name": pat["quality_name"],
                "palette_id": pal_id,
                "remove_bg": rem_bg,
                "grid_width": pat["grid_width"],
                "grid_height": pat["grid_height"],
                "total_beads": pat["total_beads"],
                "unique_colors": pat["unique_colors"],
                "estimated_time": std_prof["formatted"],
                "estimated_minutes": est_min,
                "scattered_ratio": pat["time_estimate"]["spatial_stats"]["scattered_ratio"],
                "bead_preview_url": render_bead_preview_thumbnail(pat),
                "source_thumb_url": image_to_data_url_fn(img),
            }
            scored_items.append((rank_score, img, card))
        except Exception:
            continue

    scored_items.sort(key=lambda x: x[0])
    recommendations = [item[2] for item in scored_items[:4]]

    auto_apply = None
    if scored_items and plan.get("auto_apply_best", True):
        _, best_img, best_card = scored_items[0]
        best_tiers = generate_all_tiers_summary(img_rgba=best_img, palette_id=pal_id, remove_bg=rem_bg)
        auto_apply = {
            "image_id": best_card["image_id"],
            "source_width": best_img.size[0],
            "source_height": best_img.size[1],
            "source_data_url": best_card["source_thumb_url"],
            "tiers": best_tiers,
            "active_quality": q,
            "palette_id": pal_id,
            "remove_bg": rem_bg,
        }
        tool_steps.append(
            {
                "step": "bead_quantize",
                "label": f"已转换 {len(recommendations)} 款候选拼豆方案并按可拼度排序，最佳匹配已同步至画布",
            }
        )

    reply_text = _synthesize_recommendation_reply(
        user_prompt=user_last,
        candidates_meta=recommendations,
        web_snippets=tav_res["results"],
        tavily_answer=tav_res["answer"],
        cfg=cfg,
        llm_ready=llm_ready,
    )

    return {
        "reply": reply_text,
        "tool_steps": tool_steps,
        "recommendations": recommendations,
        "auto_apply": auto_apply,
    }
