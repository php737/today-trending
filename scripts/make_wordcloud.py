#!/usr/bin/env python3
"""今日热榜 · 词云生成模块

只负责「读词频 → 画词云 → 存 PNG」,切词逻辑在 segment.py。
固定输出到 skill 的 image/ 目录,同名文件每次覆盖,不需要手动删。

  python make_wordcloud.py                       # 拉热榜(默认每平台20条)→ 出图
  python make_wordcloud.py --top 30              # 拉更多
  python make_wordcloud.py --from w.json         # 用已有词频 JSON
  python make_wordcloud.py --out /tmp/x.png       # 换输出路径

默认输出:<skill-dir>/image/wordcloud.png
"""
import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from wordcloud import WordCloud

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import segment  # 同目录模块,进程内直接 import,不走 subprocess / 临时文件

SKILL_DIR = os.path.dirname(SCRIPT_DIR)
IMAGE_DIR = os.path.join(SKILL_DIR, "image")
DEFAULT_OUT = os.path.join(IMAGE_DIR, "wordcloud.png")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def pick_font() -> str:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到中文字体,无法渲染词云")


def load_counter(args) -> dict[str, float]:
    """优先用已有词频 JSON;否则进程内拉热榜 + 切词,全程不落临时文件。"""
    if args.from_json:
        with open(args.from_json, encoding="utf-8") as f:
            return json.load(f)
    data = segment.fetch_trending(args.top, args.platform)
    return segment.segment(data)


def render(counter: dict, out_path: str, max_words: int = 200,
           width: int = 1000, height: int = 800) -> str:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    wc = WordCloud(
        font_path=pick_font(),
        width=width,
        height=height,
        background_color="white",
        max_words=max_words,
        min_font_size=10,
        colormap="tab10",
        collocations=False,
    ).generate_from_frequencies(counter)

    plt.figure(figsize=(12, 8))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.tight_layout(pad=0)
    plt.savefig(out_path, dpi=120, bbox_inches="tight", facecolor="white")
    plt.close()
    return out_path


def main():
    ap = argparse.ArgumentParser(description="今日热榜词云")
    ap.add_argument("--top", type=int, default=20, help="每平台条数,默认 20")
    ap.add_argument("--platform", default=None, help="只处理一个平台")
    ap.add_argument("--from", dest="from_json", default=None, help="使用已有词频 JSON")
    ap.add_argument("--out", default=DEFAULT_OUT, help=f"输出 PNG,默认 {DEFAULT_OUT}")
    ap.add_argument("--max-words", type=int, default=200, help="最大词数,默认 200")
    args = ap.parse_args()

    counter = load_counter(args)
    if not counter:
        print("没有可用词", file=sys.stderr)
        sys.exit(1)

    out = render(counter, args.out, max_words=args.max_words)
    top = sorted(counter.items(), key=lambda x: -x[1])[:20]
    print(f"图片已保存:{out}")
    print(json.dumps([{"word": w, "weight": round(v, 2)} for w, v in top],
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
