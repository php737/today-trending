#!python3
"""今日热榜 · jieba 分词模块

只负责「拉热榜 → 清洗 → jieba 切词 → 输出词频」,不画图。
供 make_wordcloud.py 调用,也可单独跑:

  python segment.py --top 20              # 打印词频 JSON
  python segment.py --top 20 --out w.json  # 存文件
  python segment.py --top 20 --topn 30     # 只看 TOP N

输出格式:{"张雪": 42.1, "台湾光复": 38.7, ...}
"""
import argparse
import json
import os
import re
import sys

import jieba

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import trending  # 同目录模块,进程内直接 import,不走 subprocess / 临时文件

# 停用词:热搜标题里的虚词/套话
STOPWORDS = set("""
的 了 在 和 与 为 是 有 也 就 都 而 及 或 等 被 把 让 使 从 到 对 于 这 那 其 之 中 上 下
我们 你们 他们 网友 官方 回应 发布 宣布 曝光 最新 视频 直播 讨论 关注
一个 什么 怎么 为什么 如何 真的 竟是 目击者 爆料 事件 情况 问题 方面 表示
今天 昨天 明天 上午 下午 晚上 记者 报道 消息 据悉 目前 已经 正在 可能 曾经 此前
这次 那次 之后 之前 有人 大家 自己 出来 起来 下去 上去 一样 一起 这些 那些
相关 引发 冲上 霸榜 上榜 登顶 爆火 刷屏 破防 出圈 全网 网友热议
""".split())

# 领域词:防止被切碎
CUSTOM_WORDS = [
    "台湾光复", "光复纪念日", "抗美援朝", "日本侵华",
    "吉尼斯纪录", "吉尼斯世界纪录", "水上漂", "张雪", "县委", "骑行", "机车", "摩托",
    "国考", "银保监会", "证监会", "自动驾驶", "人形机器人", "固态电池", "量子计算",
    "台风", "台风路径", "暴雨", "山洪", "滑坡", "泥石流", "地震", "余震", "救援",
    "涉未成年", "校园霸凌", "高空抛物", "电信诈骗", "AI生成", "人工智能", "大模型",
    "英伟达", "苹果", "华为", "小米", "特斯拉", "比亚迪", "小米汽车", "折叠屏",
    "苏超", "中超", "欧冠", "亚残运会", "全运会", "乒乓球", "羽毛球",
    "菜市场", "鹤岗", "房产", "二手房", "公积金", "房贷", "利率", "降息", "黄金",
    "特朗普", "普京", "泽连斯基", "白宫", "外交部", "商务部", "教育部",
    "孙颖莎", "马龙", "樊振东", "适应性", "地震局", "那曲", "西藏",
    # 领域词补充(2026-10-27):防止人名/外文人名被切碎
    "姆巴佩", "皇马", "中国足协", "金球奖", "凯恩", "孙颖莎", "卢茨",
    "总台", "央视", "外交部", "道歉", "解约", "交涉", "玉门关", "稻城亚丁",
    "三角梅", "蛟龙", "麒麟", "华为", "女首富", "双11", "天猫",
]

CLEAN = re.compile(r"[^一-鿿A-Za-z0-9]+")


def _init_jieba():
    for w in CUSTOM_WORDS:
        jieba.add_word(w, freq=100000)
    jieba.setLogLevel(60)


def fetch_trending(top: int = 20, platform: str | None = None) -> dict:
    """直接调 trending.collect(),进程内拿数据,不落临时文件。"""
    return trending.collect(top=top, only=platform)


def segment(data: dict) -> dict[str, float]:
    """把热搜标题按热度拆成词频。

    ⚠️ 2026-10-27 需求确认:词云**只放切开的词**,不再把短标题整句塞进去。
    (旧逻辑「≤8 字整句入云 +1.6 倍」导致 "今人重走玉门关" 这种整句占满词云)
    现在所有标题一律走 jieba 切词;切完只剩 1 个词时该词拿满权重。
    """
    _init_jieba()
    counter: dict[str, float] = {}
    for platform, items in data.items():
        if platform == "meta":
            continue
        for it in items:
            raw = (it.get("word") or "").strip()
            if not raw:
                continue
            # 热度归一化:平台量级差很多,用 sqrt 压平
            weight = float(it.get("hot_value") or 1) ** 0.5
            phrase = CLEAN.sub(" ", raw).strip()
            if not phrase:
                continue
            # 一律切词,整句不入云
            tokens = [t for t in jieba.lcut(phrase) if t.strip()]
            keep = [t for t in tokens
                    if t not in STOPWORDS
                    and len(t) >= 2
                    and CLEAN.sub("", t) == t]
            if not keep:
                continue
            # 只切出 1 个词 → 该词拿满权重;多个词 → 均摊
            share = weight if len(keep) == 1 else weight / len(keep)
            for t in keep:
                counter[t] = counter.get(t, 0) + share
    for k in list(counter):
        if k in STOPWORDS or len(k) < 2 or not CLEAN.sub("", k):
            del counter[k]
    return counter


def top_words(counter: dict, n: int = 30) -> list[tuple[str, float]]:
    return sorted(counter.items(), key=lambda x: -x[1])[:n]


def main():
    ap = argparse.ArgumentParser(description="今日热榜 jieba 分词")
    ap.add_argument("--top", type=int, default=20, help="每平台条数,默认 20")
    ap.add_argument("--platform", default=None, help="只处理一个平台")
    ap.add_argument("--out", default=None, help="输出 JSON 文件路径")
    ap.add_argument("--topn", type=int, default=0, help="只打印 TOP N 词")
    args = ap.parse_args()

    data = fetch_trending(args.top, args.platform)
    counter = segment(data)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(counter, f, ensure_ascii=False, indent=2)
        print(f"词频已保存:{args.out}({len(counter)} 个词)")

    if args.topn:
        print(json.dumps([{"word": w, "weight": round(v, 2)}
                          for w, v in top_words(counter, args.topn)],
                         ensure_ascii=False, indent=2))
    elif not args.out:
        print(json.dumps(counter, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
