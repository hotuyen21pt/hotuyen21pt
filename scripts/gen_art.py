#!/usr/bin/env python3
"""Render the static profile artwork: header, section titles, cards and sign-off.

Unlike gen_stats.py these carry no live data, so they are generated once and
committed rather than refreshed by the daily workflow. They live in a script
because the typing animation needs per-line character maths, and hand-editing
four clip widths and four caret positions every time a line changes is how
banners end up with the caret floating in empty space.

    python scripts/gen_art.py

Writes, under assets/: banner, portrait, contact pills, section titles, the
focus cards, the tech-stack strips and panels, the project cards and the
sign-off; and patches the <!--techstack--> and <!--projects--> blocks in
README.md. The live cards (stats, languages, contributions, track record)
come from gen_stats.py instead.
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
    """A scanline with a bright round travelling along it - the break between
    sections. Section titles are images, not ## headings, so it no longer
    doubles up with GitHub's heading underline."""
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
LOOP = 8           # seconds per draw-hold-fade cycle of the portrait
SPARK_COLORS = ["#36BCF7", "#7C4DFF", "#2EE6A6", "var(--spk)"]


# The portrait is drawn in one blue ramp rather than the picture's own colours,
# so it reads as a rendering of the avatar, not a copy of it. Tones are bucketed
# into LEVELS classes whose colours come from CSS, so the same dots can follow
# the reader's theme: on dark the prominent tones are the light blues, on light
# they are the deep ones - visual weight lands in the same places either way.
LEVELS = 8
RAMP_DARK = ["#1E3A8A", "#1D4ED8", "#3B82F6", "#60A5FA", "#BAE6FD"]
RAMP_LIGHT = ["#BFDBFE", "#93C5FD", "#3B82F6", "#1D4ED8", "#1E3A8A"]


def _ramp(stops: list, t: float) -> str:
    t = max(0.0, min(1.0, t)) * (len(stops) - 1)
    i = min(int(t), len(stops) - 2)
    f = t - i
    a, b = stops[i], stops[i + 1]
    mix = (round(int(a[k:k + 2], 16) * (1 - f) + int(b[k:k + 2], 16) * f) for k in (1, 3, 5))
    return "#" + "".join(f"{v:02X}" for v in mix)


def _level_css(stops: list) -> str:
    return " ".join(f"--q{i}:{_ramp(stops, i / (LEVELS - 1))};" for i in range(LEVELS))


def _luma_sat(hx: str) -> tuple[float, float]:
    R, G, B = (int(hx[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * R + 0.587 * G + 0.114 * B,
            (max(R, G, B) - min(R, G, B)) / max(1, max(R, G, B)))


def _is_background(luma: float, sat: float) -> bool:
    return luma > 215 and sat < 0.14


def _sparkle(x: float, y: float, s: float) -> str:
    """A four-point star centred on (x, y) with arm length s."""
    k = s * 0.28
    return (f"M{x:.1f},{y - s:.1f} Q{x + k:.1f},{y - k:.1f} {x + s:.1f},{y:.1f} "
            f"Q{x + k:.1f},{y + k:.1f} {x:.1f},{y + s:.1f} "
            f"Q{x - k:.1f},{y + k:.1f} {x - s:.1f},{y:.1f} "
            f"Q{x - k:.1f},{y - k:.1f} {x:.1f},{y - s:.1f}Z")


def portrait() -> str:
    """The picture redrawn as a dot matrix on a panel, under a mortarboard.

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
    H = int(CARD_Y + card_h + 8)

    # Stretch the ramp over the subject's own tonal range (5th-95th
    # percentile), otherwise a mostly mid-tone picture lands on one blue.
    subject = sorted(l for line in cells for l, s in map(_luma_sat, line)
                     if not _is_background(l, s) and l >= 40)
    lo = subject[len(subject) // 20]
    hi = subject[-len(subject) // 20 - 1]

    row_groups = []
    for r, line in enumerate(cells):
        dots = []
        for c, hx in enumerate(line):
            luma, sat = _luma_sat(hx)
            x, y = gx + c * DOT, gy + r * DOT
            if _is_background(luma, sat):
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.5" class="bg"/>')
            elif luma < 40:                          # ink lines, pupils, nose
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" class="ink"/>')
            else:
                # Halftone: brighter cells get bigger and lighter dots, which
                # is what gives a flat fill its shading.
                t = (luma - lo) / max(1, hi - lo)
                rad = 1.5 + 1.4 * max(0.0, min(1.0, t))
                q = round(max(0.0, min(1.0, t)) * (LEVELS - 1))
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.2f}" class="q{q}"/>')
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
      <path d="M-44,40 L-44,62 Q0,82 44,62 L44,40 Z" fill="var(--capb)"/>
      <path d="M-44,62 Q0,82 44,62" fill="none" stroke="url(#capBand)" stroke-width="4" stroke-linecap="round"/>
      <path d="M-72,26 L0,0 L72,26 L0,52 Z" fill="var(--capf)" stroke="#5B9BF8" stroke-width="3" stroke-linejoin="round"/>
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
    svg {{ --frame:#E6EDF6; --panel:#FFFFFF; --capf:#FFFFFF; --capb:#E3EAF5; --spk:#64748B;
           --ink:#0F1E3D; --bgd:#1D4ED8; --bgo:.10; {_level_css(RAMP_LIGHT)} }}
    @media (prefers-color-scheme: dark) {{
      svg {{ --frame:#0A0E15; --panel:#0D1117; --capf:#141C2B; --capb:#1A2233; --spk:#FFFFFF;
             --ink:#E0F2FE; --bgd:#93C5FD; --bgo:.14; {_level_css(RAMP_DARK)} }}
    }}
    .bg  {{ fill: var(--bgd); fill-opacity: var(--bgo) }}
    .ink {{ fill: var(--ink) }}
    {" ".join(f".q{i} {{ fill: var(--q{i}) }}" for i in range(LEVELS))}
    /* One {LOOP}s loop: rows draw in top to bottom behind the scan band, hold,
       fade out in the same order, and the picture redraws. Each row keeps
       its delay on every pass, so the wave shape survives the repeat. */
    .rw {{ opacity:0; animation: rw {LOOP}s ease-out infinite both }}
    @keyframes rw {{
      0%      {{ opacity:0; transform: translateY(-3px) }}
      7%      {{ opacity:1; transform: none }}
      80%     {{ opacity:1; transform: none }}
      90%,100% {{ opacity:0; transform: none }}
    }}
    .scan {{ animation: scan {LOOP}s cubic-bezier(.45,0,.55,1) infinite }}
    @keyframes scan {{ 0% {{ transform: translateY(-90px) }} 26%,100% {{ transform: translateY({card_h + 40}px) }} }}
    .tw {{ transform-box: fill-box; transform-origin: center; animation: tw 3s ease-in-out infinite }}
    @keyframes tw {{ 0%,100% {{ opacity:.15; transform: scale(.55) rotate(0deg) }} 50% {{ opacity:1; transform: scale(1) rotate(45deg) }} }}
    .cap {{ transform-box: fill-box; transform-origin: center; animation: bob 4.5s ease-in-out infinite }}
    @keyframes bob {{ 0%,100% {{ transform: none }} 50% {{ transform: translateY(-4px) rotate(-2deg) }} }}
    /* Pivot on the top-left of the tassel's box, which is the button it hangs from. */
    .tassel {{ transform-box: fill-box; transform-origin: 0 0; animation: swing 2.2s ease-in-out infinite }}
    @keyframes swing {{ 0%,100% {{ transform: rotate(-7deg) }} 50% {{ transform: rotate(9deg) }} }}
    @media (prefers-reduced-motion: reduce) {{
      .rw,.scan,.tw,.cap,.tassel {{ animation: none !important; opacity: 1 }} .scan {{ display: none }}
    }}
  </style>

  <rect x="{CARD_X}" y="{CARD_Y}" width="{card_w}" height="{card_h}" rx="22" fill="var(--frame)"/>
  <rect x="{CARD_X + 8}" y="{CARD_Y + 8}" width="{card_w - 16}" height="{card_h - 16}" rx="16" fill="var(--panel)" stroke="url(#rimP)" stroke-width="2"/>
  <g clip-path="url(#panel)">
    {chr(10).join(row_groups)}
    <rect class="scan" x="{CARD_X}" y="{CARD_Y - 60}" width="{card_w}" height="70" fill="url(#scan)"/>
  </g>
  {chr(10).join(sparks)}
  {cap}
</svg>
"""


# -------------------------------------------- contact, section titles, focus

# Shared by the pieces below: the same tokens as the stats cards, so headers,
# cards and telemetry read as one family in either theme.
UI_CSS = """
    svg { --bg:#FFFFFF; --panel:#F6F8FA; --bd:#D8DEE4; --ink:#1F2328; --tx:#3D4752; --mu:#636C76;
          --ac:#0B6FD4; --hi:#6A3DE8 }
    @media (prefers-color-scheme: dark) {
      svg { --bg:#0D1117; --panel:#111823; --bd:#1E3A52; --ink:#F0F6FC; --tx:#C3CDD8; --mu:#8B949E;
            --ac:#36BCF7; --hi:#9D7BFF }
    }
"""

CONTACTS = [
    # (file, glyph, label, link) - the link is used by the README, not the SVG
    ("github", "github", "@hotuyen21pt", "https://github.com/hotuyen21pt?tab=repositories"),
    ("email", "gmail", "tuyennh2102@gmail.com", "mailto:tuyennh2102@gmail.com"),
]


def contact_pill(glyph: str, label: str) -> str:
    """A rounded pill: accent icon disc and the handle, in the header's palette."""
    h = 36
    w = int(len(label) * 7.4 + 64)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(label)}">
  <defs>
    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" style="stop-color:var(--ac)"/><stop offset="100%" style="stop-color:var(--hi)"/>
    </linearGradient>
    <clipPath id="c"><rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{h / 2 - 1}"/></clipPath>
  </defs>
  <style>{UI_CSS}
    .sheen {{ animation: sheen 6s 1s ease-in-out infinite }}
    @keyframes sheen {{ 0% {{ transform: translateX(-60px) }} 35%,100% {{ transform: translateX({w + 60}px) }} }}
    @media (prefers-reduced-motion: reduce) {{ .sheen {{ display: none }} }}
  </style>
  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{h / 2 - 1}" fill="var(--panel)" stroke="url(#rim)" stroke-width="1.5"/>
  <g clip-path="url(#c)"><g class="sheen"><rect width="40" height="{h}" fill="var(--ac)" fill-opacity=".10" transform="skewX(-20)"/></g></g>
  <circle cx="19" cy="18" r="12" fill="url(#rim)"/>
  <path transform="translate(12 11) scale({14 / 24:.4f})" fill="#FFFFFF" d="{ICONS[glyph]}"/>
  <text x="40" y="22.5" style="font:600 12px {MONO_FONT}" fill="var(--ink)">{escape(label)}</text>
</svg>
"""


SECTIONS = [
    # (file, title, hint on the right)
    ("about", "About me", "paper → tested code → docker image"),
    ("stack", "Technology arsenal", "click a row to open it"),
    ("work", "Featured work", "click a card to open the repo"),
    ("telemetry", "Telemetry", "rendered daily from the GitHub API"),
]
SECTION_W = 830
DECODE_STEPS, DECODE_STEP, DECODE_LOOP = 8, 0.09, 9   # frames, seconds each, seconds per loop


def section_title(n: int, title: str, hint: str) -> str:
    """Numbered section title. It replaces a markdown ## heading so GitHub draws
    no underline of its own; the travelling-light divider above it is the
    only break between sections."""
    w, h = SECTION_W, 56
    # Decode effect: for the first DECODE_STEPS frames of every DECODE_LOOP
    # seconds the title shows scrambled glyphs, then resolves. Each frame is
    # its own <text>, visible only inside its slice of the loop.
    rng = random.Random(n * 97)
    pool = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#%&*/<>"
    frames, kf = [], []
    for i in range(DECODE_STEPS):
        # Characters lock in left to right as the frames advance.
        locked = int(len(title) * i / DECODE_STEPS)
        txt = title[:locked] + "".join(c if c == " " else rng.choice(pool) for c in title[locked:])
        a, b = 100 * i * DECODE_STEP / DECODE_LOOP, 100 * (i + 1) * DECODE_STEP / DECODE_LOOP
        kf.append(f"@keyframes f{i} {{ 0%,{a:.2f}% {{ opacity:0 }} {a + .01:.2f}%,{b:.2f}% {{ opacity:1 }} "
                  f"{b + .01:.2f}%,100% {{ opacity:0 }} }}")
        frames.append(f'<text x="0" y="46" class="tt fr" style="animation-name:f{i}">{escape(txt)}</text>')
    done = 100 * DECODE_STEPS * DECODE_STEP / DECODE_LOOP
    kf.append(f"@keyframes fin {{ 0%,{done:.2f}% {{ opacity:0 }} {done + .01:.2f}%,100% {{ opacity:1 }} }}")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">
  <style>{UI_CSS}
    .no {{ font: 700 12px {MONO_FONT}; fill: var(--ac); letter-spacing: 1.5px }}
    .tt {{ font: 800 25px {FONT}; fill: var(--ink) }}
    .fr {{ opacity:0; fill: var(--ac); animation-duration: {DECODE_LOOP}s; animation-iteration-count: infinite; animation-timing-function: linear }}
    .fin {{ animation: fin {DECODE_LOOP}s linear infinite }}
    .hn {{ font: 500 10.5px {MONO_FONT}; fill: var(--mu); letter-spacing: .4px }}
    .in {{ animation: in .6s {EASE} both }}
    @keyframes in {{ from {{ opacity:0; transform: translateX(-8px) }} to {{ opacity:1; transform:none }} }}
    {chr(10).join("    " + k for k in kf)}
    @media (prefers-reduced-motion: reduce) {{ .in,.fin {{ animation: none }} .fr {{ display: none }} }}
  </style>
  <g class="in">
    <text x="0" y="17" class="no">{n:02d} / {len(SECTIONS):02d}</text>
    {chr(10).join("    " + f for f in frames)}
    <text x="0" y="46" class="tt fin">{escape(title)}</text>
  </g>
  <text x="{w}" y="46" text-anchor="end" class="hn">{escape(hint)}</text>
</svg>
"""


FOCUS = [
    ("Aspect Sentiment Quad Prediction",
     "Implicit aspects and opinions, syntax-aware supervision, reasoning-tree chain of thought."),
    ("Multilingual & Vietnamese NLP",
     "Cross-lingual transfer for low-resource ABSA, clause-level opinion units."),
    ("Multimodal Medical AI",
     "Grounded answers with bounding-box evidence, hallucination-resistant generation."),
    ("Evaluation that means something",
     "Data audits before benchmarks, permutation tests, documented deviations."),
]


def focus_cards() -> str:
    """The four research interests as a 2x2 grid of small cards."""
    w, gap, ch = 830, 14, 92
    cw = (w - gap) / 2
    h = 2 * ch + gap
    cards = []
    for i, (title, what) in enumerate(FOCUS):
        x, y = (i % 2) * (cw + gap), (i // 2) * (ch + gap)
        acc = "var(--ac)" if i in (0, 3) else "var(--hi)"
        lines = textwrap.wrap(what, 58)
        body = "".join(f'<text x="{x + 22:.1f}" y="{y + 60 + j * 16}" class="d">{escape(l)}</text>'
                       for j, l in enumerate(lines[:2]))
        cards.append(
            f'  <g class="pop" style="animation-delay:{0.1 + i * 0.1:.2f}s">'
            f'<rect x="{x + .75:.1f}" y="{y + .75}" width="{cw - 1.5:.1f}" height="{ch - 1.5}" rx="12" '
            f'fill="var(--panel)" stroke="var(--bd)"/>'
            f'<rect x="{x + .75:.1f}" y="{y + 16}" width="3" height="{ch - 32}" rx="1.5" fill="{acc}"/>'
            f'<text x="{x + 22:.1f}" y="{y + 24}" class="k" fill="{acc}">FOCUS {i + 1:02d}</text>'
            f'<text x="{x + 22:.1f}" y="{y + 42}" class="t">{escape(title)}</text>{body}</g>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Research focus: {escape('; '.join(f[0] for f in FOCUS))}">
  <style>{UI_CSS}
    .k {{ font: 700 9px {MONO_FONT}; letter-spacing: 1.6px }}
    .t {{ font: 700 15px {FONT}; fill: var(--ink) }}
    .d {{ font: 400 12px {FONT}; fill: var(--tx) }}
    .pop {{ opacity:0; animation: pop .55s {EASE} both }}
    @keyframes pop {{ from {{ opacity:0; transform: translateY(6px) }} to {{ opacity:1; transform:none }} }}
    @media (prefers-reduced-motion: reduce) {{ .pop {{ animation: none; opacity: 1 }} }}
  </style>
{chr(10).join(cards)}
</svg>
"""


# ------------------------------------------------------------ live ASQP demo

# Illustrative sentences, not dataset rows: one English, one Vietnamese, one
# with implicit aspects (None), the three cases the research is about.
ASQP_SENTENCES = [
    ("The room was spotless but the breakfast was overpriced.",
     [("room", "spotless", "ROOMS#CLEANLINESS", "POS"),
      ("breakfast", "overpriced", "FOOD#PRICES", "NEG")]),
    ("Nhân viên lễ tân rất nhiệt tình, phòng thì hơi nhỏ.",
     [("Nhân viên lễ tân", "rất nhiệt tình", "SERVICE#GENERAL", "POS"),
      ("phòng", "hơi nhỏ", "ROOMS#DESIGN", "NEG")]),
    ("Honestly worth every penny, would stay again.",
     [(None, "worth every penny", "HOTEL#PRICES", "POS"),
      (None, "would stay again", "HOTEL#GENERAL", "POS")]),
]
ASQP_SLOT = 7.0         # seconds each sentence is on screen
ASQP_CW = 11.0          # forced advance per character (textLength), so spans line up
SENT_COLORS = {"POS": "#3FB950", "NEG": "#F85149"}


def _pct(sec: float) -> float:
    """Seconds into a slot -> percent of the whole loop."""
    return 100 * sec / (ASQP_SLOT * len(ASQP_SENTENCES))


def asqp_demo() -> str:
    """A review types itself out, aspects and opinions light up, and the quads
    assemble underneath - the research shown rather than described.

    Every sentence runs on the same keyframes over the full loop, offset by
    its slot, so the loop needs one set of keyframes per *kind* of element.
    The text is laid out with textLength, which pins each character to
    ASQP_CW whatever monospace font the reader has, so the highlight boxes
    computed here land on the right words.
    """
    import unicodedata
    w, x0, ty = 830, 56, 96
    loop = ASQP_SLOT * len(ASQP_SENTENCES)
    p = _pct

    # Within a slot: type 0-2.4s, highlights from 2.6s, quads from 3.4s,
    # hold, fade from 6.3s.
    css = [
        f"@keyframes grp {{ 0% {{ opacity:0 }} {p(.15):.2f}% {{ opacity:1 }} {p(6.3):.2f}% {{ opacity:1 }} "
        f"{p(6.8):.2f}%,100% {{ opacity:0 }} }}",
        ".grp { opacity:0; animation: grp %.1fs linear infinite both }" % loop,
        f"@keyframes hl {{ 0%,{p(2.6):.2f}% {{ opacity:0; transform: scaleX(0) }} "
        f"{p(3.0):.2f}%,100% {{ opacity:1; transform: scaleX(1) }} }}",
        f"@keyframes hl2 {{ 0%,{p(3.0):.2f}% {{ opacity:0; transform: scaleX(0) }} "
        f"{p(3.4):.2f}%,100% {{ opacity:1; transform: scaleX(1) }} }}",
        f"@keyframes tu {{ 0%,{p(3.4):.2f}% {{ opacity:0; transform: translateX(-8px) }} "
        f"{p(3.9):.2f}%,100% {{ opacity:1; transform: none }} }}",
        f"@keyframes tu2 {{ 0%,{p(4.1):.2f}% {{ opacity:0; transform: translateX(-8px) }} "
        f"{p(4.6):.2f}%,100% {{ opacity:1; transform: none }} }}",
        ".hl,.hl2 { transform-box: fill-box; transform-origin: left center }",
    ]
    for name in ("hl", "hl2", "tu", "tu2"):
        css.append(f".{name} {{ opacity:0; animation: {name} {loop:.1f}s cubic-bezier(.22,1,.36,1) infinite both }}")

    groups, defs = [], []
    for k, (sentence, quads) in enumerate(ASQP_SENTENCES):
        sentence = unicodedata.normalize("NFC", sentence)
        n = len(sentence)
        tw = n * ASQP_CW
        delay = k * ASQP_SLOT
        # Typing: a clip that widens one character at a time, and a caret on it.
        css.append(f"@keyframes typ{k} {{ 0% {{ width:0; animation-timing-function: steps({n}, end) }} "
                   f"{p(2.4):.2f}%,100% {{ width:{tw:.0f}px }} }}")
        css.append(f"@keyframes car{k} {{ 0% {{ transform:none; animation-timing-function: steps({n}, end) }} "
                   f"{p(2.4):.2f}%,100% {{ transform: translateX({tw:.0f}px) }} }}")
        defs.append(f'<clipPath id="ty{k}"><rect x="{x0}" y="{ty - 22}" height="34" width="0" '
                    f'style="animation: typ{k} {loop:.1f}s {delay:.1f}s infinite both"/></clipPath>')

        marks, tuples = [], []
        for qi, (asp, opi, cat, pol) in enumerate(quads):
            cls = "hl" if qi == 0 else "hl2"
            tcls = "tu" if qi == 0 else "tu2"
            st = f'style="animation-delay:{delay:.1f}s"'
            for span, kind in ((asp, "a"), (opi, "o")):
                if not span:
                    continue
                s = sentence.find(unicodedata.normalize("NFC", span))
                assert s >= 0, (span, sentence)
                x, wd = x0 + s * ASQP_CW, len(span) * ASQP_CW
                if kind == "a":
                    marks.append(
                        f'<g class="{cls}" {st}><rect x="{x - 2:.1f}" y="{ty - 19}" width="{wd + 4:.1f}" height="26" rx="5" '
                        f'fill="var(--ac)" fill-opacity=".14"/><rect x="{x:.1f}" y="{ty + 6}" width="{wd:.1f}" height="2.5" '
                        f'rx="1.2" fill="var(--ac)"/><text x="{x:.1f}" y="{ty - 26}" class="lb" fill="var(--ac)">ASPECT</text></g>')
                else:
                    marks.append(
                        f'<g class="{cls}" {st}><rect x="{x - 2:.1f}" y="{ty - 19}" width="{wd + 4:.1f}" height="26" rx="5" '
                        f'fill="var(--hi)" fill-opacity=".16" stroke="var(--hi)" stroke-opacity=".5"/>'
                        f'<text x="{x:.1f}" y="{ty - 26}" class="lb" fill="var(--hi)">OPINION</text></g>')
            a_txt = f'<tspan fill="var(--ac)">{escape(asp)}</tspan>' if asp else '<tspan fill="var(--mu)" font-style="italic">NULL</tspan>'
            tuples.append(
                f'<text x="{x0}" y="{ty + 42 + qi * 24}" class="tp {tcls}" {st}>'
                f'<tspan fill="var(--mu)">→ (</tspan>{a_txt}<tspan fill="var(--mu)">, </tspan>'
                f'<tspan fill="var(--hi)">{escape(opi)}</tspan><tspan fill="var(--mu)">, </tspan>'
                f'<tspan fill="var(--ink)">{escape(cat)}</tspan><tspan fill="var(--mu)">, </tspan>'
                f'<tspan fill="{SENT_COLORS[pol]}" font-weight="800">{pol}</tspan><tspan fill="var(--mu)">)</tspan></text>')

        implicit = any(a is None for a, *_ in quads)
        tag = ("implicit aspects" if implicit else
               "vietnamese" if any(ord(c) > 127 for c in sentence) else "english")
        groups.append(f"""  <g class="grp" style="animation-delay:{delay:.1f}s">
    <text x="{w - 24}" y="56" text-anchor="end" class="tg">{k + 1}/{len(ASQP_SENTENCES)} · {tag}</text>
    {''.join(marks)}
    <text x="{x0}" y="{ty}" class="sn" textLength="{tw:.0f}" lengthAdjust="spacingAndGlyphs" clip-path="url(#ty{k})">{escape(sentence)}</text>
    <rect x="{x0 + 1}" y="{ty - 17}" width="2" height="22" fill="var(--ac)" style="animation: car{k} {loop:.1f}s {delay:.1f}s infinite both"/>
    {''.join(tuples)}
  </g>""")

    h = ty + 42 + 24 + 44
    body = "\n".join(groups)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="Aspect sentiment quad prediction, demonstrated on three hotel reviews">
  <defs>
    <linearGradient id="edge" x1="0" y1="0" x2="{w}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0%" style="stop-color:var(--ac)"/><stop offset="100%" style="stop-color:var(--hi)"/>
    </linearGradient>
    <clipPath id="win"><rect width="{w}" height="{h}" rx="12"/></clipPath>
    {''.join(defs)}
  </defs>
  <style>{UI_CSS}
    .sn {{ font: 500 18px {MONO_FONT}; fill: var(--ink) }}
    .tp {{ font: 500 13px {MONO_FONT} }}
    .lb {{ font: 700 8.5px {MONO_FONT}; letter-spacing: 1.4px }}
    .tg {{ font: 500 10.5px {MONO_FONT}; fill: var(--mu) }}
    .cm {{ font: 400 11px {MONO_FONT}; fill: var(--mu) }}
    .ft {{ font: 400 10.5px {MONO_FONT}; fill: var(--mu) }}
    {chr(10).join("    " + c for c in css)}
    @media (prefers-reduced-motion: reduce) {{
      .grp,.hl,.hl2,.tu,.tu2 {{ animation: none !important; opacity: 0 }}
      .grp:first-of-type,.grp:first-of-type .hl,.grp:first-of-type .hl2,.grp:first-of-type .tu,.grp:first-of-type .tu2 {{ opacity: 1 }}
    }}
  </style>
  <g clip-path="url(#win)">
    <rect width="{w}" height="{h}" fill="var(--bg)"/>
    <rect width="{w}" height="34" fill="var(--panel)"/>
    <rect y="33" width="{w}" height="1" fill="var(--bd)"/>
    <rect width="{w}" height="2" fill="url(#edge)"/>
    <circle cx="20" cy="18" r="4" fill="#FF5F57"/><circle cx="34" cy="18" r="4" fill="#FEBC2E"/><circle cx="48" cy="18" r="4" fill="#28C840"/>
    <text x="66" y="22" class="cm">~/hotuyen21pt $ asqp --live "hotel review"</text>
    <text x="30" y="{ty}" class="sn" fill="var(--ac)" style="fill:var(--ac)">›</text>
{body}
    <rect y="{h - 30}" width="{w}" height="1" fill="var(--bd)"/>
    <text x="24" y="{h - 11}" class="ft">aspect sentiment quad prediction · one review in, (aspect, opinion, category, sentiment) out</text>
  </g>
  <rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="none" stroke="var(--bd)"/>
</svg>
"""


# ------------------------------------------------------------ project cards


@dataclass(frozen=True)
class Project:
    key: str            # output file: assets/projects/<key>.svg
    repo: str           # links the card; also shown in its footer
    title: str
    kicker: str         # what kind of work this is; also picks the card colour
    mono: str           # chip monogram
    tagline: str
    metrics: tuple      # three (value, label) pairs
    what: str
    stack: tuple
    footer: str = ""    # footer override when one card stands for two repos


# One colour per kind of work rather than one per project: eight hues read as
# decoration, three read as a legend.
KIND_COLORS = {
    "RESEARCH": "7C4DFF", "UNDERGRADUATE THESIS": "7C4DFF",
    "PAPER REPRODUCTION": "0EA5E9", "PAPER REPRODUCTIONS": "0EA5E9",
    "PRODUCT": "14B8A6",
}


PROJECTS = [
    Project("prism", "Prism", "PRISM", "RESEARCH", "PR",
            "Temporal aspect-based sentiment analysis at scale",
            (("1.95M", "Booking.com reviews"), ("10,631", "hotels, 2022 → 2025"), ("23,995", "gold multimodal quads")),
            "Aspect-level sentiment drift with semi-supervised quad extraction, cross-modal "
            "confidence calibration from images, and reviewer-adjusted drift tested with "
            "permutation nulls + BH-FDR.",
            ("Python", "OpenCLIP", "Statistics", "Docker")),
    Project("kltn", "KLTN-Token-Merging", "KLTN · Token Merging", "UNDERGRADUATE THESIS", "KL",
            "Vietnamese ABSA triplet extraction",
            (("2", "architectures"), ("GAS + UOS", "LLM extract & split"), ("FastAPI", "+ React demo UI")),
            "Joint (aspect, category, sentiment) extraction from Vietnamese hotel reviews: "
            "Joint ATE+APC against a T5 → BERT pipeline, GAS generative extraction and UOS "
            "clause splitting, plus the full LaTeX thesis.",
            ("T5", "BERT", "FastAPI", "React", "Ollama")),
    Project("cxr", "CXR-VQA-custom", "CXR-VQA", "PAPER REPRODUCTION", "CX",
            "Explainable chest X-ray VQA (arXiv:2511.00504)",
            (("4B", "MedGemma + LoRA"), ("60%", "released boxes wrong"), ("soft-GIoU", "differentiable bbox loss")),
            "MedGemma-4B-it fine-tuned under L_VQA + 0.5·L_bbox. A data audit found 60% of "
            "released QA pairs carried a mismatched ground-truth box; the published and the "
            "repaired data both ship behind a config switch.",
            ("MedGemma", "LoRA", "React UI", "Kaggle")),
    Project("evidencekd", "EvidenceKD-MedVQA", "EvidenceKD-MedVQA", "RESEARCH", "EK",
            "Evidence-grounded medical VQA with a verifier",
            (("180", "tests passing"), ("3-stage", "decide, explain, verify"), ("torch-free", "core logic")),
            "A decision branch produces the answer, findings and scores; a generator only "
            "explains them under a citation constraint; a verifier checks every claim. "
            "Faster R-CNN evidence detector with knowledge distillation.",
            ("Faster R-CNN", "Distillation", "pytest")),
    Project("multilabsa", "MultiLABSA", "MultiLABSA", "RESEARCH", "ML",
            "Dual-teacher multilingual quad prediction",
            (("2", "teachers: mT5 + XLM-R"), ("4-tuple", "quads per opinion"), ("1 cmd", "Docker Compose")),
            "A generative mT5 teacher and an extractive XLM-R teacher merged by Confidence "
            "Fusion, with multi-view and disagreement modules. Gradio UI, CLI and a "
            "one-command Docker Compose.",
            ("mT5", "XLM-R", "Gradio", "Docker")),
    Project("s2it", "s2it", "S2IT · Tree-CoT-RT", "PAPER REPRODUCTIONS", "S2",
            "Two ASQP baselines, rebuilt faithfully",
            (("NAACL '25", "S2IT"), ("ACL '26", "Tree-CoT-RT"), ("95", "tests")),
            "S2IT: three-stage syntax-guided tuning on one LoRA adapter with dependency-graph "
            "supervision. Tree-CoT-RT: type-specific reasoning trees, tSFT, then GRPO with a "
            "rule-based reward and self-consistent voting.",
            ("GRPO", "Stanza", "LoRA"), footer="hotuyen21pt/s2it  ·  /tree"),
    Project("warehouse", "Smart-Warehouse-Management", "Smart Warehouse", "PRODUCT", "SW",
            "IoT lot tracking for multi-branch warehouses",
            (("Go + Gin", "JWT REST API"), ("React 18", "TypeScript + Vite"), ("CV", "box-counter service")),
            "Barcode and QR scanning track lot numbers, manufacturing and expiry dates per SKU "
            "and branch, with a computer-vision service that counts boxes. Docker Compose for "
            "the whole stack.",
            ("Go", "Gin", "React", "TypeScript", "Docker")),
    Project("cccd", "Detect-CCCD", "Detect-CCCD", "PRODUCT", "ID",
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


def project_visual(key: str, acc: str) -> tuple[str, str]:
    """A small looping illustration of what the project does, drawn in a
    118x50 box at the card's top right. Returns (markup, css)."""
    v = {
        # Sentiment drift over 2022-2025: the line draws, holds, and redraws.
        "prism": (f"""
      <path d="M0,34 L20,26 L40,30 L60,17 L80,21 L100,8 L118,12 L118,40 L0,40 Z" fill="{acc}" fill-opacity=".10" class="fd"/>
      <polyline points="0,34 20,26 40,30 60,17 80,21 100,8 118,12" fill="none" stroke="{acc}" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" class="ln"/>
      <circle cx="118" cy="12" r="3" fill="{acc}" class="pl"/>
      <line x1="0" y1="40" x2="118" y2="40" stroke="var(--line)"/>
      <text x="0" y="49" class="vt">2022</text><text x="118" y="49" text-anchor="end" class="vt">2025</text>""",
                  """
    .ln { stroke-dasharray: 150; stroke-dashoffset: 150; animation: ln 5s ease-in-out infinite }
    @keyframes ln { 0% { stroke-dashoffset:150 } 40%,85% { stroke-dashoffset:0 } 100% { stroke-dashoffset:-150 } }
    .fd { animation: fd 5s ease-in-out infinite }
    @keyframes fd { 0%,20% { opacity:0 } 45%,80% { opacity:1 } 100% { opacity:0 } }"""),

        # Joint model vs a T5 -> BERT pipeline, data flowing through both.
        "kltn": (f"""
      <text x="0" y="13" class="vt">JOINT</text>
      <rect x="34" y="4" width="84" height="13" rx="4" fill="{acc}" fill-opacity=".14" stroke="{acc}" stroke-opacity=".5"/>
      <line x1="38" y1="10.5" x2="114" y2="10.5" stroke="{acc}" stroke-width="2" class="fl"/>
      <text x="0" y="39" class="vt">PIPE</text>
      <rect x="34" y="30" width="30" height="13" rx="4" fill="{acc}" fill-opacity=".14" stroke="{acc}" stroke-opacity=".5"/>
      <text x="49" y="39.5" text-anchor="middle" class="vt" fill="{acc}">T5</text>
      <line x1="66" y1="36.5" x2="84" y2="36.5" stroke="{acc}" stroke-width="2" class="fl"/>
      <rect x="86" y="30" width="32" height="13" rx="4" fill="{acc}" fill-opacity=".14" stroke="{acc}" stroke-opacity=".5"/>
      <text x="102" y="39.5" text-anchor="middle" class="vt" fill="{acc}">BERT</text>""",
                 """
    .fl { stroke-dasharray: 3 5; animation: fl 1s linear infinite }
    @keyframes fl { to { stroke-dashoffset: -8 } }"""),

        # A chest film with a grounded box and a scan line sweeping it.
        "cxr": (f"""
      <rect x="28" y="0" width="62" height="50" rx="6" fill="{acc}" fill-opacity=".07" stroke="{acc}" stroke-opacity=".35"/>
      <line x1="59" y1="6" x2="59" y2="46" stroke="{acc}" stroke-opacity=".45" stroke-width="2"/>
      {''.join(f'<path d="M57,{10 + i * 8} Q44,{8 + i * 8} 36,{15 + i * 8}" fill="none" stroke="{acc}" stroke-opacity=".4"/>'
               f'<path d="M61,{10 + i * 8} Q74,{8 + i * 8} 82,{15 + i * 8}" fill="none" stroke="{acc}" stroke-opacity=".4"/>'
               for i in range(4))}
      <rect x="64" y="17" width="18" height="15" rx="2" fill="none" stroke="{acc}" stroke-width="1.6" class="bb"/>
      <text x="96" y="22" class="vt" fill="{acc}">bbox</text>
      <text x="96" y="32" class="vt">+ VQA</text>
      <rect x="28" y="0" width="62" height="2" fill="{acc}" class="sc"/>""",
                """
    .sc { animation: sc 3s ease-in-out infinite }
    @keyframes sc { 0%,100% { transform: translateY(1px); opacity:.2 } 50% { transform: translateY(46px); opacity:.9 } }
    .bb { stroke-dasharray: 4 3; animation: bb 1.6s ease-in-out infinite }
    @keyframes bb { 0%,100% { stroke-opacity:.35 } 50% { stroke-opacity:1 } }"""),

        # Decide -> explain -> verify, with the check landing on each pass.
        "evidencekd": (f"""
      <line x1="18" y1="22" x2="51" y2="22" stroke="{acc}" stroke-width="2" class="fl"/>
      <line x1="67" y1="22" x2="100" y2="22" stroke="{acc}" stroke-width="2" class="fl"/>
      {''.join(f'<circle cx="{cx}" cy="22" r="9" fill="{acc}" fill-opacity=".15" stroke="{acc}"/>'
               f'<text x="{cx}" y="25.5" text-anchor="middle" class="vt" fill="{acc}" font-weight="800">{l}</text>'
               f'<text x="{cx}" y="44" text-anchor="middle" class="vt">{n}</text>'
               for cx, l, n in ((9, "D", "decide"), (59, "E", "explain"), (109, "V", "verify")))}
      <path d="M103,3 L107,7 L115,-1" fill="none" stroke="#3FB950" stroke-width="2.4" stroke-linecap="round" class="ck"/>""",
                       """
    .fl { stroke-dasharray: 3 5; animation: fl 1s linear infinite }
    @keyframes fl { to { stroke-dashoffset: -8 } }
    .ck { stroke-dasharray: 20; stroke-dashoffset: 20; animation: ck 2.4s ease-out infinite }
    @keyframes ck { 0%,40% { stroke-dashoffset:20 } 60%,90% { stroke-dashoffset:0 } 100% { stroke-dashoffset:20 } }"""),

        # Two teachers converge and fuse into one prediction.
        "multilabsa": (f"""
      <g class="ml"><circle cx="16" cy="20" r="10" fill="{acc}" fill-opacity=".2" stroke="{acc}"/>
        <text x="16" y="23" text-anchor="middle" class="vt" fill="{acc}">mT5</text></g>
      <g class="mr"><circle cx="102" cy="20" r="10" fill="{acc}" fill-opacity=".2" stroke="{acc}"/>
        <text x="102" y="23" text-anchor="middle" class="vt" fill="{acc}">XLM</text></g>
      <circle cx="59" cy="20" r="13" fill="{acc}" class="fu"/>
      <text x="59" y="23" text-anchor="middle" class="vt fu" fill="#FFFFFF" font-weight="800">fuse</text>
      <text x="59" y="46" text-anchor="middle" class="vt">confidence fusion</text>""",
                       """
    .ml { animation: ml 4s ease-in-out infinite } .mr { animation: mr 4s ease-in-out infinite }
    @keyframes ml { 0%,15% { transform:none; opacity:1 } 45% { transform: translateX(43px); opacity:.2 } 55%,100% { transform:none; opacity:1 } }
    @keyframes mr { 0%,15% { transform:none; opacity:1 } 45% { transform: translateX(-43px); opacity:.2 } 55%,100% { transform:none; opacity:1 } }
    .fu { opacity:0; animation: fu 4s ease-in-out infinite }
    @keyframes fu { 0%,38% { opacity:0 } 45%,60% { opacity:1 } 75%,100% { opacity:0 } }"""),

        # A reasoning tree grows and the rewarded leaf lights up.
        "s2it": (f"""
      <path d="M59,4 L30,24 M59,4 L88,24 M30,24 L16,44 M30,24 L44,44 M88,24 L74,44 M88,24 L102,44"
            fill="none" stroke="{acc}" stroke-width="1.6" class="tr"/>
      {''.join(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{acc}" class="nd" style="animation-delay:{d}s"/>'
               for x, y, d in ((59, 4, 0), (30, 24, .4), (88, 24, .4), (16, 44, .8), (44, 44, .8), (74, 44, .8), (102, 44, .8)))}
      <circle cx="74" cy="44" r="7" fill="none" stroke="#FACC15" stroke-width="2" class="rw"/>
      <text x="118" y="10" text-anchor="end" class="vt" fill="#FACC15">reward</text>""",
                 """
    .tr { stroke-dasharray: 160; stroke-dashoffset: 160; animation: tr 5s ease-in-out infinite }
    @keyframes tr { 0% { stroke-dashoffset:160 } 35%,90% { stroke-dashoffset:0 } 100% { stroke-dashoffset:160 } }
    .nd { transform-box: fill-box; transform-origin: center; animation: nd 5s ease-in-out infinite both }
    @keyframes nd { 0%,10% { transform: scale(0) } 25%,90% { transform: scale(1) } 100% { transform: scale(0) } }
    .rw { opacity:0; animation: rw 5s ease-in-out infinite }
    @keyframes rw { 0%,45% { opacity:0 } 55%,85% { opacity:1 } 100% { opacity:0 } }"""),

        # A barcode with a laser sweeping across it.
        "warehouse": (f"""
      {''.join(f'<rect x="{x}" y="4" width="{bw}" height="32" fill="var(--ink)" fill-opacity=".75"/>'
               for x, bw in ((8, 2), (12, 1), (15, 3), (20, 1), (23, 2), (28, 1), (31, 3), (36, 2), (40, 1), (43, 3),
                             (48, 1), (51, 2), (55, 3), (60, 1), (63, 2), (67, 1), (70, 3), (75, 2), (79, 1), (82, 3),
                             (87, 1), (90, 2), (94, 1), (97, 3), (102, 2), (106, 1), (109, 2)))}
      <text x="59" y="47" text-anchor="middle" class="vt">LOT 24-11 · EXP 2027</text>
      <rect x="4" y="1" width="2" height="38" fill="{acc}" class="lz"/>""",
                      """
    .lz { animation: lz 2.4s ease-in-out infinite alternate }
    @keyframes lz { from { transform:none } to { transform: translateX(108px) } }"""),

        # An ID card read line by line by OCR, then classified.
        "cccd": (f"""
      <rect x="4" y="1" width="110" height="46" rx="5" fill="{acc}" fill-opacity=".07" stroke="{acc}" stroke-opacity=".5"/>
      <rect x="11" y="9" width="22" height="28" rx="3" fill="{acc}" fill-opacity=".2"/>
      <circle cx="22" cy="19" r="5" fill="{acc}" fill-opacity=".6"/>
      <path d="M14,35 Q22,25 30,35" fill="{acc}" fill-opacity=".6"/>
      {''.join(f'<rect x="40" y="{y}" width="{bw}" height="4" rx="2" fill="var(--ink)" fill-opacity=".55" class="ox" style="animation-delay:{d}s"/>'
               for y, bw, d in ((10, 50, 0), (19, 64, .3), (28, 40, .6), (37, 56, .9)))}
      <rect x="4" y="1" width="110" height="2" fill="{acc}" class="sc"/>
      <text x="114" y="-3" text-anchor="end" class="vt cl" fill="#3FB950">CCCD ✓</text>""",
                 """
    .sc { animation: sc 3.6s ease-in-out infinite }
    @keyframes sc { 0% { transform: translateY(0); opacity:.2 } 45% { transform: translateY(44px); opacity:.9 } 50%,100% { opacity:0; transform: translateY(44px) } }
    .ox { transform-box: fill-box; transform-origin: left center; animation: ox 3.6s ease-out infinite both }
    @keyframes ox { 0%,5% { transform: scaleX(0) } 30%,90% { transform: scaleX(1) } 100% { transform: scaleX(0) } }
    .cl { opacity:0; animation: cl 3.6s ease-out infinite }
    @keyframes cl { 0%,50% { opacity:0 } 60%,90% { opacity:1 } 100% { opacity:0 } }"""),
    }
    markup, css = v[key]
    css += """
    .vt { font: 600 7.5px 'JetBrains Mono','Cascadia Code',Consolas,monospace }
    .vt:not([fill]) { fill: var(--dim) }
    .pl { transform-box: fill-box; transform-origin: center; animation: pl 2s ease-in-out infinite }
    @keyframes pl { 0%,100% { transform: scale(1) } 50% { transform: scale(1.6) } }"""
    return markup, css


def project_card(p: Project, n: int) -> str:
    acc, pad, w, h = f"#{KIND_COLORS[p.kicker]}", 18, PROJ_W, PROJ_H
    vis, vis_css = project_visual(p.key, acc)
    out = [
        f'<rect x="{pad}" y="20" width="36" height="36" rx="9" fill="{acc}"/>',
        f'<text x="{pad + 18}" y="42.5" text-anchor="middle" style="font:800 13px {FONT}" fill="#FFFFFF">{p.mono}</text>',
        f'<text x="{pad + 48}" y="30" style="font:700 8.5px {MONO_FONT};letter-spacing:1.6px" fill="{acc}">{escape(p.kicker)}</text>',
        f'<text x="{pad + 48}" y="50" style="font:700 17px {FONT}" fill="var(--ink)">{escape(p.title)}</text>',
        f'<g transform="translate({w - pad - 118},16)">{vis}</g>',
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
  <style>{PALETTE_CSS}{vis_css}
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

    for sub in ("contact", "sections"):
        (ASSETS / sub).mkdir(exist_ok=True)
    for key, glyph, label, _ in CONTACTS:
        (ASSETS / "contact" / f"{key}.svg").write_text(contact_pill(glyph, label), encoding="utf-8")
    for n, (key, title, hint) in enumerate(SECTIONS, 1):
        (ASSETS / "sections" / f"{key}.svg").write_text(section_title(n, title, hint), encoding="utf-8")
    (ASSETS / "focus.svg").write_text(focus_cards(), encoding="utf-8")
    (ASSETS / "asqp.svg").write_text(asqp_demo(), encoding="utf-8")
    print("wrote contact pills, section titles and focus cards")

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
