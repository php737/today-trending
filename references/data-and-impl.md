# 数据格式与抓取实现

SKILL.md 只管**怎么渲染**。这里管**脚本吐出什么、怎么吐的** —— 调试脚本、字段对不上、平台挂了的时候读。

## 输出格式(JSON schema)

```json
{
  "meta": {
    "fetched_at": "2026-10-10T09:51:27+08:00",
    "elapsed_ms": 320,
    "platforms": {"weibo": "ok", "douyin": "ok", "baidu": "ok"}
  },
  "weibo":  [{"rank": 1, "board_rank": 1, "word": "...", "hot_value": 289.27,
              "icon_desc": "新", "desc": "", "url": "..."}, ...N 条],
  "douyin": [...N 条],
  "baidu":  [...N 条]
}
```

| 顶层 key | 说明 |
|---|---|
| `meta.fetched_at` | ISO 8601,东八区 |
| `meta.elapsed_ms` | 三平台并发耗时(ms) |
| `meta.platforms` | **只含本次实际请求的平台**。`--platform weibo` → `{"weibo": "ok"}` |
| `<平台>` | 该平台 TOP N(默认 10,`--top` 上限 50),失败时为 `[]` |

每条热搜字段:

| 字段 | 说明 |
|---|---|
| `rank` | **过滤后**的输出名次,1-based,连续无空洞。做名次用这个 |
| `board_rank` | 榜单原始名次,只做交叉验证,不用于排序 |
| `word` | 热搜词,已清洗(压缩空白、丢弃空/超长/非字符串) |
| `hot_value` | 热度,单位**万**,浮点 2 位。脏值回落 `0.0` 而非崩溃 |
| `icon_desc` | 角标:`新`/`热`/`爆`/`沸`/`首发`。微博取 `icon_desc`,抖音按 `label` 枚举映射,百度为 `null` |
| `desc` | 百度专有:榜单条目描述(截断 80 字),写锐评的**第一信息源**;微博/抖音恒为 `""` |
| `url` | 搜索链接 |

> ⚠️ **`board_rank` 不一定连续**。微博 `realtime` 偶发混入无 `realpos` 的置顶条目,此时 `board_rank` 为 `null` 且 `rank` 连续 —— 这是正常的。

## 行为约定

- 三平台并发抓取(asyncio.gather),整次 200-400ms
- **不写任何文件**。stdout 纯 JSON,失败信息走 stderr
- 平台失败不阻断其它平台
- 不带 `--platform` 三平台都抓;带则单平台
- **条目级容错优先**:单条脏数据只丢该条,不影响其余条目;脏热度回落 0
- **平台级失败才标 `failed`**,异常信息必带平台名 + 具体原因(风控/端点下线/页面改版/类型异常)

## 解析实现

| 平台 | 端点 | 解析方式 |
|---|---|---|
| 微博 | `weibo.com/ajax/side/hotSearch` | JSON。校验 `ok==1` → `data.realtime` 非 null 且为 list;逐条读 `word`/`num`/`realpos`/`icon_desc` |
| 抖音 | `iesdouyin.com/web/api/v2/hotsearch/billboard/word/` | JSON。校验 `word_list` 存在且为 list;`label` 数字枚举映射为中文角标 |
| 百度 | `top.baidu.com/board?tab=realtime` | 页面内嵌 `<!--s-data:{...}-->`,用 `re.search(r'<!--s-data:(.*?)-->', text, re.S)` 提取。剔除 `isTop=True` 的置顶项,`index` 是 0-based 需 `+1` |

> 百度 `hotScore` 是**字符串**(`"7904377"`),`_safe_int` 会转;误用 `int()` 裸转会炸。

## 调用禁令

> ⚠️ **不要用 `head` 截断输出**。脚本体量有界(≈15 KB / 30 条),head 截断会破坏 JSON 结构导致解析失败。直接全量输出即可。

> 🚫 **不要加 `2>` / `2>&1` / `> /tmp/*.json` 任何重定向**。stdout 本来就是纯 JSON,直接跑就行;工具会分开返回 stdout 和 stderr。
