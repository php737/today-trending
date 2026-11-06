# today-trending  今日热榜 今日热搜 今日头条

微博 / 抖音 / 百度 **实时热搜排行榜**一键拉取 —— 各 TOP 10 共 30 条,输出干净 JSON,附带一套「每条热搜配一句锐评」的渲染规范。

无状态:不落快照、不做历史差分。三平台并发抓取,整次 200-400ms。

## 这是什么

一个 OpenClaw skill + 一组可独立运行的 Python 脚本。核心能力是把三个平台的实时热搜榜抓成结构化 JSON;在此之上定义了一套**锐评渲染规范** —— 避免 AI 把榜单复述一遍(「某地被通报…」)却没给出任何观点。

- 📄 `SKILL.md` —— agent 侧的完整工作流:取数 → 识别跨平台共振 → 动态分组 → 锐评模板 → 出稿自检
- 🧠 锐评 ≠ 摘要。判断标准是**读完应该多出一个观点,而不是少一个信息点**
- 🔁 同事件多平台时,一条讲结果,一条讲机制/代价/情绪
- 🗂️ 无状态,不记录历史,不做涨跌对比(没有历史数据可对比,硬写就是编)

## 安装

```bash
git clone https://github.com/php737/today-trending
cd today-trending
pip install -r requirements.txt
```

依赖:`curl_cffi`(必需,三个平台的抓取都走它)、`jieba`、`lxml`(必需),`wordcloud`、`matplotlib`(仅词云功能需要)。

## 用法

```bash
# 三平台各 10 条(默认)
python3 scripts/trending.py

# 单平台
python3 scripts/trending.py --platform weibo

# 每平台 20 条(1-50)
python3 scripts/trending.py --top 20
```

> ⚠️ stdout 是纯 JSON,**不要加重定向、不要用 `head` 截断** —— 会破坏 JSON 结构。失败信息走 stderr。

### 词云图(可选)

```bash
python3 scripts/make_wordcloud.py --top 20
```

固定输出 `image/wordcloud.png`,同名覆盖。需要系统中文字体(默认找 Noto Sans CJK),且切词只放「词」不放整句标题。

## 输出样例

以下为真实运行输出(节选,三个平台各自取前两条):

```json
{
  "meta": {
    "fetched_at": "2026-11-06T15:25:02.807419+08:00",
    "elapsed_ms": 213,
    "platforms": {
      "weibo": "ok",
      "douyin": "ok",
      "baidu": "ok"
    }
  },
  "weibo": [
    {
      "word": "商南命案嫌犯孙某已死亡",
      "hot_value": 170.17,
      "board_rank": 1,
      "icon_desc": "新",
      "desc": "",
      "rank": 1,
      "url": "https://s.weibo.com/weibo?q=%E5%95%86%E5%8D%97%E5%91%BD%E6%A1%88%E5%AB%8C%E7%8A%AF%E5%AD%99%E6%9F%90%E5%B7%B2%E6%AD%BB%E4%BA%A1"
    },
    {
      "word": "ShowMaker回应不敌BLG",
      "hot_value": 93.39,
      "board_rank": 2,
      "icon_desc": null,
      "desc": "",
      "rank": 2,
      "url": "https://s.weibo.com/weibo?q=ShowMaker%E5%9B%9E%E5%BA%94%E4%B8%8D%E6%95%8CBLG"
    }
  ]
}
```

字段说明见 `references/data-and-impl.md`。

## 模块地图

| 文件 | 职责 |
|---|---|
| `scripts/trending.py` | 取数。三平台并发 + 条目级容错,`collect(top, only)` 可被 import |
| `scripts/segment.py` | 切词。jieba 分词 + 停用词 + 领域词锁定,输出词频 dict(**不画图**) |
| `scripts/make_wordcloud.py` | 出图。读词频 → WordCloud PNG(**不切词**) |
| `references/data-and-impl.md` | 接口端点、解析实现、字段定义、容错约定 |
| `references/wordcloud.md` | 词云模块职责、分词参数、踩过的坑 |

数据流全在内存:`trending.collect()` → `segment.segment()` → `WordCloud`,零临时文件、零 subprocess。

## 实现要点

| 平台 | 端点 | 解析方式 |
|---|---|---|
| 微博 | `weibo.com/ajax/side/hotSearch` | JSON,校验 `ok==1` 后逐条取字段 |
| 抖音 | `iesdouyin.com/web/api/v2/hotsearch/billboard/word/` | JSON,`label` 枚举映射为中文角标 |
| 百度 | `top.baidu.com/board?tab=realtime` | 页面内嵌 `<!--s-data:{...}-->`,正则提取 |

几个容易踩的坑,已在代码和文档里标注:

- 百度 `hotScore` 是**字符串**,裸转 `int()` 会炸
- 微博 `realtime` 偶发混入置顶条目,此时 `board_rank` 为 `null` 但 `rank` 连续 —— 正常
- 脚本**不能叫 `wordcloud.py`**,和 pip 包同名会 `import self`
- 热度量级差 7 倍(微博 vs 百度),词云权重要用 `sqrt` 压平

## 非官方声明

本项目与微博、抖音、百度三个平台**无任何隶属或合作关系**,仅调用其公开可见的榜单页面/接口。相关数据版权归各平台所有,使用时请遵守各平台的服务条款。

## License

MIT
