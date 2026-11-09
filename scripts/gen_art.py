#!/usr/bin/env python3
"""Render the static profile artwork: banner, divider and sign-off.

Unlike gen_stats.py these carry no live data, so they are generated once and
committed rather than refreshed by the daily workflow. They live in a script
because the typing animation needs per-line character maths, and hand-editing
four clip widths and four caret positions every time a line changes is how
banners end up with the caret floating in empty space.

    python scripts/gen_art.py

Writes assets/banner.svg, assets/divider.svg, assets/signoff.svg, one tile per
technology under assets/tech/, and the tech-stack grid in README.md between
the <!--techstack--> markers.
Every file carries a light and a dark palette; GitHub renders whichever the
reader's theme asks for.
"""

from __future__ import annotations

import json
import pathlib
import random
import re
import textwrap
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

GH = "https://github.com/hotuyen21pt/"


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

TILE_W, TILE_H, ICON = 100, 74, 36
COLS = 6            # 6 x ~140px fits GitHub's README column with the summary marker
TILE_PX = 92        # rendered width in the README
NOTE_CHARS = 26    # hand-wrapped note width, see techstack_html()

TILE_CSS = """
    svg { --panel:#F6F8FA; --ink:#1F2328; --dim:#636C76 }
    @media (prefers-color-scheme: dark) {
      svg { --panel:#161B26; --ink:#E6EDF3; --dim:#8B949E }
    }
    .lb { font: 600 11px 'Segoe UI',Ubuntu,-apple-system,sans-serif; fill: var(--ink) }
    .mn { font: 800 12px 'Segoe UI',Ubuntu,-apple-system,sans-serif }
"""


def _luma(hex_: str) -> float:
    r, g, b = (int(hex_[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def tile(t: Tech) -> str:
    """One brand tile: icon chip, coloured outline, label."""
    stroke = t.border if t.border.startswith("var") else f"#{t.border or t.color}"
    ink = "#1F2328" if _luma(t.color) > 160 else "#FFFFFF"
    ix, iy = (TILE_W - ICON) / 2, 9
    if t.glyph:
        mark = (f'<path transform="translate({ix + 7} {iy + 7}) scale({22 / 24:.4f})" '
                f'fill="{ink}" d="{ICONS[t.glyph]}"/>')
    else:
        size = 12 if len(t.mono) <= 3 else 10.5
        mark = (f'<text x="{TILE_W / 2}" y="{iy + ICON / 2 + size * .36:.1f}" text-anchor="middle" '
                f'class="mn" style="font-size:{size}px" fill="{ink}">{t.mono}</text>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{TILE_W}" height="{TILE_H}" viewBox="0 0 {TILE_W} {TILE_H}" role="img" aria-label="{t.label}">
  <style>{TILE_CSS}  </style>
  <rect x=".75" y=".75" width="{TILE_W - 1.5}" height="{TILE_H - 1.5}" rx="9" fill="var(--panel)" stroke="{stroke}" stroke-width="1.5"/>
  <rect x="{ix}" y="{iy}" width="{ICON}" height="{ICON}" rx="8" fill="#{t.color}"/>
  {mark}
  <text x="{TILE_W / 2}" y="62" text-anchor="middle" class="lb">{t.label}</text>
</svg>
"""


def techstack_html() -> str:
    """The README grid: every tile is a <details>, so a click opens its notes.

    GitHub strips scripts and styles from READMEs; <details> is the only
    click-to-reveal it keeps, and putting one per table cell is what lets each
    icon open on its own. GitHub also wraps every README image in a link to
    the file, which would make a click open the SVG instead of the tile; an
    image already inside an <a name> is left alone, and a name-only anchor
    does nothing on click, so the click reaches the <summary>.
    """
    # GitHub lays README tables out at max-content width, so an opened note
    # would stretch its column to one long line. Breaking it by hand keeps
    # the column close to the tile's width.
    cells = []
    for t in TECH:
        notes = "<br/>".join(textwrap.wrap(t.what, NOTE_CHARS))
        if t.repos:
            notes += "<br/><br/>" + "<br/>".join(
                f'📁 <a href="{GH}{r}">{r}</a>' for r in t.repos)
        cells.append(
            f'<td align="center" valign="top"><details><summary>'
            f'<a name="tech-{t.key}"><img src="assets/tech/{t.key}.svg" width="{TILE_PX}" alt="{t.label}" /></a>'
            f'</summary><sub>{notes}</sub></details></td>'
        )
    rows = ["<tr>\n" + "\n".join(cells[i:i + COLS]) + "\n</tr>"
            for i in range(0, len(cells), COLS)]
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def patch_readme() -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(<!--techstack-->\n).*?(<!--/techstack-->)", text, re.S)
    if not m:
        raise SystemExit("README.md has no <!--techstack--> block")
    text = text[:m.end(1)] + techstack_html() + "\n" + text[m.start(2):]
    path.write_text(text, encoding="utf-8")
    print("patched README.md tech stack")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    for name, svg in (("banner.svg", banner()),
                      ("divider.svg", divider()),
                      ("signoff.svg", signoff())):
        (ASSETS / name).write_text(svg, encoding="utf-8")
        print(f"wrote assets/{name}")

    tech_dir = ASSETS / "tech"
    tech_dir.mkdir(exist_ok=True)
    for old in tech_dir.glob("*.svg"):
        old.unlink()
    for t in TECH:
        (tech_dir / f"{t.key}.svg").write_text(tile(t), encoding="utf-8")
    print(f"wrote {len(TECH)} tiles to assets/tech/")
    patch_readme()


if __name__ == "__main__":
    main()
