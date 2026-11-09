#!/usr/bin/env python3
"""Render the static profile artwork: banner, divider and sign-off.

Unlike gen_stats.py these carry no live data, so they are generated once and
committed rather than refreshed by the daily workflow. They live in a script
because the typing animation needs per-line character maths, and hand-editing
four clip widths and four caret positions every time a line changes is how
banners end up with the caret floating in empty space.

    python scripts/gen_art.py

Writes assets/banner.svg, assets/divider.svg, assets/signoff.svg, a strip and a
panel per tech-stack group under assets/tech/, and the matching <details>
blocks in README.md between the <!--techstack--> markers, plus one card per
featured project under assets/projects/ and the <!--projects--> block.
Every file carries a light and a dark palette; GitHub renders whichever the
reader's theme asks for.
"""

from __future__ import annotations

import json
import pathlib
import random
import re
import textwrap
from html import escape
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# Shared palette. Light is the default; dark overrides under the media query.
PALETTE = """
    svg {
      --sky0:#F4F8FE; --sky1:#DCE8FA; --ink:#0B1F33; --dim:#4A6076;
      --ac:#0B6FD4; --hi:#6A3DE8; --star:#2B4A68; --bd:#C9D6E5; --glass:#FFFFFF;
    }
    @media (prefers-color-scheme: dark) {
      svg {
        --sky0:#05070F; --sky1:#0C1A33; --ink:#E8F2FF; --dim:#8FB3C9;
        --ac:#36BCF7; --hi:#7C4DFF; --star:#FFFFFF; --bd:#1E3A52; --glass:#0D1117;
      }
    }
"""

# A fighter pointing right, drawn around its own origin.
JET = """<g class="jet-body">
      <rect x="-30" y="-2" width="24" height="4" rx="2" fill="url(#thrust)"/>
      <path d="M16,0 L-7,-6 L-2,0 L-7,6 Z" fill="var(--ac)"/>
      <path d="M-2,-3 L-13,-11 L-5,-3 Z" fill="var(--hi)"/>
      <path d="M-2,3 L-13,11 L-5,3 Z" fill="var(--hi)"/>
      <circle cx="-5" cy="0" r="2.6" fill="#FFFFFF" opacity=".92"/>
    </g>"""

W, H = 900, 300
MONO = 16          # terminal font size
ADV = 9.7          # advance width of one monospace glyph at that size
TX, TY = 78, 228   # where typed text starts
CYCLE = 16.0       # one full pass through all four lines

LINES = [
    "target    : aspect sentiment quad prediction",
    "payload   : MedGemma-4B + LoRA, soft-GIoU",
    "telemetry : 180 tests green, docker builds clean",
    "objective : faithful to the paper, then fast",
]


def starfield(n: int = 46) -> str:
    """Pseudo-random but fixed: the file must be byte-stable between runs."""
    rng = random.Random(21)
    out = []
    for _ in range(n):
        x, y = rng.uniform(8, W - 8), rng.uniform(8, H - 8)
        r = rng.choice([0.7, 0.9, 1.1, 1.4])
        op = rng.uniform(0.25, 0.85)
        dur = rng.uniform(2.4, 6.5)
        delay = rng.uniform(0, 5)
        out.append(
            f'    <circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="var(--star)" '
            f'opacity="{op:.2f}" class="twinkle" '
            f'style="animation-duration:{dur:.1f}s;animation-delay:{delay:.1f}s"/>'
        )
    return "\n".join(out)


def typing_css() -> str:
    """Four lines share one timeline; each owns a quarter of it."""
    share = 100.0 / len(LINES)          # 25% of the cycle per line
    hold_in, hold_out = share * 0.52, share * 0.84
    css = []
    for i, text in enumerate(LINES):
        w = len(text) * ADV
        delay = CYCLE * i / len(LINES)
        css.append(
            f"    .r{i} {{ animation: t{i} {CYCLE}s steps({len(text)}) infinite {delay:.2f}s }}\n"
            f"    @keyframes t{i} {{ 0%{{width:0}} {hold_in:.1f}%{{width:{w:.0f}px}} "
            f"{hold_out:.1f}%{{width:{w:.0f}px}} {share:.1f}%{{width:0}} 100%{{width:0}} }}\n"
            f"    .k{i} {{ animation: c{i} {CYCLE}s steps({len(text)}) infinite {delay:.2f}s,"
            f" blink 1.05s steps(1) infinite }}\n"
            f"    @keyframes c{i} {{ 0%{{x:{TX}px}} {hold_in:.1f}%{{x:{TX + w:.0f}px}} "
            f"{hold_out:.1f}%{{x:{TX + w:.0f}px}} {share:.1f}%{{x:{TX}px}} 100%{{x:{TX}px}} }}\n"
            f"    .l{i} {{ animation: show {CYCLE}s linear infinite {delay:.2f}s }}\n"
        )
    css.append(
        f"    @keyframes show {{ 0%{{opacity:1}} {share - 0.1:.1f}%{{opacity:1}} "
        f"{share:.1f}%{{opacity:0}} 100%{{opacity:0}} }}\n"
    )
    return "".join(css)


def banner() -> str:
    clips = "\n".join(
        f'    <clipPath id="c{i}"><rect class="r{i}" x="{TX}" y="{TY - 17}" width="0" height="24"/></clipPath>'
        for i in range(len(LINES))
    )
    lines = "\n".join(
        f'    <g class="line l{i}"><g clip-path="url(#c{i})">'
        f'<text x="{TX}" y="{TY}" class="mono typed">{t}</text></g></g>'
        for i, t in enumerate(LINES)
    )
    carets = "\n".join(
        f'    <g class="line l{i}"><rect class="caret k{i}" y="{TY - 14}" width="9" height="19" rx="1"/></g>'
        for i in range(len(LINES))
    )

    # HUD corner brackets, 18px inside each corner.
    br = 18
    corners = "\n".join([
        f'    <path d="M{br},{br + 26} L{br},{br} L{br + 26},{br}" class="hud"/>',
        f'    <path d="M{W - br - 26},{br} L{W - br},{br} L{W - br},{br + 26}" class="hud"/>',
        f'    <path d="M{br},{H - br - 26} L{br},{H - br} L{br + 26},{H - br}" class="hud"/>',
        f'    <path d="M{W - br - 26},{H - br} L{W - br},{H - br} L{W - br},{H - br - 26}" class="hud"/>',
    ])

    chips = []
    for i, (dot, label) in enumerate([("var(--ac)", "open to research collaboration"),
                                      ("var(--hi)", "Ho Chi Minh City, VN"),
                                      ("var(--ac)", "reproducible by default")]):
        x = 48 + i * 268
        chips.append(
            f'    <g class="rise" style="animation-delay:{1.0 + 0.12 * i:.2f}s">'
            f'<circle cx="{x + 4}" cy="{H - 42}" r="3.2" fill="{dot}"/>'
            f'<text x="{x + 16}" y="{H - 38}" class="chip">{label}</text></g>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Tuyen Ho Nguyen - NLP Research, Multimodal AI, ML Engineering">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="var(--sky0)"/>
      <stop offset="52%" stop-color="var(--sky1)"/>
      <stop offset="100%" stop-color="var(--sky0)"/>
    </linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="1" y2="0" gradientUnits="objectBoundingBox">
      <stop offset="0%" stop-color="var(--hi)"/>
      <stop offset="42%" stop-color="var(--ac)"/>
      <stop offset="52%" stop-color="var(--ink)"/>
      <stop offset="100%" stop-color="var(--ac)"/>
      <animate attributeName="x1" values="-1;0;-1" dur="7s" repeatCount="indefinite"/>
      <animate attributeName="x2" values="0;1;0" dur="7s" repeatCount="indefinite"/>
    </linearGradient>
    <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="var(--ac)" stop-opacity="0"/>
      <stop offset="45%" stop-color="var(--ac)" stop-opacity="1"/>
      <stop offset="100%" stop-color="var(--hi)" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="thrust" x1="1" y1="0" x2="0" y2="0">
      <stop offset="0%" stop-color="var(--ac)" stop-opacity=".85"/>
      <stop offset="100%" stop-color="var(--ac)" stop-opacity="0"/>
    </linearGradient>
    <radialGradient id="nebA">
      <stop offset="0%" stop-color="var(--ac)" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="var(--ac)" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="nebB">
      <stop offset="0%" stop-color="var(--hi)" stop-opacity="0.38"/>
      <stop offset="100%" stop-color="var(--hi)" stop-opacity="0"/>
    </radialGradient>
    <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">
      <path d="M36 0H0V36" fill="none" stroke="var(--ac)" stroke-opacity="0.08" stroke-width="1"/>
    </pattern>
    <clipPath id="card"><rect width="{W}" height="{H}" rx="16"/></clipPath>
{clips}
  </defs>

  <style>{PALETTE}
    .name {{ font: 800 48px 'Segoe UI',Ubuntu,-apple-system,Helvetica,sans-serif;
             letter-spacing: 2.6px; fill: url(#sheen) }}
    .role {{ font: 600 14px 'Segoe UI',Ubuntu,-apple-system,sans-serif;
             letter-spacing: 3.6px; fill: var(--dim); text-transform: uppercase }}
    .mono {{ font: 500 {MONO}px 'JetBrains Mono','Cascadia Code','Fira Code',Consolas,monospace }}
    .chip {{ font: 400 11.5px 'JetBrains Mono','Cascadia Code',Consolas,monospace; fill: var(--dim) }}
    .typed {{ fill: var(--ink) }}
    .prompt, .caret {{ fill: var(--ac) }}
    .hud {{ fill: none; stroke: var(--ac); stroke-opacity: .45; stroke-width: 2; stroke-linecap: round }}

    .line {{ opacity: 0 }}
{typing_css()}
    @keyframes blink {{ 0%,50% {{ opacity: 1 }} 51%,100% {{ opacity: .12 }} }}

    .twinkle {{ animation-name: tw; animation-iteration-count: infinite;
                animation-timing-function: ease-in-out }}
    @keyframes tw {{ 0%,100% {{ opacity: .15 }} 50% {{ opacity: .9 }} }}

    .rise {{ opacity: 0; animation: rise .9s cubic-bezier(.2,.8,.2,1) both }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(12px) }} to {{ opacity: 1; transform: none }} }}

    .pulse {{ animation: pulse 4.5s ease-in-out infinite }}
    @keyframes pulse {{ 0%,100% {{ opacity: .7 }} 50% {{ opacity: 1 }} }}

    .fly {{ animation: fly 11s linear infinite }}
    @keyframes fly {{ from {{ transform: translateX(-60px) }} to {{ transform: translateX({W + 70}px) }} }}
    .jet-body {{ animation: bob 2.6s ease-in-out infinite }}
    @keyframes bob {{ 0%,100% {{ transform: translateY(-3px) }} 50% {{ transform: translateY(3px) }} }}

    @media (prefers-reduced-motion: reduce) {{
      .line,.caret,.twinkle,.rise,.pulse,.fly,.jet-body,.name {{ animation: none !important }}
      .line,.rise {{ opacity: 1 }}
      .line.l0 {{ opacity: 1 }} .r0 {{ width: {len(LINES[0]) * ADV:.0f}px }}
      .line.l1,.line.l2,.line.l3 {{ opacity: 0 }}
    }}
  </style>

  <g clip-path="url(#card)">
    <rect width="{W}" height="{H}" fill="url(#bg)"/>
    <rect width="{W}" height="{H}" fill="url(#grid)"/>

    <ellipse cx="150" cy="70" rx="270" ry="180" fill="url(#nebA)">
      <animate attributeName="cx" values="150;360;150" dur="14s" repeatCount="indefinite"/>
      <animate attributeName="cy" values="70;150;70" dur="18s" repeatCount="indefinite"/>
    </ellipse>
    <ellipse cx="790" cy="230" rx="260" ry="170" fill="url(#nebB)">
      <animate attributeName="cx" values="790;600;790" dur="16s" repeatCount="indefinite"/>
      <animate attributeName="cy" values="230;130;230" dur="12s" repeatCount="indefinite"/>
    </ellipse>

{starfield()}
{corners}

    <g transform="translate(0,62)"><g class="fly">{JET}</g></g>

    <g class="rise">
      <text x="48" y="96" class="role">NLP Research &#183; Multimodal AI &#183; ML Engineering</text>
      <text x="46" y="158" class="name">TUYEN HO NGUYEN</text>
      <rect x="48" y="176" width="320" height="2" rx="1" fill="url(#rule)" class="pulse"/>
    </g>

    <text x="48" y="{TY}" class="mono prompt">&#8250;</text>
{lines}
{carets}

{chr(10).join(chips)}

    <rect x="0" y="{H - 3}" width="{W}" height="3" fill="url(#rule)" class="pulse"/>
  </g>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="16" fill="none" stroke="var(--bd)"/>
</svg>
"""


def divider() -> str:
    """A scanline with a bright round travelling along it."""
    return """<svg xmlns="http://www.w3.org/2000/svg" width="900" height="8" viewBox="0 0 900 8" role="presentation">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#36BCF7" stop-opacity="0"/>
      <stop offset="25%" stop-color="#36BCF7" stop-opacity="0.85"/>
      <stop offset="55%" stop-color="#7C4DFF" stop-opacity="0.85"/>
      <stop offset="100%" stop-color="#36BCF7" stop-opacity="0"/>
      <animate attributeName="x1" values="-0.6;0.6;-0.6" dur="9s" repeatCount="indefinite"/>
      <animate attributeName="x2" values="0.4;1.6;0.4" dur="9s" repeatCount="indefinite"/>
    </linearGradient>
    <radialGradient id="blip">
      <stop offset="0%" stop-color="#9FE8FF" stop-opacity="1"/>
      <stop offset="100%" stop-color="#36BCF7" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <style>
    .blip { animation: run 6s cubic-bezier(.45,0,.55,1) infinite }
    @keyframes run { 0% { transform: translateX(-30px) } 100% { transform: translateX(930px) } }
    @media (prefers-reduced-motion: reduce) { .blip { display: none } }
  </style>
  <rect y="3" width="900" height="2" rx="1" fill="url(#g)"/>
  <circle class="blip" cx="0" cy="4" r="7" fill="url(#blip)"/>
</svg>
"""


NAME = "Tuyen Ho Nguyen"

# The signature is an outline, not <text>. A font-based signature is laid out
# by whatever cursive face the reader happens to own, so its width is unknown
# here - and the reveal clip has to be an exact width or it truncates the name.
# These numbers come from measuring the real glyphs once, with the path:
#
#   Add-Type -AssemblyName PresentationCore,PresentationFramework,WindowsBase
#   $tf = New-Object System.Windows.Media.Typeface("Segoe Script")
#   $ft = New-Object System.Windows.Media.FormattedText("Tuyen Ho Nguyen",
#           [Globalization.CultureInfo]::InvariantCulture,
#           [Windows.FlowDirection]::LeftToRight, $tf, 42,
#           [Windows.Media.Brushes]::Black, 1.0)
#   $ft.BuildGeometry((New-Object Windows.Point(0,0))).GetOutlinedPathGeometry().ToString()
#
# then stripped of its "F1" fill-rule prefix and rounded to two decimals.
SIG_PATH = pathlib.Path(__file__).resolve().parent / "signature.path"
SIG_INK_W = 397.64          # measured width of the drawn glyphs
SIG_BASELINE = 45.73        # baseline offset inside the path's own space


def signoff() -> str:
    """Signature with a mortarboard that tips in a slow loop.

    No photograph and no webfont: the glyphs are outlines and the cap is drawn,
    so the file is self-contained and renders identically for every reader.
    """
    d = SIG_PATH.read_text(encoding="utf-8").strip()

    sx, baseline = 26, 82                       # where the signature sits
    dy = baseline - SIG_BASELINE
    pen = int(SIG_INK_W + 8)                    # clip clears the last stroke
    rule = int(SIG_INK_W)
    cap_dx = round(sx + SIG_INK_W + 20 - 422)   # cap is drawn from x=422; keep it clear of the ink
    w, h = 560, 150
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Signed, {NAME}">
  <defs>
    <linearGradient id="ink" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="var(--ac)"/>
      <stop offset="100%" stop-color="var(--hi)"/>
    </linearGradient>
    <clipPath id="write"><rect class="pen" x="{sx}" y="40" width="0" height="62"/></clipPath>
  </defs>
  <style>{PALETTE}
    .cap-line {{ font: 400 11px 'JetBrains Mono','Cascadia Code',Consolas,monospace;
                 fill: var(--dim); letter-spacing: 1.6px }}

    /* The pen sweeps left to right, revealing the signature as it goes. */
    .pen {{ animation: pen 7s cubic-bezier(.3,.7,.4,1) infinite }}
    @keyframes pen {{ 0% {{ width: 0 }} 34% {{ width: {pen}px }} 92% {{ width: {pen}px }} 100% {{ width: 0 }} }}

    /* Doff: lift, tip forward, hold, settle back. */
    .cap {{ transform-origin: 462px 70px; animation: doff 7s cubic-bezier(.34,1.3,.5,1) infinite }}
    @keyframes doff {{
      0%,30%   {{ transform: none }}
      42%      {{ transform: translate(-6px,-16px) rotate(-20deg) }}
      58%      {{ transform: translate(-6px,-16px) rotate(-20deg) }}
      74%,100% {{ transform: none }}
    }}
    .tassel {{ transform-origin: 484px 56px; animation: swing 2.1s ease-in-out infinite }}
    @keyframes swing {{ 0%,100% {{ transform: rotate(-9deg) }} 50% {{ transform: rotate(12deg) }} }}

    .underline {{ animation: ul 7s cubic-bezier(.3,.7,.4,1) infinite }}
    @keyframes ul {{ 0%,30% {{ width: 0 }} 46% {{ width: {rule}px }} 92% {{ width: {rule}px }} 100% {{ width: 0 }} }}

    @media (prefers-reduced-motion: reduce) {{
      .pen,.cap,.tassel,.underline {{ animation: none }}
      .pen {{ width: {pen}px }} .underline {{ width: {rule}px }}
    }}
  </style>

  <g clip-path="url(#write)">
    <g transform="translate({sx},{dy:.2f})"><path d="{d}" fill="url(#ink)"/></g>
  </g>
  <rect class="underline" x="{sx}" y="98" width="0" height="2" rx="1" fill="url(#ink)" opacity=".55"/>
  <text x="{sx}" y="126" class="cap-line">MSc-track &#183; NLP &amp; Multimodal AI</text>

  <g transform="translate({cap_dx},0)"><g class="cap">
    <!-- mortarboard: board, cap base, button, tassel -->
    <path d="M422,62 L462,48 L502,62 L462,76 Z" fill="var(--ac)"/>
    <path d="M440,68 L440,84 Q462,94 484,84 L484,68 L462,77 Z" fill="var(--hi)"/>
    <circle cx="462" cy="62" r="3" fill="var(--glass)" opacity=".9"/>
    <g class="tassel">
      <path d="M484,56 L484,80" stroke="var(--hi)" stroke-width="2" fill="none" stroke-linecap="round"/>
      <circle cx="484" cy="84" r="4.5" fill="var(--ac)"/>
    </g>
  </g></g>
</svg>
"""


# Glyphs are simple-icons paths (24x24 viewBox) - 13.21.0, plus gradio from
# 14.15.0 and powershell from 10.0.0, the last release that still shipped it.
# Vendored so the render needs no network and stays byte-stable.
ICONS = json.loads((pathlib.Path(__file__).resolve().parent / "tech_icons.json")
                   .read_text(encoding="utf-8"))

@dataclass(frozen=True)
class Tech:
    key: str            # output file name: assets/tech/<key>.svg
    label: str
    color: str          # brand colour of the icon chip
    what: str           # what it is used for - shown when the tile is opened
    repos: tuple = ()
    glyph: str = ""     # simple-icons slug; empty means draw the monogram
    mono: str = ""      # chip text when there is no glyph
    border: str = ""    # outline override for brands too dark to read on dark


# Ordered: languages, ML / DL, models, serving & infra.
TECH = [
    Tech("python", "Python", "3776AB", "Main language of every research repo: data pipelines, training, evaluation, statistics.",
         ("Prism", "CXR-VQA-custom", "EvidenceKD-MedVQA", "MultiLABSA"), "python"),
    Tech("go", "Go", "00ADD8", "Backend services in idiomatic Go with a clean cmd/internal layout.",
         ("Smart-Warehouse-Management", "work_reminder"), "go"),
    Tech("typescript", "TypeScript", "3178C6", "Typed React 18 frontend for the warehouse system.",
         ("Smart-Warehouse-Management",), "typescript"),
    Tech("javascript", "JavaScript", "F7DF1E", "Demo UIs that put research models in front of people.",
         ("KLTN-Token-Merging", "CXR-VQA-custom"), "javascript"),
    Tech("sql", "SQL", "4169E1", "Schemas, Alembic migrations and schema verification.",
         ("Book-Management",), "postgresql"),
    Tech("shell", "Shell", "4EAA25", "Training launchers, Docker entrypoints and CI steps.",
         (), "gnubash"),
    Tech("powershell", "PowerShell", "5391FE", "Windows-side tooling for local runs and asset generation.",
         (), "powershell"),
    Tech("git", "Git", "F05032", "Every repo versioned, with a 'decisions that must not be reverted' ledger where it matters.",
         ("s2it", "tree"), "git"),
    Tech("jupyter", "Jupyter", "F37626", "Kaggle-reproducible notebooks, EDA and labelling experiments.",
         ("Automatic-Labelling-Engine-with-LLM", "Customer_Segmentation"), "jupyter"),
    Tech("pytorch", "PyTorch", "EE4C2C", "Custom training loops: LoRA fine-tuning, distillation, detectors, soft-GIoU loss.",
         ("CXR-VQA-custom", "EvidenceKD-MedVQA"), "pytorch"),
    Tech("transformers", "Transformers", "FFD21E", "Loading and fine-tuning T5/mT5, BERT, XLM-R, MedGemma and Qwen.",
         ("KLTN-Token-Merging", "MultiLABSA", "CXR-VQA-custom"), "huggingface"),
    Tech("peft", "PEFT / LoRA", "FF6F00", "Parameter-efficient fine-tuning on a single GPU - one adapter, many stages.",
         ("CXR-VQA-custom", "s2it"), mono="LoRA"),
    Tech("trl", "TRL / GRPO", "8A2BE2", "GRPO with a rule-based reward and self-consistent voting for Tree-CoT-RT.",
         ("tree",), mono="TRL"),
    Tech("sklearn", "scikit-learn", "F7931E", "Classical ML baselines, clustering, regression and metrics.",
         ("Customer_Segmentation", "House-price-prediction", "text-classification"), "scikitlearn"),
    Tech("opencv", "OpenCV", "5C3EE8", "Image preprocessing and the computer-vision box counter.",
         ("Smart-Warehouse-Management", "Detect-CCCD"), "opencv"),
    Tech("pandas", "Pandas", "150458", "Wrangling review corpora - 1.95M Booking.com reviews in PRISM.",
         ("Prism", "Customer_Segmentation"), "pandas", border="E70488"),
    Tech("numpy", "NumPy", "013243", "Numerics behind permutation nulls, BH-FDR and drift estimation.",
         ("Prism",), "numpy", border="4DABCF"),
    Tech("medgemma", "MedGemma-4B", "4285F4", "Fine-tuned with LoRA under L_VQA + 0.5*L_bbox for explainable chest X-ray VQA.",
         ("CXR-VQA-custom",), "googlegemini"),
    Tech("qwen", "Qwen3-8B", "615CED", "UOS clause segmentation: one opinion, one target per unit.",
         ("Split_Sentence", "KLTN-Token-Merging"), mono="Qw"),
    Tech("t5", "mT5 / T5", "4285F4", "Generative quad extraction: GAS, the pipeline T5 stage and the generative teacher.",
         ("MultiLABSA", "KLTN-Token-Merging"), "google"),
    Tech("xlmr", "XLM-R / BERT", "0467DF", "Extractive teacher and aspect polarity classification.",
         ("MultiLABSA", "KLTN-Token-Merging"), "meta"),
    Tech("openclip", "OpenCLIP", "00B5AD", "Cross-modal confidence calibration from review images.",
         ("Prism",), mono="CLIP"),
    Tech("fasterrcnn", "Faster R-CNN", "E34F26", "Evidence detector that grounds medical VQA answers in boxes.",
         ("EvidenceKD-MedVQA",), mono="RCNN"),
    Tech("fastapi", "FastAPI", "009688", "REST backends for model demos and CRUD services.",
         ("KLTN-Token-Merging", "Detect-CCCD", "Book-Management"), "fastapi"),
    Tech("gin", "Gin", "008ECF", "Go HTTP API with JWT auth for lot tracking.",
         ("Smart-Warehouse-Management",), "gin"),
    Tech("gradio", "Gradio", "FF7C00", "Quick interactive UI for the dual-teacher ASQP model.",
         ("MultiLABSA",), "gradio"),
    Tech("react", "React", "61DAFB", "Demo and product frontends.",
         ("KLTN-Token-Merging", "CXR-VQA-custom", "Smart-Warehouse-Management"), "react"),
    Tech("vite", "Vite", "646CFF", "Frontend build and dev server.",
         ("Smart-Warehouse-Management",), "vite"),
    Tech("docker", "Docker", "2496ED", "One-command Docker Compose for research code that runs on a stranger's machine.",
         ("MultiLABSA", "Prism", "Detect-CCCD", "Book-Management"), "docker"),
    Tech("actions", "GH Actions", "2088FF", "CI for the OCR API, and the daily job that renders this profile's cards.",
         ("Detect-CCCD", "hotuyen21pt"), "githubactions"),
    Tech("ollama", "Ollama", "000000", "Running Qwen3 locally for segmentation and labelling.",
         ("Split_Sentence", "KLTN-Token-Merging"), "ollama", border="var(--dim)"),
    Tech("kaggle", "Kaggle GPU", "20BEFF", "Free-GPU training with notebooks anyone can re-run.",
         ("CXR-VQA-custom",), "kaggle"),
    Tech("sqlite", "SQLite", "003B57", "Zero-setup storage for small services and bots.",
         (), "sqlite", border="0F80CC"),
    Tech("pytest", "pytest", "0A9EDC", "180 tests in EvidenceKD-MedVQA, 95 across the ASQP baselines.",
         ("EvidenceKD-MedVQA", "s2it", "tree"), "pytest"),
]

GH = "https://github.com/hotuyen21pt/"

# TECH is ordered by group: (slug, title, size), in order.
GROUPS = [("languages", "LANGUAGES", 9), ("ml", "ML & DEEP LEARNING", 8),
          ("models", "MODELS", 6), ("infra", "SERVING & INFRA", 11)]
assert sum(n for _, _, n in GROUPS) == len(TECH)

ROW_W = 800                     # summary strip and panel width in the README
MINI_W, MINI_H, MINI_GAP = 68, 66, 5    # 11 minis fit 800px
CARD_COLS, CARD_GAP = 3, 13
CARD_W = (ROW_W - (CARD_COLS - 1) * CARD_GAP) // CARD_COLS
CARD_CHARS = 40                 # description wrap at 11.5px inside a card
CHIP_CHARS = 30                 # longest repo name a chip shows
REVEAL = 0.8                    # seconds for the panel to unroll

FONT = "'Segoe UI',Ubuntu,-apple-system,sans-serif"
MONO_FONT = "'JetBrains Mono','Cascadia Code',Consolas,monospace"
EASE = "cubic-bezier(.22,1,.36,1)"     # one easing curve everywhere keeps it calm

PALETTE_CSS = """
    svg { --panel:#F6F8FA; --card:#FFFFFF; --ink:#1F2328; --tx:#3D4752; --dim:#6E7781;
          --chip:#F3F6FA; --ac:#0B6FD4 }
    @media (prefers-color-scheme: dark) {
      svg { --panel:#161B26; --card:#111826; --ink:#F0F6FC; --tx:#C3CDD8; --dim:#8B949E;
            --chip:#1A2333; --ac:#36BCF7 }
    }
"""


def _luma(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def _accent(t: Tech) -> str:
    """Outline/accent colour: the brand, unless it is too dark to read on dark."""
    return t.border if t.border.startswith("var") else f"#{t.border or t.color}"


def _mark(t: Tech, x: float, y: float, size: float) -> str:
    """The brand glyph (or monogram) inside a chip of `size` at (x, y)."""
    ink = "#1F2328" if _luma(t.color) > 160 else "#FFFFFF"
    g = size * 0.6
    if t.glyph:
        o = (size - g) / 2
        return (f'<path transform="translate({x + o:.1f} {y + o:.1f}) scale({g / 24:.4f})" '
                f'fill="{ink}" d="{ICONS[t.glyph]}"/>')
    fs = size * (0.33 if len(t.mono) <= 3 else 0.28)
    return (f'<text x="{x + size / 2:.1f}" y="{y + size / 2 + fs * .36:.1f}" text-anchor="middle" '
            f'style="font:800 {fs:.1f}px {FONT}" fill="{ink}">{escape(t.mono)}</text>')


def groups():
    i = 0
    for slug, title, n in GROUPS:
        yield slug, title, TECH[i:i + n]
        i += n


def strip(title: str, techs: list) -> str:
    """The clickable summary: group title and a row of mini tiles."""
    head = 26
    h = head + MINI_H + 2
    out = [
        f'<text x="2" y="16" style="font:800 12px {MONO_FONT};letter-spacing:1.6px" fill="var(--ac)">{escape(title)}</text>',
        f'<text x="{ROW_W - 2}" y="16" text-anchor="end" style="font:600 10.5px {FONT}" fill="var(--dim)">'
        f'{len(techs)} tools · click to open</text>',
    ]
    for i, t in enumerate(techs):
        x, y = 1 + i * (MINI_W + MINI_GAP), head
        out.append(
            f'<g class="mi" style="animation-delay:{i * 0.04:.2f}s">'
            f'<rect x="{x + .75}" y="{y + .75}" width="{MINI_W - 1.5}" height="{MINI_H - 1.5}" rx="9" '
            f'fill="var(--panel)" stroke="{_accent(t)}" stroke-width="1.5"/>'
            f'<rect x="{x + (MINI_W - 30) / 2}" y="{y + 8}" width="30" height="30" rx="7" fill="#{t.color}"/>'
            + _mark(t, x + (MINI_W - 30) / 2, y + 8, 30) +
            f'<text x="{x + MINI_W / 2}" y="{y + 54}" text-anchor="middle" '
            f'style="font:600 {9.5 if len(t.label) <= 10 else 8.5}px {FONT}" fill="var(--ink)">{escape(t.label)}</text></g>'
        )
    body = "\n  ".join(out)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{ROW_W}" height="{h}" viewBox="0 0 {ROW_W} {h}" role="img" aria-label="{escape(title)}: {escape(', '.join(t.label for t in techs))}">
  <style>{PALETTE_CSS}
    .mi {{ animation: mi .45s {EASE} both }}
    @keyframes mi {{ from {{ opacity:0; transform: translateY(5px) }} to {{ opacity:1; transform:none }} }}
    @media (prefers-reduced-motion: reduce) {{ .mi {{ animation: none }} }}
  </style>
  {body}
</svg>
"""


def _card_body(t: Tech, title: str) -> tuple[list, float]:
    """Card contents relative to its own top-left, and the height they need."""
    acc, pad, w = _accent(t), 14, CARD_W
    tag = {"LANGUAGES": "LANGUAGE", "MODELS": "MODEL",
           "SERVING & INFRA": "INFRA"}.get(title, title.split(" ")[0])
    tag_w = len(tag) * 6.3 + 14
    out = [
        f'<rect x="{pad}" y="16" width="30" height="30" rx="7" fill="#{t.color}"/>',
        _mark(t, pad, 16, 30),
        f'<text x="{pad + 40}" y="29" style="font:700 15px {FONT}" fill="var(--ink)">{escape(t.label)}</text>',
        f'<rect x="{pad + 40}" y="35" width="{tag_w:.0f}" height="13" rx="6.5" fill="{acc}" fill-opacity=".15"/>',
        f'<text x="{pad + 47}" y="44.5" class="k" fill="{acc}">{escape(tag)}</text>',
        f'<circle class="pulse" cx="{w - pad - 4}" cy="22" r="3" fill="{acc}"/>',
        f'<line class="rule" x1="{pad}" y1="60" x2="{w - pad}" y2="60" stroke="{acc}" '
        f'stroke-opacity=".7" stroke-width="1.5" stroke-linecap="round"/>',
    ]
    y = 80
    lines = textwrap.wrap(t.what, CARD_CHARS)
    for i, line in enumerate(lines):
        # The caret rides in a tspan so the renderer places it after the real
        # glyph widths - estimating them put it on top of the last word.
        caret = (f'<tspan dx="3" fill="{acc}">▍<animate attributeName="fill-opacity" '
                 f'values="1;0" dur="1.1s" calcMode="discrete" repeatCount="indefinite"/></tspan>'
                 if i == len(lines) - 1 else "")
        out.append(f'<text x="{pad}" y="{y}" class="d">{escape(line)}{caret}</text>')
        y += 16
    if t.repos:
        y += 8
        out.append(f'<text x="{pad}" y="{y}" class="k" fill="var(--dim)">USED IN</text>')
        y += 8
        x = pad
        for r in t.repos:
            name = r if len(r) <= CHIP_CHARS else r[:CHIP_CHARS - 1] + "…"
            cw = len(name) * 5.75 + 24
            if x + cw > w - pad:
                x, y = pad, y + 25
            out.append(
                f'<rect x="{x}" y="{y}" width="{cw:.0f}" height="20" rx="10" fill="var(--chip)" '
                f'stroke="{acc}" stroke-opacity=".55"/>'
                f'<circle cx="{x + 10}" cy="{y + 10}" r="2.6" fill="{acc}"/>'
                f'<text x="{x + 17}" y="{y + 13.5}" class="c">{escape(name)}</text>'
            )
            x += cw + 6
        y += 20
    return out, y + 14


def panel(slug: str, title: str, techs: list) -> str:
    """The content that unrolls under a strip: one card per tool, in its colours."""
    bodies = [_card_body(t, title) for t in techs]
    rows = [bodies[i:i + CARD_COLS] for i in range(0, len(bodies), CARD_COLS)]
    row_h = [max(h for _, h in r) for r in rows]
    total = int(sum(row_h) + CARD_GAP * (len(rows) - 1) + 4)

    defs, cards = [], []
    y = 2
    for ri, row in enumerate(rows):
        for ci, (body, _) in enumerate(row):
            i = ri * CARD_COLS + ci
            t = techs[i]
            acc, h = _accent(t), row_h[ri]
            x = ci * (CARD_W + CARD_GAP)
            defs.append(
                f'<linearGradient id="rim-{t.key}" x1="0" y1="0" x2="1" y2="1">'
                f'<stop offset="0%" style="stop-color:{acc}"/>'
                f'<stop offset="50%" style="stop-color:{acc};stop-opacity:.25"/>'
                f'<stop offset="100%" style="stop-color:{acc}"/>'
                f'<animateTransform attributeName="gradientTransform" type="rotate" '
                f'from="0 .5 .5" to="360 .5 .5" dur="{6 + i % 3}s" repeatCount="indefinite"/></linearGradient>'
                f'<clipPath id="cl-{t.key}"><rect x="1" y="1" width="{CARD_W - 2}" height="{h - 2}" rx="12"/></clipPath>'
            )
            delay = 0.15 + REVEAL * 0.5 * (y / max(total, 1)) + ci * 0.07
            inner = "\n        ".join(body)
            cards.append(f"""    <g transform="translate({x},{y})"><g class="card" style="animation-delay:{delay:.2f}s">
      <rect x="1" y="1" width="{CARD_W - 2}" height="{h - 2}" rx="12" fill="var(--card)" stroke="url(#rim-{t.key})" stroke-width="2"/>
      <g clip-path="url(#cl-{t.key})">
        <rect width="{CARD_W}" height="4" fill="{acc}"/>
        <rect width="{CARD_W}" height="64" fill="{acc}" fill-opacity=".07"/>
        <g class="sheen" style="animation-delay:{1.2 + i * 0.35:.2f}s"><rect width="70" height="{h}" fill="url(#glare)" transform="skewX(-20)"/></g>
      </g>
        {inner}
    </g></g>""")
        y += row_h[ri] + CARD_GAP

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{ROW_W}" height="{total}" viewBox="0 0 {ROW_W} {total}" role="img" aria-label="{escape(title)} details">
  <defs>
    <linearGradient id="glare" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0"/>
      <stop offset="50%" stop-color="#FFFFFF" stop-opacity=".16"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="reveal"><rect class="unroll" width="{ROW_W}" height="{total}"/></clipPath>
    {"".join(defs)}
  </defs>
  <style>{PALETTE_CSS}
    .d {{ font: 400 11.5px {FONT}; fill: var(--tx) }}
    .k {{ font: 700 8.5px {MONO_FONT}; letter-spacing: 1.4px }}
    .c {{ font: 500 9.5px {MONO_FONT}; fill: var(--ink) }}

    /* Entrance: the panel unrolls like a drawer, cards rise in as it reaches them. */
    .unroll {{ animation: unroll {REVEAL}s {EASE} both }}
    @keyframes unroll {{ from {{ height: 0 }} to {{ height: {total}px }} }}
    .card {{ animation: card .6s {EASE} both }}
    @keyframes card {{ from {{ opacity:0; transform: translateY(-10px) }} to {{ opacity:1; transform:none }} }}
    .rule {{ stroke-dasharray: 240; stroke-dashoffset: 240; animation: draw .9s .5s {EASE} forwards }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0 }} }}

    /* Ambient, so the cards still move once the entrance has played. */
    .sheen {{ animation: sheen 4.5s ease-in-out infinite }}
    @keyframes sheen {{ 0% {{ transform: translateX(-120px) }} 45%,100% {{ transform: translateX({CARD_W + 140}px) }} }}
    .pulse {{ transform-box: fill-box; transform-origin: center; animation: pulse 2.4s ease-in-out infinite }}
    @keyframes pulse {{ 0%,100% {{ opacity:.35; transform: scale(1) }} 50% {{ opacity:1; transform: scale(1.4) }} }}

    @media (prefers-reduced-motion: reduce) {{
      .unroll,.card,.rule,.sheen,.pulse {{ animation: none !important; opacity: 1 }}
      .rule {{ stroke-dashoffset: 0 }} .sheen {{ display: none }}
    }}
  </style>
  <g clip-path="url(#reveal)">
{chr(10).join(cards)}
  </g>
</svg>
"""


def techstack_html() -> str:
    """The README block: one <details> per group.

    GitHub strips scripts and styles from READMEs, so <details> is the only
    click-to-open there is, and its content always appears right after its own
    summary. Making each group's strip the summary is what lets a click open
    one full-width panel under that row, instead of a narrow note squeezed
    into a table cell that pushes the grid around.

    GitHub also wraps every README image in a link to the raw file, which
    would make a click open the SVG; an image already inside an <a name> is
    left alone, and a name-only anchor does nothing on click, so the click
    reaches the <summary>.
    """
    out = []
    for slug, title, techs in groups():
        repos = list(dict.fromkeys(r for t in techs for r in t.repos))
        links = " · ".join(f'<a href="{GH}{r}">{r}</a>' for r in repos)
        out.append(
            f'<details>\n<summary><a name="stack-{slug}"><img src="assets/tech/strip-{slug}.svg" '
            f'width="{ROW_W}" alt="{escape(title.title())}: {escape(", ".join(t.label for t in techs))}" /></a></summary>\n'
            f'<a name="stack-{slug}-panel"><img src="assets/tech/panel-{slug}.svg" width="{ROW_W}" '
            f'alt="{escape(title.title())} - what each tool is used for" /></a>\n'
            + (f'<p><sub>↗ {links}</sub></p>\n' if links else "")
            + '</details>'
        )
    return "\n\n".join(out)


# ------------------------------------------------------------- dot portrait

# Colour grid sampled from a picture by scripts/sample_portrait.ps1.
PORTRAIT = json.loads((pathlib.Path(__file__).resolve().parent / "portrait.json")
                      .read_text(encoding="utf-8"))

DOT = 7.2               # grid pitch
CARD_X, CARD_Y = 30, 62
SPARK_COLORS = ["#36BCF7", "#7C4DFF", "#2EE6A6", "#FFFFFF"]


def _hsl_tweak(hex_: str, sat: float = 1.05, light: float = 1.08) -> str:
    """Push a sampled colour a little brighter and more saturated - dots on a
    dark panel read duller than the same pixels in a photo."""
    import colorsys
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, min(1, l * light), min(1, s * sat))
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _sparkle(x: float, y: float, s: float) -> str:
    """A four-point star centred on (x, y) with arm length s."""
    k = s * 0.28
    return (f"M{x:.1f},{y - s:.1f} Q{x + k:.1f},{y - k:.1f} {x + s:.1f},{y:.1f} "
            f"Q{x + k:.1f},{y + k:.1f} {x:.1f},{y + s:.1f} "
            f"Q{x - k:.1f},{y + k:.1f} {x - s:.1f},{y:.1f} "
            f"Q{x - k:.1f},{y - k:.1f} {x:.1f},{y - s:.1f}Z")


def portrait() -> str:
    """The picture redrawn as a dot matrix on a dark panel, under a mortarboard.

    Bright, colourless cells are the picture's background: they stay as faint
    dots so the subject stands out. Rows fade in top to bottom, then a scan
    band keeps sweeping the panel and sparkles twinkle around it.
    """
    cols, rows, cells = PORTRAIT["cols"], PORTRAIT["rows"], PORTRAIT["cells"]
    grid_w, grid_h = (cols - 1) * DOT, (rows - 1) * DOT
    card_w = grid_w + 56
    card_h = grid_h + 64
    gx = CARD_X + (card_w - grid_w) / 2
    gy = CARD_Y + 36
    W = int(card_w + 2 * CARD_X)
    cx = W / 2
    name_y = CARD_Y + card_h + 52
    H = int(name_y + 34)

    row_groups = []
    for r, line in enumerate(cells):
        dots = []
        for c, hx in enumerate(line):
            R, G, B = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
            luma = 0.299 * R + 0.587 * G + 0.114 * B
            sat = (max(R, G, B) - min(R, G, B)) / max(1, max(R, G, B))
            x, y = gx + c * DOT, gy + r * DOT
            if luma > 215 and sat < 0.14:           # background
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.5" fill="#C9D1D9" fill-opacity=".22"/>')
            elif luma < 40:                          # ink lines, pupils, nose
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="#8FA3BF"/>')
            else:
                # Halftone: brighter cells get bigger dots, which is what gives
                # a flat fill its shading.
                rad = 1.6 + 1.5 * min(1.0, luma / 200)
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.2f}" fill="{_hsl_tweak(hx)}"/>')
        row_groups.append(f'<g class="rw" style="animation-delay:{0.2 + r * 0.028:.3f}s">{"".join(dots)}</g>')

    rng = random.Random(7)
    sparks = []
    for i in range(16):
        # Keep sparkles in the margin band or sparse over the panel edge.
        x = rng.uniform(CARD_X + 8, CARD_X + card_w - 8)
        y = rng.uniform(CARD_Y + 8, CARD_Y + card_h - 8)
        s = rng.choice([3.5, 4.5, 5.5])
        col = SPARK_COLORS[i % len(SPARK_COLORS)]
        sparks.append(
            f'<path class="tw" d="{_sparkle(x, y, s)}" fill="{col}" '
            f'style="animation-duration:{rng.uniform(2.2, 4.8):.1f}s;animation-delay:{rng.uniform(0, 4):.1f}s"/>'
        )

    # Mortarboard straddling the panel's top edge, drawn around (cx, 0).
    cap = f"""<g transform="translate({cx:.1f},14)">
    <g class="cap">
      <path d="M-44,40 L-44,62 Q0,82 44,62 L44,40 Z" fill="#1A2233"/>
      <path d="M-44,62 Q0,82 44,62" fill="none" stroke="url(#capBand)" stroke-width="4" stroke-linecap="round"/>
      <path d="M-72,26 L0,0 L72,26 L0,52 Z" fill="#141C2B" stroke="#5B9BF8" stroke-width="3" stroke-linejoin="round"/>
      <circle cx="0" cy="26" r="3.2" fill="#5B9BF8"/>
      <g class="tassel">
        <path d="M0,26 L66,28 L66,58" fill="none" stroke="#2EE6A6" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="66" cy="62" r="5.5" fill="#2EE6A6"/>
      </g>
    </g>
  </g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Dot-matrix portrait of {NAME}">
  <defs>
    <linearGradient id="capBand" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#7C4DFF"/><stop offset="100%" stop-color="#C4A8FF"/>
    </linearGradient>
    <linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#36BCF7" stop-opacity="0"/>
      <stop offset="50%" stop-color="#36BCF7" stop-opacity=".16"/>
      <stop offset="100%" stop-color="#36BCF7" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="rimP" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#2F5A93"/>
      <stop offset="50%" stop-color="#7C4DFF" stop-opacity=".7"/>
      <stop offset="100%" stop-color="#2F5A93"/>
      <animateTransform attributeName="gradientTransform" type="rotate" from="0 .5 .5" to="360 .5 .5" dur="9s" repeatCount="indefinite"/>
    </linearGradient>
    <clipPath id="panel"><rect x="{CARD_X + 8}" y="{CARD_Y + 8}" width="{card_w - 16}" height="{card_h - 16}" rx="16"/></clipPath>
  </defs>
  <style>
    svg {{ --ink:#1F2328; --dim:#57606A }}
    @media (prefers-color-scheme: dark) {{ svg {{ --ink:#F0F6FC; --dim:#8B949E }} }}
    .rw {{ opacity:0; animation: rw .6s cubic-bezier(.22,1,.36,1) both }}
    @keyframes rw {{ from {{ opacity:0; transform: translateY(-3px) }} to {{ opacity:1; transform:none }} }}
    .scan {{ animation: scan 6s 2.2s cubic-bezier(.45,0,.55,1) infinite }}
    @keyframes scan {{ 0% {{ transform: translateY(-90px) }} 60%,100% {{ transform: translateY({card_h + 40}px) }} }}
    .tw {{ transform-box: fill-box; transform-origin: center; animation: tw 3s ease-in-out infinite }}
    @keyframes tw {{ 0%,100% {{ opacity:.15; transform: scale(.55) rotate(0deg) }} 50% {{ opacity:1; transform: scale(1) rotate(45deg) }} }}
    .cap {{ transform-box: fill-box; transform-origin: center; animation: bob 4.5s ease-in-out infinite }}
    @keyframes bob {{ 0%,100% {{ transform: none }} 50% {{ transform: translateY(-4px) rotate(-2deg) }} }}
    /* Pivot on the top-left of the tassel's box, which is the button it hangs from. */
    .tassel {{ transform-box: fill-box; transform-origin: 0 0; animation: swing 2.2s ease-in-out infinite }}
    @keyframes swing {{ 0%,100% {{ transform: rotate(-7deg) }} 50% {{ transform: rotate(9deg) }} }}
    .nm {{ font: 800 32px 'Segoe UI',Ubuntu,-apple-system,sans-serif; fill: var(--ink); letter-spacing: .3px }}
    .sb {{ font: 500 11px 'JetBrains Mono','Cascadia Code',Consolas,monospace; fill: var(--dim); letter-spacing: 2.4px }}
    .fade {{ animation: rw .8s 1.6s cubic-bezier(.22,1,.36,1) both }}
    @media (prefers-reduced-motion: reduce) {{
      .rw,.scan,.tw,.cap,.tassel,.fade {{ animation: none !important; opacity: 1 }} .scan {{ display: none }}
    }}
  </style>

  <rect x="{CARD_X}" y="{CARD_Y}" width="{card_w}" height="{card_h}" rx="22" fill="#0A0E15"/>
  <rect x="{CARD_X + 8}" y="{CARD_Y + 8}" width="{card_w - 16}" height="{card_h - 16}" rx="16" fill="#0D1117" stroke="url(#rimP)" stroke-width="2"/>
  <g clip-path="url(#panel)">
    {chr(10).join(row_groups)}
    <rect class="scan" x="{CARD_X}" y="{CARD_Y - 60}" width="{card_w}" height="70" fill="url(#scan)"/>
  </g>
  {chr(10).join(sparks)}
  {cap}

  <g class="fade">
    <text x="{cx:.1f}" y="{name_y}" text-anchor="middle" class="nm">{NAME}</text>
    <text x="{cx:.1f}" y="{name_y + 24}" text-anchor="middle" class="sb">NLP · MULTIMODAL AI · ML ENGINEERING</text>
  </g>
</svg>
"""


# ------------------------------------------------------------ project cards


@dataclass(frozen=True)
class Project:
    key: str            # output file: assets/projects/<key>.svg
    repo: str           # links the card; also shown in its footer
    title: str
    kicker: str         # what kind of work this is
    color: str
    mono: str           # chip monogram
    tagline: str
    metrics: tuple      # three (value, label) pairs
    what: str
    stack: tuple
    footer: str = ""    # footer override when one card stands for two repos


PROJECTS = [
    Project("prism", "Prism", "PRISM", "RESEARCH", "7C4DFF", "PR",
            "Temporal aspect-based sentiment analysis at scale",
            (("1.95M", "Booking.com reviews"), ("10,631", "hotels, 2022 → 2025"), ("23,995", "gold multimodal quads")),
            "Aspect-level sentiment drift with semi-supervised quad extraction, cross-modal "
            "confidence calibration from images, and reviewer-adjusted drift tested with "
            "permutation nulls + BH-FDR.",
            ("Python", "OpenCLIP", "Statistics", "Docker")),
    Project("kltn", "KLTN-Token-Merging", "KLTN · Token Merging", "UNDERGRADUATE THESIS", "F59E0B", "KL",
            "Vietnamese ABSA triplet extraction",
            (("2", "architectures"), ("GAS + UOS", "LLM extract & split"), ("FastAPI", "+ React demo UI")),
            "Joint (aspect, category, sentiment) extraction from Vietnamese hotel reviews: "
            "Joint ATE+APC against a T5 → BERT pipeline, GAS generative extraction and UOS "
            "clause splitting, plus the full LaTeX thesis.",
            ("T5", "BERT", "FastAPI", "React", "Ollama")),
    Project("cxr", "CXR-VQA-custom", "CXR-VQA", "PAPER REPRODUCTION", "0EA5E9", "CX",
            "Explainable chest X-ray VQA (arXiv:2511.00504)",
            (("4B", "MedGemma + LoRA"), ("60%", "released boxes wrong"), ("soft-GIoU", "differentiable bbox loss")),
            "MedGemma-4B-it fine-tuned under L_VQA + 0.5·L_bbox. A data audit found 60% of "
            "released QA pairs carried a mismatched ground-truth box; the published and the "
            "repaired data both ship behind a config switch.",
            ("MedGemma", "LoRA", "React UI", "Kaggle")),
    Project("evidencekd", "EvidenceKD-MedVQA", "EvidenceKD-MedVQA", "RESEARCH", "10B981", "EK",
            "Evidence-grounded medical VQA with a verifier",
            (("180", "tests passing"), ("3-stage", "decide, explain, verify"), ("torch-free", "core logic")),
            "A decision branch produces the answer, findings and scores; a generator only "
            "explains them under a citation constraint; a verifier checks every claim. "
            "Faster R-CNN evidence detector with knowledge distillation.",
            ("Faster R-CNN", "Distillation", "pytest")),
    Project("multilabsa", "MultiLABSA", "MultiLABSA", "RESEARCH", "EC4899", "ML",
            "Dual-teacher multilingual quad prediction",
            (("2", "teachers: mT5 + XLM-R"), ("4-tuple", "quads per opinion"), ("1 cmd", "Docker Compose")),
            "A generative mT5 teacher and an extractive XLM-R teacher merged by Confidence "
            "Fusion, with multi-view and disagreement modules. Gradio UI, CLI and a "
            "one-command Docker Compose.",
            ("mT5", "XLM-R", "Gradio", "Docker")),
    Project("s2it", "s2it", "S2IT · Tree-CoT-RT", "PAPER REPRODUCTIONS", "EF4444", "S2",
            "Two ASQP baselines, rebuilt faithfully",
            (("NAACL '25", "S2IT"), ("ACL '26", "Tree-CoT-RT"), ("95", "tests")),
            "S2IT: three-stage syntax-guided tuning on one LoRA adapter with dependency-graph "
            "supervision. Tree-CoT-RT: type-specific reasoning trees, tSFT, then GRPO with a "
            "rule-based reward and self-consistent voting.",
            ("GRPO", "Stanza", "LoRA"), footer="hotuyen21pt/s2it  ·  /tree"),
    Project("warehouse", "Smart-Warehouse-Management", "Smart Warehouse", "PRODUCT", "84CC16", "SW",
            "IoT lot tracking for multi-branch warehouses",
            (("Go + Gin", "JWT REST API"), ("React 18", "TypeScript + Vite"), ("CV", "box-counter service")),
            "Barcode and QR scanning track lot numbers, manufacturing and expiry dates per SKU "
            "and branch, with a computer-vision service that counts boxes. Docker Compose for "
            "the whole stack.",
            ("Go", "Gin", "React", "TypeScript", "Docker")),
    Project("cccd", "Detect-CCCD", "Detect-CCCD", "PRODUCT", "3B82F6", "ID",
            "Vietnamese ID card classifier as an OCR REST API",
            (("2", "card types"), ("OCR", "Vietnamese model"), ("CI", "GitHub Actions")),
            "Classifies an image as a citizen ID (CCCD) or a student card by running "
            "Vietnamese PaddleOCR and scoring keyword matches. FastAPI endpoint, "
            "drag-and-drop web UI, Dockerised.",
            ("PaddleOCR", "FastAPI", "Docker")),
]

PROJ_W = 400
PROJ_CHARS = 64         # description wrap at 11.5px across 364px
PROJ_LINES = max(len(textwrap.wrap(p.what, PROJ_CHARS)) for p in PROJECTS)
# Every card is the same height so the pairs line up in the README.
PROJ_H = 166 + PROJ_LINES * 16 + 84


def project_card(p: Project, n: int) -> str:
    acc, pad, w, h = f"#{p.color}", 18, PROJ_W, PROJ_H
    out = [
        f'<rect x="{pad}" y="20" width="36" height="36" rx="9" fill="{acc}"/>',
        f'<text x="{pad + 18}" y="42.5" text-anchor="middle" style="font:800 13px {FONT}" fill="#FFFFFF">{p.mono}</text>',
        f'<text x="{pad + 48}" y="30" style="font:700 8.5px {MONO_FONT};letter-spacing:1.6px" fill="{acc}">{escape(p.kicker)}</text>',
        f'<text x="{pad + 48}" y="50" style="font:700 17px {FONT}" fill="var(--ink)">{escape(p.title)}</text>',
        f'<circle class="pulse" cx="{w - pad - 4}" cy="26" r="3.5" fill="{acc}"/>',
        f'<text x="{pad}" y="78" style="font:600 11.5px {FONT}" fill="var(--dim)">{escape(p.tagline)}</text>',
    ]

    mw = (w - 2 * pad - 2 * 8) / 3
    for i, (val, label) in enumerate(p.metrics):
        x = pad + i * (mw + 8)
        out.append(
            f'<g class="pop" style="animation-delay:{0.35 + i * 0.1:.2f}s">'
            f'<rect x="{x:.1f}" y="92" width="{mw:.1f}" height="54" rx="9" fill="{acc}" fill-opacity=".09" '
            f'stroke="{acc}" stroke-opacity=".35"/>'
            f'<text x="{x + 12:.1f}" y="118" style="font:800 18px {FONT}" fill="{acc}">{escape(val)}</text>'
            f'<text x="{x + 12:.1f}" y="136" style="font:500 9.5px {FONT}" fill="var(--dim)">{escape(label)}</text></g>'
        )

    y = 172
    for line in textwrap.wrap(p.what, PROJ_CHARS):
        out.append(f'<text x="{pad}" y="{y}" style="font:400 11.5px {FONT}" fill="var(--tx)">{escape(line)}</text>')
        y += 16

    y = h - 76
    x = pad
    for s in p.stack:
        cw = len(s) * 5.75 + 20
        out.append(
            f'<rect x="{x:.1f}" y="{y}" width="{cw:.0f}" height="20" rx="10" fill="var(--chip)" '
            f'stroke="{acc}" stroke-opacity=".5"/>'
            f'<text x="{x + 10:.1f}" y="{y + 13.5}" style="font:500 9.5px {MONO_FONT}" fill="var(--ink)">{escape(s)}</text>'
        )
        x += cw + 6

    foot = p.footer or f"hotuyen21pt/{p.repo}"
    out += [
        f'<line x1="{pad}" y1="{h - 42}" x2="{w - pad}" y2="{h - 42}" stroke="var(--line)"/>',
        f'<text x="{pad}" y="{h - 20}" style="font:500 10px {MONO_FONT}" fill="var(--dim)">{escape(foot)}</text>',
        f'<g class="nudge"><text x="{w - pad}" y="{h - 20}" text-anchor="end" style="font:700 10.5px {FONT}" '
        f'fill="{acc}">View repo →</text></g>',
    ]
    body = "\n    ".join(out)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(p.title)}: {escape(p.tagline)}">
  <defs>
    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" style="stop-color:{acc}"/>
      <stop offset="50%" style="stop-color:{acc};stop-opacity:.2"/>
      <stop offset="100%" style="stop-color:{acc}"/>
      <animateTransform attributeName="gradientTransform" type="rotate" from="0 .5 .5" to="360 .5 .5" dur="{7 + n % 3}s" repeatCount="indefinite"/>
    </linearGradient>
    <linearGradient id="glare" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0"/>
      <stop offset="50%" stop-color="#FFFFFF" stop-opacity=".14"/>
      <stop offset="100%" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="clip"><rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="14"/></clipPath>
  </defs>
  <style>{PALETTE_CSS}
    svg {{ --line:#D8DEE4 }}
    @media (prefers-color-scheme: dark) {{ svg {{ --line:#253043 }} }}
    .card {{ animation: card .7s {n * 0.08:.2f}s {EASE} both }}
    @keyframes card {{ from {{ opacity:0; transform: translateY(10px) }} to {{ opacity:1; transform:none }} }}
    .pop {{ opacity:0; transform-box: fill-box; transform-origin: center; animation: pop .5s {EASE} both }}
    @keyframes pop {{ from {{ opacity:0; transform: scale(.85) }} to {{ opacity:1; transform:none }} }}
    .sheen {{ animation: sheen 5s {1.5 + n * 0.6:.1f}s ease-in-out infinite }}
    @keyframes sheen {{ 0% {{ transform: translateX(-140px) }} 40%,100% {{ transform: translateX({w + 160}px) }} }}
    .pulse {{ transform-box: fill-box; transform-origin: center; animation: pulse 2.4s ease-in-out infinite }}
    @keyframes pulse {{ 0%,100% {{ opacity:.35; transform: scale(1) }} 50% {{ opacity:1; transform: scale(1.4) }} }}
    .nudge {{ animation: nudge 2.4s ease-in-out infinite }}
    @keyframes nudge {{ 0%,100% {{ transform: none }} 50% {{ transform: translateX(3px) }} }}
    @media (prefers-reduced-motion: reduce) {{
      .card,.pop,.sheen,.pulse,.nudge {{ animation: none !important; opacity: 1 }} .sheen {{ display: none }}
    }}
  </style>
  <g class="card">
    <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="14" fill="var(--card)" stroke="url(#rim)" stroke-width="2"/>
    <g clip-path="url(#clip)">
      <rect width="{w}" height="5" fill="{acc}"/>
      <rect width="{w}" height="88" fill="{acc}" fill-opacity=".06"/>
      <g class="sheen"><rect width="90" height="{h}" fill="url(#glare)" transform="skewX(-20)"/></g>
    </g>
    {body}
  </g>
</svg>
"""


def projects_html() -> str:
    """Cards in pairs. Each image sits inside its own repo link, so GitHub does
    not also wrap it in a link to the raw SVG, and a click opens the repo."""
    cells = [
        f'<a href="{GH}{p.repo}"><img src="assets/projects/{p.key}.svg" width="49%" '
        f'alt="{escape(p.title)}: {escape(p.tagline)}" /></a>'
        for p in PROJECTS
    ]
    rows = ["&nbsp;".join(cells[i:i + 2]) for i in range(0, len(cells), 2)]
    return '<p align="center">\n' + "\n<br/><br/>\n".join(rows) + "\n</p>"


def patch_block(marker: str, html: str) -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"(<!--{marker}-->\n).*?(<!--/{marker}-->)", text, re.S)
    if not m:
        raise SystemExit(f"README.md has no <!--{marker}--> block")
    path.write_text(text[:m.end(1)] + html + "\n" + text[m.start(2):], encoding="utf-8")
    print(f"patched README.md {marker}")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    for name, svg in (("banner.svg", banner()),
                      ("divider.svg", divider()),
                      ("signoff.svg", signoff()),
                      ("portrait.svg", portrait())):
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(f"wrote assets/{name}")

    tech_dir = ASSETS / "tech"
    tech_dir.mkdir(exist_ok=True)
    for old in tech_dir.glob("*.svg"):
        old.unlink()
    for slug, title, techs in groups():
        (tech_dir / f"strip-{slug}.svg").write_text(strip(title, techs), encoding="utf-8")
        (tech_dir / f"panel-{slug}.svg").write_text(panel(slug, title, techs), encoding="utf-8")
    print(f"wrote {len(GROUPS)} strips and panels to assets/tech/")
    patch_block("techstack", techstack_html())

    proj_dir = ASSETS / "projects"
    proj_dir.mkdir(exist_ok=True)
    for old in proj_dir.glob("*.svg"):
        old.unlink()
    for n, pr in enumerate(PROJECTS):
        (proj_dir / f"{pr.key}.svg").write_text(project_card(pr, n), encoding="utf-8")
    print(f"wrote {len(PROJECTS)} project cards to assets/projects/")
    patch_block("projects", projects_html())


if __name__ == "__main__":
    main()
