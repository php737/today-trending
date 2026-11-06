# 今日热榜 · 词云图实现细节

SKILL.md 只留触发条件和入口,细节在这里。**词云是按需功能 —— 用户明确要才跑。**

## 模块职责(三个,全部进程内 import)

| 模块 | 职责 |
|---|---|
| `scripts/trending.py` | 取数。`collect(top, only)` 可被 import,也能当 CLI 跑 |
| `scripts/segment.py` | 切词。import `trending.collect()` → jieba → 词频 dict(**不画图**) |
| `scripts/make_wordcloud.py` | 出图。import `segment` → 词云 PNG(**不切词**) |

**数据流**:`trending.collect()` → `segment.segment()` → `WordCloud` —— 全在内存里,零临时文件、零 subprocess。

## 命令

```bash
# 一步出图
python3 scripts/make_wordcloud.py --top 20

# 只看词频
python3 scripts/segment.py --top 20 --topn 30

# 词频存盘(仅当需要留存/复用)
python3 scripts/segment.py --top 20 --out /tmp/w.json
python3 scripts/make_wordcloud.py --from /tmp/w.json
```

**固定输出**:`<skill-dir>/image/wordcloud.png`,**同名覆盖**,不用手动删。
出图后用 `MEDIA:` 单独一行发给用户看。

## 渲染参数

参考实现:

```python
WordCloud(
    font_path=FONT_PATH,          # Noto Sans CJK
    width=1000, height=800,
    background_color="white",
    max_words=200, min_font_size=10,
    colormap="tab10",
    collocations=False,            # 停用默认的搭配词合并
).generate_from_frequencies(counter)
```

输出 PNG 实际尺寸约 1224×984(1200×960 + bbox 边距)。

## 分词要点(jieba)

- **停用词表**滤掉热搜套话:网友 / 回应 / 曝光 / 刷屏 / 全网 / 官宣 / 现身 …… 不滤的话词云会被垃圾词占满
- **`CUSTOM_WORDS`** 锁住领域词防切碎:台湾光复、吉尼斯纪录、水上漂、国考、苏超、亚残运会、地名、机构名…… 人名/外文人名极易被切碎("姆巴佩"→"姆巴"),发现就往 `CUSTOM_WORDS` 里补
- **热度用 `sqrt` 压平** —— 微博 111 和百度 780 的量级差 7 倍,直接用会把微博的词全压没
- **⚠️ 一律切词,整句不入云**(2026-10-27 需求确认)。旧逻辑「≤8 字整句入云 +1.6 倍」会把 "今人重走玉门关""万花世界杀青" 这种整句塞进词云占满版面 —— 词云只该放**词**,不是标题。切完只剩 1 个词时该词拿满权重,多个词则均摊
- 词云本身**不做情绪/分类** —— 那是另一回事,别混进来

## 踩过的坑

- ⚠️ 脚本**不能叫 `wordcloud.py`** —— 和 pip 包同名会 `import self`,报 `cannot import name 'WordCloud'`
- ⚠️ 同目录模块 import 前要 `sys.path.insert(0, SCRIPT_DIR)`,否则找不到 `trending` / `segment`
- ⚠️ 依赖:`python -m pip install jieba wordcloud`
- ⚠️ 字体必须是中文字体,系统里是 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`
- ⚠️ 用 `python3` 运行;若依赖装在虚拟环境里,用该环境的解释器绝对路径

## 文件位置

```
<skill-dir>/
├── SKILL.md
├── image/wordcloud.png        ← 固定名,每次覆盖
├── references/
│   ├── data-and-impl.md       ← 热榜接口/解析/容错
│   └── wordcloud.md           ← 本文件
└── scripts/
    ├── trending.py
    ├── segment.py
    └── make_wordcloud.py
```
