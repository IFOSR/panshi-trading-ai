"""Generate a logical architecture diagram for panshi-trading-ai."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def get_font(size: int) -> ImageFont.FreeTypeFont:
    # Prefer CJK fonts first so Chinese text renders correctly.
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: str,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def main() -> None:
    width, height = 1600, 1200
    img = Image.new("RGB", (width, height), "#f8f9fa")
    draw = ImageDraw.Draw(img)

    title_font = get_font(26)
    header_font = get_font(18)
    body_font = get_font(14)
    small_font = get_font(12)

    # Title
    title = "磐石交易AI 逻辑架构图"
    tw, th = text_size(draw, title, title_font)
    draw.text(((width - tw) // 2, 20), title, fill="#1a1a2e", font=title_font)

    # Colors
    user_color = "#e3f2fd"
    web_color = "#fff3e0"
    api_color = "#e8f5e9"
    persistence_color = "#fce4ec"
    external_color = "#f3e5f5"
    internal_color = "#e0f7fa"
    output_color = "#fffde7"
    arrow_color = "#555555"

    # Layout helpers
    def box(x: int, y: int, w: int, h: int, label: str, sub: str, fill: str) -> tuple[int, int, int, int]:
        draw_rounded_rect(draw, (x, y, x + w, y + h), 10, fill=fill, outline="#333333", width=2)
        lw, lh = text_size(draw, label, header_font)
        draw.text((x + (w - lw) // 2, y + 12), label, fill="#1a1a2e", font=header_font)
        # subtext lines
        lines = sub.split("\n")
        cy = y + 38
        for line in lines:
            sw, sh = text_size(draw, line, body_font)
            draw.text((x + (w - sw) // 2, cy), line, fill="#444444", font=body_font)
            cy += sh + 4
        return x, y, x + w, y + h

    # Row 1: User + Web
    user_b = box(60, 80, 180, 90, "用户", "问题 + 原图\n私有持仓/风控", user_color)
    web_b = box(380, 80, 220, 90, "Next.js Web :8989", "登录 / 对话 / 附件\n策略选择 / 历史记录", web_color)

    # Row 2: FastAPI + Persistence on sides
    db_b = box(60, 230, 220, 90, "持久化", "SQLite (本地)\nPostgreSQL (Docker)\n案例 / 会话 / 分析版本", persistence_color)
    api_b = box(380, 230, 300, 90, "FastAPI :8000", "API 鉴权 / 案例管理\n分析编排 / 会话管理", api_color)
    img_b = box(780, 230, 220, 90, "原图存储", ".local/data/images\nMinIO (Docker)", persistence_color)

    # Row 3: Internal services
    evidence_b = box(40, 420, 220, 110, "证据管道", "原图抽取 (Vision)\n行情合并 (Market)\n来源 / 冲突 / 置信度", internal_color)
    strategy_b = box(300, 420, 220, 110, "策略引擎", "策略注册表\n版本化策略插件\n里程碑计算", internal_color)
    risk_b = box(560, 420, 220, 110, "风险引擎", "风险预算 / 止损距离\n相关暴露 / 风险否决", internal_color)
    conv_b = box(820, 420, 220, 110, "对话与澄清", "结论解释\n后续追问\n澄清请求生成", internal_color)

    # Row 4: External providers
    codex_b = box(40, 620, 180, 90, "Codex 多模态", "直接读取原图\n结构化观察", external_color)
    kimi_b = box(260, 620, 180, 90, "Kimi 备用", "失效关闭降级\n外部隔离验证", external_color)
    tq_b = box(480, 620, 180, 90, "TqSdk", "主行情源\n中国期货", external_color)
    ak_b = box(700, 620, 180, 90, "AkShare", "自动降级源\n公开行情", external_color)

    # Row 5: Output
    output_b = box(430, 820, 240, 90, "可审计结论", "最终动作 / 依据\n阻断原因 / 下一条件", output_color)

    # Arrows helper
    def arrow(a: tuple[int, int, int, int], b: tuple[int, int, int, int], label: str = "") -> None:
        x1 = (a[0] + a[2]) // 2
        y1 = a[3]
        x2 = (b[0] + b[2]) // 2
        y2 = b[1]
        # Adjust for side connections if needed
        if abs(y1 - y2) < 20:
            x1 = a[2]
            x2 = b[0]
            y1 = (a[1] + a[3]) // 2
            y2 = (b[1] + b[3]) // 2
        draw.line([(x1, y1), (x2, y2)], fill=arrow_color, width=2)
        # Arrow head
        if y2 > y1:
            draw.polygon([(x2, y2), (x2 - 6, y2 - 10), (x2 + 6, y2 - 10)], fill=arrow_color)
        elif y2 < y1:
            draw.polygon([(x2, y2), (x2 - 6, y2 + 10), (x2 + 6, y2 + 10)], fill=arrow_color)
        elif x2 > x1:
            draw.polygon([(x2, y2), (x2 - 10, y2 - 6), (x2 - 10, y2 + 6)], fill=arrow_color)
        else:
            draw.polygon([(x2, y2), (x2 + 10, y2 - 6), (x2 + 10, y2 + 6)], fill=arrow_color)
        if label:
            lw, lh = text_size(draw, label, small_font)
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            draw.rounded_rectangle((mx - lw // 2 - 2, my - lh // 2 - 2, mx + lw // 2 + 2, my + lh // 2 + 2), radius=4, fill="#f8f9fa", outline="#cccccc")
            draw.text((mx - lw // 2, my - lh // 2), label, fill="#555555", font=small_font)

    # Connections
    arrow(user_b, web_b, "提交")
    arrow(web_b, api_b, "HTTP")

    arrow(api_b, db_b, "读写")
    arrow(api_b, img_b, "存原图")
    arrow(api_b, evidence_b, "调度")
    arrow(api_b, strategy_b, "执行")
    arrow(api_b, conv_b, "追问")

    arrow(evidence_b, codex_b, "原图")
    arrow(evidence_b, kimi_b, "降级")
    arrow(evidence_b, tq_b, "行情")
    arrow(evidence_b, ak_b, "降级")

    arrow(evidence_b, strategy_b, "合并证据")
    arrow(strategy_b, risk_b, "信号")
    arrow(risk_b, output_b, "校验")
    arrow(output_b, db_b, "保存")
    arrow(output_b, conv_b, "解释")
    arrow(conv_b, web_b, "SSE/HTTP")

    # Analysis flow note
    note = (
        "分析流程：用户提交 → 原图多模态抽取 → 公开行情补全 → 证据合并校验 → "
        "策略版本固定 → 里程碑计算 → 风险否决/通过 → 可审计结论 → 持续追问"
    )
    nw, nh = text_size(draw, note, body_font)
    draw.text(((width - nw) // 2, height - 60), note, fill="#333333", font=body_font)

    # Deployment modes note
    modes = (
        "本地轻量模式：Browser → Next.js :8989 → FastAPI :8000 → SQLite + 本地图片 + 进程内分析\n"
        "Docker 生产模式：+ PostgreSQL + Redis + MinIO + Temporal Worker + OTel Collector"
    )
    lines = modes.split("\n")
    my = height - 130
    for line in lines:
        lw, lh = text_size(draw, line, small_font)
        draw.text(((width - lw) // 2, my), line, fill="#666666", font=small_font)
        my += lh + 4

    out_path = Path(__file__).with_suffix(".png")
    img.save(out_path, "PNG")
    print(f"Saved architecture diagram to {out_path}")


if __name__ == "__main__":
    main()
