#!/usr/bin/env python3
"""Build the BidRadar-X Chinese demo video from real UI captures.

The narration is synthesized locally with the macOS Reed Mandarin voice.
FFmpeg is used only for deterministic composition and encoding.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
import textwrap
import wave
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "demo"
ASSETS = OUT / "assets"
SLIDES = OUT / "slides"
AUDIO = OUT / "audio"
SEGMENTS = OUT / "segments"
WIDTH, HEIGHT = 1920, 1080

BG = "#f5f5f2"
PAPER = "#ffffff"
INK = "#1d1d1f"
MUTED = "#73757a"
BLUE = "#0a72e8"
BLUE_SOFT = "#eaf3ff"
GREEN = "#248a45"
GREEN_SOFT = "#eaf6ed"
ORANGE = "#c87942"
LINE = "#e4e4df"

FONT_SANS = Path("/System/Library/Fonts/STHeiti Medium.ttc")
FONT_SERIF = Path("/System/Library/Fonts/Supplemental/Songti.ttc")


@dataclass(frozen=True)
class Scene:
    slug: str
    eyebrow: str
    title: str
    narration: str


SCENES = [
    Scene(
        "01-opening",
        "BIDRADAR-X · DEMO",
        "从一句话，到一组可执行的投标机会",
        "这是 BidRadar-X，一套证据驱动的招投标智能情报工作台。它把一句自然语言需求，自动转化为可追溯、可下载、可持续更新的项目机会。",
    ),
    Scene(
        "02-requirements",
        "COMPETITION REQUIREMENTS",
        "赛题主链路，逐项落到产品动作",
        "赛题要求系统识别主题、地区、时间与频率，至少检索两个互联网来源，完成清洗、去重和条件过滤，再输出多份 Word。对于每日或每周任务，还必须只推送新增内容。BidRadar-X 按这条主链路逐项实现；账户授权型来源由独立适配器承载，演示中不公开用户凭据。",
    ),
    Scene(
        "03-intent",
        "NATURAL LANGUAGE ORCHESTRATION",
        "自然语言直接驱动，不需要填写复杂表单",
        "用户只需输入，例如：查找最近一个月上海市的充电桩招标信息，每周更新。后端先执行意图解析，把句子结构化为主题、地区、时间窗口和调度频率；随后自动进入任务编排，无需二次确认。",
    ),
    Scene(
        "04-sources",
        "SOURCE ADAPTER LAYER",
        "多源检索，不是一个脆弱的巨型爬虫",
        "语义理解之后，模型执行 Query Expansion，扩展同义词、相关词和检索组合。采集层采用 Source Adapter 架构，接入政府平台、公共资源交易平台、中国移动采购与招标网、TED，以及可配置的天眼查和 SAM.gov 授权接口。每个来源独立限流、重试和记录失败原因，单站异常不会伪装成零结果。",
    ),
    Scene(
        "05-pipeline",
        "AUTOMATED EVIDENCE PIPELINE",
        "五段式自动链路，全过程可解释",
        "系统依次完成五个阶段：第一，理解检索意图；第二，扩展检索词；第三，并发访问已接入信息源；第四，清洗、审核与查重；第五，生成项目 Word。每一步都返回结构化状态，失败会就地停止，不会把空任务写进项目报告。",
    ),
    Scene(
        "06-report",
        "FACT-BOUND REPORTING",
        "AI 可以总结，但不能改写公告事实",
        "清洗阶段只保留仍在招标的项目，排除已中标、流标和重复公告。跨站内容先做规则指纹，再做语义复核。标题、发布时间、来源链接、核心内容与附件入口都会保留；预算、截止时间和资质等事实必须绑定 Evidence Reference。AI 只生成辅助摘要与风险研判，不能凭空补写精确数据。每个项目单独生成一份 Word。",
    ),
    Scene(
        "07-insight",
        "PROJECT INTELLIGENCE",
        "从“找到公告”升级为“辅助投标决策”",
        "项目卡片进一步抽取采购人、联系人、电话、预算、投标截止、资格资质、工期、评审办法与附件。用户可以多选指标、查看原文证据、打开本地归档文件，并把重点项目加入收藏。这样，信息检索被转换成可核验的投标准备清单。",
    ),
    Scene(
        "08-schedule",
        "PERSISTENT INCREMENTAL DELIVERY",
        "定时任务只交付新增与实质变化",
        "当用户说每天、每周或每三分钟，调度器会把自然语言频率保存为持久化任务。后端持续运行即可按时触发，前端可以关闭。每次执行都与历史快照比对，利用幂等键和水位线过滤旧内容；没有新增就明确显示无新增，有变化才生成新的项目文档。",
    ),
    Scene(
        "09-engineering",
        "PRODUCTION GUARDRAILS",
        "可靠性与成本控制，写进后端而不是写在口号里",
        "工程侧采用后端密钥隔离、原子预算检查、适配器故障隔离、可恢复重试和本地持久化。下一次付费调用如果会超过每日预算，请求会在发出前被强制中断。核心事实一致性、来源解析、调度、Word 和外部投递都有自动化测试覆盖。",
    ),
    Scene(
        "10-feishu",
        "ROADMAP · FEISHU ENTERPRISE KNOWLEDGE BASE",
        "下一步：把新增项目自动归档到飞书知识库",
        "下一阶段将启用飞书企业自建应用。定时任务完成后，新增项目先写入 Transactional Outbox，再由投递服务写入飞书多维表格，并用机器人发送通知。这样可以避免抓取成功但外部推送丢失，同时形成企业内部可检索的招投标知识库。该能力已具备接口与重试设计，正式上线仍需企业飞书凭据和表格授权。",
    ),
    Scene(
        "11-closing",
        "BIDRADAR-X",
        "检索有来源，结论有证据，更新不重复",
        "BidRadar-X 覆盖了赛题从输入到输出的完整操作链路，并在证据约束、增量订阅、预算防线和可解释项目洞察上继续向前一步。让招投标信息不再只是被搜索，而是被持续理解、核验和交付。本片中文男声由人工智能合成。",
    ),
]


def font(size: int, serif: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_SERIF if serif and FONT_SERIF.exists() else FONT_SANS
    return ImageFont.truetype(str(path), size=size)


def canvas() -> Image.Image:
    return Image.new("RGB", (WIDTH, HEIGHT), BG)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if current and draw.textbbox((0, 0), trial, font=fnt)[2] > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def text_block(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fnt: ImageFont.FreeTypeFont,
               fill: str, max_width: int, line_gap: int = 12, max_lines: int | None = None) -> int:
    x, y = xy
    lines = wrap(draw, text, fnt, max_width)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    line_h = fnt.getbbox("国")[3] - fnt.getbbox("国")[1]
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h + line_gap
    return y


def shadow_card(img: Image.Image, box: tuple[int, int, int, int], radius: int = 34,
                fill: str = PAPER, shadow: int = 18) -> None:
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((x0, y0 + 12, x1, y1 + 12), radius=radius, fill=(0, 0, 0, 32))
    layer = layer.filter(ImageFilter.GaussianBlur(shadow))
    img.paste(layer, (0, 0), layer)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline="#ecece8", width=2)


def header(img: Image.Image, scene: Scene, number: int) -> ImageDraw.ImageDraw:
    d = ImageDraw.Draw(img)
    d.text((90, 60), scene.eyebrow, font=font(24), fill=MUTED)
    d.text((90, 108), scene.title, font=font(58, serif=True), fill=INK)
    d.rounded_rectangle((1730, 58, 1830, 102), radius=22, fill=INK)
    d.text((1762, 66), f"{number:02d}", font=font(22), fill=PAPER)
    d.line((90, 198, 1830, 198), fill=LINE, width=2)
    return d


def paste_rounded(base: Image.Image, asset_name: str, box: tuple[int, int, int, int], radius: int = 28,
                  crop: str = "fit") -> None:
    src = Image.open(ASSETS / asset_name).convert("RGB")
    x0, y0, x1, y1 = box
    target_w, target_h = x1 - x0, y1 - y0
    if crop == "cover":
        scale = max(target_w / src.width, target_h / src.height)
    else:
        scale = min(target_w / src.width, target_h / src.height)
    resized = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.Resampling.LANCZOS)
    frame = Image.new("RGB", (target_w, target_h), "#eef0ef")
    if crop == "cover":
        left = max(0, (resized.width - target_w) // 2)
        top = max(0, (resized.height - target_h) // 2)
        resized = resized.crop((left, top, left + target_w, top + target_h))
        frame.paste(resized, (0, 0))
    else:
        frame.paste(resized, ((target_w - resized.width) // 2, (target_h - resized.height) // 2))
    mask = Image.new("L", (target_w, target_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, target_w, target_h), radius=radius, fill=255)
    base.paste(frame, (x0, y0), mask)


def pill(d: ImageDraw.ImageDraw, xy: tuple[int, int], label: str, fill: str = BLUE_SOFT,
         color: str = BLUE, width: int | None = None) -> None:
    x, y = xy
    fnt = font(22)
    tw = d.textbbox((0, 0), label, font=fnt)[2]
    w = width or tw + 42
    d.rounded_rectangle((x, y, x + w, y + 46), radius=23, fill=fill)
    d.text((x + 21, y + 9), label, font=fnt, fill=color)


def slide_opening(scene: Scene, idx: int) -> Image.Image:
    img = canvas()
    d = ImageDraw.Draw(img)
    d.ellipse((1310, -170, 2110, 630), fill="#e8f2ff")
    d.ellipse((-300, 760, 420, 1480), fill="#e9f4eb")
    d.rounded_rectangle((92, 82, 178, 168), radius=24, fill=INK)
    d.text((112, 101), "BR", font=font(28), fill=PAPER)
    d.text((210, 105), scene.eyebrow, font=font(24), fill=MUTED)
    text_block(d, (150, 310), scene.title, font(76, serif=True), INK, 1500, 20, 2)
    d.text((156, 565), "自然语言  →  多源采集  →  清洗核验  →  Word 与增量订阅", font=font(30), fill=MUTED)
    for x, label, color in [(156, "可解释", BLUE), (330, "证据约束", GREEN), (540, "持续更新", ORANGE)]:
        pill(d, (x, 685), label, fill=PAPER, color=color)
    d.text((156, 940), "招投标情报工作台 · 演示视频", font=font(22), fill=MUTED)
    return img


def slide_requirements(scene: Scene, idx: int) -> Image.Image:
    img = canvas(); d = header(img, scene, idx)
    items = [
        ("01", "自然语言识别", "主题 / 地区 / 时间 / 频率"),
        ("02", "互联网信息源", "多站检索 + 账户授权型适配器"),
        ("03", "数据治理", "正文清洗 / 去重 / 条件过滤"),
        ("04", "事实汇总", "标题 / 时间 / 来源 / 核心内容 / 附件"),
        ("05", "Word 交付", "一个项目一份文档，可分别下载"),
        ("06", "定时增量", "每日 / 每周 / 分钟级，只推新增"),
    ]
    positions = [(90, 250), (655, 250), (1220, 250), (90, 580), (655, 580), (1220, 580)]
    for (num, title, sub), (x, y) in zip(items, positions):
        shadow_card(img, (x, y, x + 520, y + 255), radius=30)
        d.ellipse((x + 34, y + 34, x + 92, y + 92), fill=GREEN)
        d.text((x + 52, y + 44), "✓", font=font(28), fill=PAPER)
        d.text((x + 112, y + 36), title, font=font(34, serif=True), fill=INK)
        d.text((x + 38, y + 122), sub, font=font(23), fill=MUTED)
        d.text((x + 430, y + 194), num, font=font(20), fill="#b4b5b7")
    return img


def slide_screenshot(scene: Scene, idx: int, asset: str, callouts: list[tuple[str, str]],
                     crop: str = "fit") -> Image.Image:
    img = canvas(); d = header(img, scene, idx)
    shadow_card(img, (70, 230, 1360, 1010), radius=34)
    paste_rounded(img, asset, (90, 250, 1340, 990), radius=24, crop=crop)
    y = 260
    for title, body in callouts:
        shadow_card(img, (1410, y, 1840, y + 190), radius=26, fill=PAPER, shadow=12)
        d.ellipse((1440, y + 38, 1462, y + 60), fill=GREEN)
        d.text((1482, y + 25), title, font=font(27, serif=True), fill=INK)
        text_block(d, (1440, y + 83), body, font(20), MUTED, 360, 8, 3)
        y += 220
    return img


def slide_pipeline(scene: Scene, idx: int) -> Image.Image:
    img = canvas(); d = header(img, scene, idx)
    labels = [
        ("01", "意图解析", "topic · region\ntime_window · schedule"),
        ("02", "智能扩词", "同义词 · 相关词\n检索组合"),
        ("03", "多源采集", "Adapter 并发\n限流 · 重试"),
        ("04", "清洗核验", "状态过滤 · 去重\nEvidence Reference"),
        ("05", "文档交付", "项目 Word\n附件与增量"),
    ]
    xs = [70, 440, 810, 1180, 1550]
    for i, ((num, title, sub), x) in enumerate(zip(labels, xs)):
        if i < 4:
            d.line((x + 295, 548, x + 365, 548), fill="#b8d5f7", width=6)
            d.polygon([(x + 350, 535), (x + 370, 548), (x + 350, 561)], fill=BLUE)
        shadow_card(img, (x, 360, x + 310, 745), radius=34, fill=PAPER)
        d.ellipse((x + 34, 400, x + 106, 472), fill=GREEN if i < 4 else BLUE)
        d.text((x + 57, 417), "✓" if i < 4 else num, font=font(29), fill=PAPER)
        d.text((x + 36, 510), title, font=font(34, serif=True), fill=INK)
        text_block(d, (x + 36, 580), sub, font(20), MUTED, 240, 10, 3)
        pill(d, (x + 36, 670), "结构化状态", fill=GREEN_SOFT if i < 4 else BLUE_SOFT,
             color=GREEN if i < 4 else BLUE, width=190)
    d.rounded_rectangle((70, 825, 1860, 935), radius=32, fill="#edf4fc")
    d.text((110, 856), "失败即停 · 空结果不入库 · 过程状态可追踪 · 原文证据可回溯", font=font(30), fill="#315d7d")
    return img


def slide_report(scene: Scene, idx: int) -> Image.Image:
    img = canvas(); d = header(img, scene, idx)
    shadow_card(img, (80, 240, 810, 990), radius=34)
    paste_rounded(img, "word-thumbnail.png", (118, 280, 772, 770), radius=22, crop="fit")
    pill(d, (120, 814), "每个项目一份 Word", fill=INK, color=PAPER, width=280)
    pill(d, (420, 814), "可分别下载", fill=BLUE_SOFT, color=BLUE, width=190)
    d.text((122, 890), "AI 辅助摘要 · 风险研判 · 原文证据 ID", font=font(25), fill=MUTED)
    shadow_card(img, (860, 240, 1840, 990), radius=34)
    d.text((920, 290), "赛题要求字段", font=font(36, serif=True), fill=INK)
    fields = ["标题", "发布时间", "来源链接", "核心内容", "附件链接（如有）"]
    y = 380
    for f in fields:
        d.ellipse((922, y + 10, 946, y + 34), fill=GREEN)
        d.text((970, y), f, font=font(29), fill=INK)
        d.text((1435, y + 3), "证据约束", font=font(21), fill=GREEN)
        d.line((970, y + 53, 1775, y + 53), fill=LINE, width=2)
        y += 94
    d.rounded_rectangle((920, 865, 1775, 940), radius=22, fill="#fff7eb")
    d.text((954, 887), "AI 不改写事实，只在证据边界内总结", font=font(25), fill="#8a5a25")
    return img


def slide_insight(scene: Scene, idx: int) -> Image.Image:
    img = canvas(); d = header(img, scene, idx)
    shadow_card(img, (70, 235, 650, 1010), radius=34)
    paste_rounded(img, "structured-detail.png", (95, 260, 625, 985), radius=24, crop="cover")
    shadow_card(img, (710, 235, 1845, 1010), radius=34)
    d.text((770, 285), "项目重点", font=font(42, serif=True), fill=INK)
    d.text((1670, 300), "8 项证据", font=font(22), fill=GREEN)
    cards = [
        ("采购预算 / 最高限价", "3,409,287 CNY", "公告结构化字段"),
        ("投标 / 响应截止", "2026-07-27 09:00", "公告正文"),
        ("资格与资质要求", "建筑机电安装专业承包", "原文第 3 条"),
        ("项目联系人", "吴女士 · 139****2024", "联系方式可核验"),
        ("附件与 PDF", "已归档到本地", "一键打开原文件"),
        ("收藏与跟踪", "持续更新", "项目快照"),
    ]
    positions = [(770, 375), (1290, 375), (770, 585), (1290, 585), (770, 795), (1290, 795)]
    for (label, value, source), (x, y) in zip(cards, positions):
        d.rounded_rectangle((x, y, x + 465, y + 165), radius=26, fill="#f5f5f7")
        d.text((x + 28, y + 26), label, font=font(20), fill=MUTED)
        text_block(d, (x + 28, y + 67), value, font(27, serif=True), INK, 400, 6, 2)
        d.text((x + 28, y + 127), source, font=font(18), fill=GREEN)
    return img


def slide_engineering(scene: Scene, idx: int) -> Image.Image:
    img = slide_screenshot(scene, idx, "interfaces.png", [
        ("Backend Spend Guard", "下一次请求若会超限，在发出前原子拦截。"),
        ("Secret Isolation", "API Key 只在后端环境加载，浏览器不保存。"),
        ("Failure Isolation", "来源分级失败、可恢复重试、原因可观测。"),
    ], crop="cover")
    return img


def slide_feishu(scene: Scene, idx: int) -> Image.Image:
    img = canvas(); d = header(img, scene, idx)
    pill(d, (90, 235), "即将上线 · 需企业凭据授权", fill="#fff4df", color="#956121", width=370)
    nodes = [
        ("定时任务", "新增项目快照", BLUE_SOFT, BLUE),
        ("Transactional Outbox", "同事务写入待投递事件", GREEN_SOFT, GREEN),
        ("飞书 Bitable", "结构化写入多维表格", "#f0ecff", "#6e56cf"),
        ("企业知识库", "归档、检索与协作", "#fff0e8", ORANGE),
    ]
    xs = [80, 520, 960, 1400]
    for i, ((title, sub, fill, color), x) in enumerate(zip(nodes, xs)):
        if i < 3:
            d.line((x + 330, 575, x + 430, 575), fill="#b9cce5", width=6)
            d.polygon([(x + 415, 561), (x + 438, 575), (x + 415, 589)], fill=color)
        shadow_card(img, (x, 405, x + 360, 745), radius=34)
        d.rounded_rectangle((x + 34, 445, x + 112, 523), radius=22, fill=fill)
        d.text((x + 58, 461), str(i + 1), font=font(31), fill=color)
        d.text((x + 34, 560), title, font=font(31, serif=True), fill=INK)
        text_block(d, (x + 34, 625), sub, font(20), MUTED, 290, 8, 2)
    d.rounded_rectangle((80, 820, 1760, 948), radius=32, fill="#eef6f0")
    d.text((125, 850), "可靠投递：幂等键  ·  指数退避  ·  状态可追踪  ·  失败可重放  ·  机器人通知", font=font(29), fill="#315d45")
    return img


def slide_closing(scene: Scene, idx: int) -> Image.Image:
    img = canvas(); d = ImageDraw.Draw(img)
    d.ellipse((1250, -260, 2220, 710), fill="#e9f3ff")
    d.ellipse((-350, 760, 440, 1550), fill="#eaf5ec")
    d.text((100, 100), scene.eyebrow, font=font(26), fill=MUTED)
    text_block(d, (190, 310), scene.title, font(72, serif=True), INK, 1500, 22, 2)
    y = 620
    for label, color in [("多源采集", BLUE), ("事实核验", GREEN), ("增量交付", ORANGE), ("可解释决策", "#6e56cf")]:
        pill(d, (190, y), label, fill=PAPER, color=color, width=230)
        y += 62
    d.text((1160, 850), "BidRadar-X", font=font(58, serif=True), fill=INK)
    d.text((1164, 930), "本片中文男声由人工智能合成", font=font(20), fill=MUTED)
    return img


def render_slides() -> None:
    for p in (SLIDES, AUDIO, SEGMENTS):
        p.mkdir(parents=True, exist_ok=True)
    builders = [
        slide_opening,
        slide_requirements,
        lambda s, i: slide_screenshot(s, i, "project.png", [
            ("意图解析", "主题、地区、时间窗口与调度频率结构化。"),
            ("无需二次确认", "提交后直接进入自动任务编排。"),
            ("自然语言调度", "每天、每周与分钟级间隔均可识别。"),
        ]),
        lambda s, i: slide_screenshot(s, i, "sources.png", [
            ("Source Adapter", "每个网站独立实现、独立重试。"),
            ("账户授权", "敏感凭据只在后端；演示不公开。"),
            ("失败可解释", "区分零结果、登录失败与站点异常。"),
        ], crop="cover"),
        slide_pipeline,
        slide_report,
        slide_insight,
        lambda s, i: slide_screenshot(s, i, "schedule.png", [
            ("持久化调度", "后端持续运行，前端可以关闭。"),
            ("Snapshot Diff", "水位线与幂等键识别真实新增。"),
            ("不重复推送", "无新增明确提示，有变化才生成文档。"),
        ]),
        slide_engineering,
        slide_feishu,
        slide_closing,
    ]
    for idx, (scene, builder) in enumerate(zip(SCENES, builders), start=1):
        image = builder(scene, idx)
        image.save(SLIDES / f"{scene.slug}.png", quality=95)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def synthesize_voice() -> None:
    if not shutil.which("say"):
        raise RuntimeError("macOS say is required")
    for scene in SCENES:
        target = AUDIO / f"{scene.slug}.aiff"
        # Use the explicit Simplified-Chinese Reed variant. The bare "Reed"
        # alias can resolve to a non-Chinese locale and silently skip Han text.
        run(["say", "-v", "Reed (中文（中国大陆）)", "-r", "185", "-o", str(target), scene.narration])


def duration(path: Path) -> float:
    value = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(value)


def timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    h, rem = divmod(millis, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_subtitles(durations: list[float]) -> None:
    cursor = 0.0
    entries = []
    for idx, (scene, dur) in enumerate(zip(SCENES, durations), start=1):
        start = cursor + 0.15
        end = cursor + max(0.3, dur - 0.15)
        entries.append(f"{idx}\n{timestamp(start)} --> {timestamp(end)}\n{scene.narration}\n")
        cursor += dur
    (OUT / "BidRadar-X-Demo-zh-CN.srt").write_text("\n".join(entries), encoding="utf-8")
    script = "# BidRadar-X Demo 中文旁白\n\n" + "\n\n".join(
        f"## {idx:02d} {scene.title}\n\n{scene.narration}" for idx, scene in enumerate(SCENES, start=1)
    )
    script += "\n\n> 配音声明：本片中文男声由人工智能合成。\n"
    (OUT / "BidRadar-X-Demo-旁白稿.md").write_text(script, encoding="utf-8")


def synthesize_music(total_seconds: float) -> Path:
    sample_rate = 22050
    target = AUDIO / "original-ambient-bed.wav"
    chords = [(110.0, 164.81, 220.0), (98.0, 146.83, 196.0), (123.47, 185.0, 246.94), (82.41, 123.47, 164.81)]
    frames = int((total_seconds + 2) * sample_rate)
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(sample_rate)
        buf = bytearray()
        for n in range(frames):
            t = n / sample_rate
            chord = chords[int(t // 8) % len(chords)]
            swell = 0.55 + 0.45 * math.sin(2 * math.pi * t / 12.0) ** 2
            value = sum(math.sin(2 * math.pi * f * t) for f in chord) / len(chord)
            shimmer = 0.18 * math.sin(2 * math.pi * chord[-1] * 2 * t + math.sin(t * 0.3))
            sample = int(max(-1, min(1, (value + shimmer) * 0.075 * swell)) * 32767)
            left = sample
            right = int(sample * (0.93 + 0.05 * math.sin(t * 0.4)))
            buf += int(left).to_bytes(2, "little", signed=True)
            buf += int(right).to_bytes(2, "little", signed=True)
            if len(buf) >= 262144:
                wav.writeframesraw(buf); buf.clear()
        if buf:
            wav.writeframesraw(buf)
    return target


def build_segments() -> list[float]:
    durations: list[float] = []
    for scene in SCENES:
        audio = AUDIO / f"{scene.slug}.aiff"
        dur = duration(audio) + 0.55
        durations.append(dur)
        slide = SLIDES / f"{scene.slug}.png"
        target = SEGMENTS / f"{scene.slug}.mp4"
        frames = max(1, int(dur * 30))
        vf = (
            "scale=1960:1103,crop=1920:1080,"
            f"zoompan=z='min(zoom+0.000045,1.018)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30,format=yuv420p"
        )
        run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(slide), "-i", str(audio),
            "-vf", vf, "-af", "apad=pad_dur=0.55", "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(target),
        ])
    return durations


def compose(durations: list[float]) -> Path:
    concat = OUT / "segments.txt"
    concat.write_text("".join(f"file '{(SEGMENTS / (s.slug + '.mp4')).as_posix()}'\n" for s in SCENES), encoding="utf-8")
    raw = OUT / "BidRadar-X-Demo-zh-CN-raw.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(raw)])
    music = synthesize_music(sum(durations))
    final = OUT / "BidRadar-X-Demo-zh-CN.mp4"
    run([
        "ffmpeg", "-y", "-i", str(raw), "-i", str(music),
        "-filter_complex", "[0:a]volume=1.0[voice];[1:a]volume=0.12[bed];[voice][bed]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(final),
    ])
    return final


def main() -> int:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ffmpeg/ffprobe not found", file=sys.stderr)
        return 2
    render_slides()
    synthesize_voice()
    durations = build_segments()
    write_subtitles(durations)
    final = compose(durations)
    print(f"Built {final} ({duration(final):.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
