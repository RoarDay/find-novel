# Research: fanqienovel.com 可接入性深探

- **Query**: 为实现 `FanqieParser`（与 `FalooParser` 同级）铺路，需求 = 目录 + 前 20 章 + 搜索（推荐用）
- **Scope**: external（GitHub 源码 + 直接 HTTP 探测，未用 chrome-devtools）
- **Date**: 2026-07-21
- **样本**: bookId `7143038691944959011`（《十日终焉》，悬疑脑洞/完结/1496 章/VIP）

## 速览结论

| # | 维度 | 可行性 | 一句话 |
|---|---|---|---|
| 1 | 搜索 | ❌ web 不可拿 | XHR `/api/author/search/search_book/v1` 存在但被 secsdk 锁空 body；APP API 仍 `PARAM_INVALID` |
| 2 | 分类/排行 | ✅ 强 | `/api/rank/recommend/list` 全字段 JSON 裸拿 |
| 3 | 详情页元数据 | ✅ 强 | `/page/{id}` 内联 `__INITIAL_STATE__.page` 全字段 |
| 4 | 目录 | ✅ 强 | `/api/reader/directory/detail?bookId=` 带 `isChapterLock` 标记 |
| 5 | 前 20 章 | ⚠️ VIP 卡死 10 章 | VIP 书 web 仅给前 10 章全文，第 11 章起 2 段预览 |
| 6 | PUA 字体解密 | ✅ 当前 100% 覆盖 | 字体 URL 未轮换，romcere 362 条表全解 |
| 7 | 反爬现状 | ⚠️ 低-中 | 裸 requests 可拿内容；签名墙只挡 `/api/author/*` 与 APP API |

**最关键结论**：
- ❌ **搜索不可实现**（裸 requests 下）。这是与上一版调研的最大变化——XHR endpoint 找到了（`/api/author/search/search_book/v1`），但被 ByteDance secsdk 锁成 0 字节 body。
- ✅ **目录 + 前 10 章内容**完全可实现，font_map 稳定。
- ⚠️ **前 20 章**对 VIP 书不可达，建议把目标改为「免费章节（前 10）」。

---

## 1. 搜索 ❌ 不可实现（web XHR 锁死，APP 签名墙）

### 1a. Web XHR endpoint（已逆向，但锁空）

- **URL**：`https://fanqienovel.com/api/author/search/search_book/v1`
- **方法**：GET
- **关键参数**：`query_word=<kw>&aid=1967&page_count=0&query_type=0&filter=0`
- **来源**：`muye_b9835416.js`（fanqie 主 SPA bundle）反编译：
  ```js
  var $="/api/author/search/search_book/v1";
  function ee(e,t,o,i){ ... Object(_.N)({url:$, params:X(X({},o),{},{query_word:e})}, r)
    .then(function(e){
      var o=e.data||{},
          r=o.search_author_data_list,
          n=o.search_book_data_list,    // ← 结果字段
          a=o.total_count;
      t({searchBookList:n||[], authorData:r||[], total:a||0, ...});
    })}
  ```
- **响应结构（推断）**：`{code, data:{search_book_data_list:[{...}], search_author_data_list:[...], total_count:N}}`
- **实测**：
  | 请求 | 结果 |
  |---|---|
  | `curl ...?query_word=法师&aid=1967` | HTTP 200, **body 0 字节** |
  | 加 `Referer: /search/法师` | HTTP 200, body 0 字节 |
  | POST | HTTP 403 "Invalid Content-Type" |
  | HEAD（curl -I） | HTTP 404，响应头含 `x-tt-agw-login: 0` |
- **原因**：muye.js 引入 `window.byted_acrawler` + `secsdk`（15 处引用），axios 拦截器注入 `msToken`/`x-bogus` 签名头；缺签 → 网关返回空 body。
- **结论**：裸 requests 拿不到，需 browser emulation（selenium/playwright）或 secsdk 逆向，超出 parser 范围。

### 1b. APP API（持续签名墙）

- **URL**：`https://api5-normal-lf.fqnovel.com/reading/bookapi/search/page/v/`
- **实测**：`{"code":100103,"message":"PARAM_INVALID","data":null}`（缺 x-argus/x-helios/x-medusa）
- **ying-ck/fanqienovel-downloader `src/main.py:193-234` 的 `search_novel()` 正是用此 API**——其 README 注明 "v1.1.5及以下版本API失效"，当前 v1.1.14 的搜索路径实际不可用（无签名）。
- 字节系签名算法每请求一签、未开源，不可复用。

### 1c. 备选

- 全文搜索可走 ying-ck 推荐的衍生工具 [qxqycb/search-novel](https://github.com/qxqycb/search-novel)（本地索引，非实时站搜）。
- 番茄的天然优势是**结构化分类**，搜索缺口可用分类/排行补足（见第 2 节）。

---

## 2. 分类/排行 ✅ 强（弥补搜索缺口的主力）

### 2a. `/api/rank/recommend/list`（推荐榜，强）

- **URL**：`https://fanqienovel.com/api/rank/recommend/list?aid=1967&gender={0|1}`
- **实测**：HTTP 200, 9.4 KB JSON
- **gender**：`0`=男频，`1`=女频
- **字段（每本书）**：
  ```json
  {"bookId":"7080092010052324352","bookName":"特工易冷","author":"骁骑校",
   "abstract":"（原名特工易冷）玉梅饭店的厨子...","category":"都市日常",
   "thumbUri":"https://p3-novel-sign.byteimg.com/..."}
  ```
- **价值**：自带 abstract（长简介）+ 分类，**直接可作 SearchResult**，无需补抓详情页。

### 2b. `/api/rank/recent/update/list`（最近更新）

- **URL**：`https://fanqienovel.com/api/rank/recent/update/list?aid=1967&gender={0|1}&page_count=0`
- **实测**：HTTP 200, 5.4 KB JSON
- **字段**：`bookId/bookName/itemId/title/category/updateTime/author/uid/needPay`
- **价值**：分页 `page_count=0/1/2...`，可枚举；但**无 abstract**，需补抓详情页。

### 2c. `/api/rank/category/list`（分类榜，参数未对齐）

- 实测多组参数（`gender=0&rank_type=1&category_id=539&page_count=0` 等）均返回：
  ```json
  {"code":0,"data":{"book_list":[],"rankTypeText":"","total_num":0}}
  ```
- 推测参数名变了（旧版文档过时），需 chrome-devtools 抓真实 XHR 才能补全；暂不可用。

### 2d. 分类树（37 个，静态嵌入 `/rank` 页 HTML）

沿用上一版调研结论（`/rank` 页 `__INITIAL_STATE__.rank.rankCategoryTypeList` 静态可拿）：

```python
male_cats = {1141:"西方奇幻", 1140:"东方仙侠", 8:"科幻末世", 261:"都市日常",
             124:"都市修真", 1014:"都市高武", 273:"历史古代", 27:"战神赘婿",
             263:"都市种田", 258:"传统玄幻", 272:"历史脑洞", 539:"悬疑脑洞",
             262:"都市脑洞", 257:"玄幻脑洞", 751:"悬疑灵异", 504:"抗战谍战",
             746:"游戏体育", 718:"动漫衍生", 1016:"男频衍生"}
female_cats = {1139:"古风世情", 1015:"女频衍生", 248:"玄幻言情", 23:"种田",
               79:"年代", 267:"现言脑洞", 246:"宫斗宅斗", 253:"古言脑洞",
               24:"快穿", 749:"青春甜宠", 745:"星光璀璨", 747:"女频悬疑",
               750:"职场婚恋", 748:"豪门总裁", 1017:"民国言情"}
```

---

## 3. 详情页元数据 ✅ 全字段内联

- **URL**：`https://fanqienovel.com/page/{book_id}`
- **实测**：HTTP 200, 703 KB HTML，内嵌 359 KB `__INITIAL_STATE__` JSON
- **抽取方法**（brace-match + `undefined→null` 归一化）：
  ```python
  import re, json
  idx = html.find('__INITIAL_STATE__')
  start = html.find('{', idx)
  # 向后 brace-match 找闭合 }
  depth = 0
  for i in range(start, len(html)):
      if html[i] == '{': depth += 1
      elif html[i] == '}':
          depth -= 1
          if depth == 0:
              end = i + 1; break
  state = json.loads(re.sub(r'\bundefined\b', 'null', html[start:end]))
  page = state['page']
  ```
- **`page` 字段实测**（《十日终焉》）：

  | 字段 | 类型 | 示例 |
  |---|---|---|
  | `bookId` | str | `'7143038691944959011'` |
  | `bookName` | str | `'十日终焉'` |
  | `author` | str | `'杀虫队队员'` |
  | `abstract` | str(长) | `'24年番茄年度巅峰榜TOP1 \| ...'`（推荐语义主依据） |
  | `description` | str(短) | `'心中有个世界，想带你们去看看。'` |
  | `wordNumber` | int | `3201288` |
  | `readCount` | int | `2567353` |
  | `creationStatus` | int | `0` |
  | `status` | int | `1`（推测 1=完结） |
  | `category` | str | `''`（**空**，看 `categoryV2`） |
  | `categoryV2` | list[obj] | `[{ObjectId:539, Name:"悬疑脑洞", ExternalDesc:"环环相扣挑战心理极限", Gender:2}]` |
  | `itemIds` | list[str] | 全 1496 个 chapter id（与目录 API 一致） |
  | `chapterListWithVolume` | list[list[obj]] | 分卷二维，每项 `{itemId, title, ...}` |
  | `volumeNameList` | list[str] | `['第一卷：...', ...]` |
  | `chapterTotal` | int | `1496` |
  | `lastChapterTitle` | str | `'陈俊南（终）'` |

- **重要**：`page.chapterListWithVolume` 已是结构化目录（带 title），**可省一次目录 API 调用**。

---

## 4. 目录 API ✅ 带 VIP 锁标记

- **URL**：`https://fanqienovel.com/api/reader/directory/detail?bookId={book_id}`
- **实测**：HTTP 200, 398 KB JSON，无需 cookie/header（UA 即可）
- **结构**：
  ```python
  {
    "code": 0,
    "data": {
      "allItemIds": ["7173216089122439711", ...],          # 扁平 chapter id
      "volumeNameList": ["第一卷：...", ...],
      "chapterListWithVolume": [[                          # 分卷二维
        {"itemId":"...","title":"第1章 空屋",
         "needPay":0,"isChapterLock":false,                # ← VIP 锁标记
         "isChapterLock":false,"isPaidPublication":false,
         "isPaidStory":false,"volume_name":"第一卷：...",
         "realChapterOrder":"1","firstPassTime":"1670144602"},
        ...
      ], ...]
    }
  }
  ```
- **`isChapterLock` 实测分界**（《十日终焉》VIP）：

  | 章 | isChapterLock | web 内容 |
  |---|---|---|
  | 第 1-10 章 | `false` | ✅ 全文（ch1: 66 段, 2345 字） |
  | 第 11 章+ | `true` | ⚠️ 仅 2 段预览（HTML 含 VIP/SVIP/登录/下载番茄 标记） |

---

## 5. 前 20 章 ⚠️ VIP 卡死 10 章

### 5a. 章节正文 URL

- `https://fanqienovel.com/reader/{chapter_id}`
- HTTP 200, 45 KB HTML（无锁章节）/ 30 KB（锁章节，预览）

### 5b. VIP 边界实测

| 章节 | 文本提取 | 字数估计 |
|---|---|---|
| 第 1 章 (`isChapterLock=false`) | 66 段 `<p>`，1456 个 PUA 字符全可解 | ~2345 字 |
| 第 11 章 (`isChapterLock=true`) | 仅 2 段 `<p>` | ~50 字预览 |

锁章节 HTML 包含标记词：`VIP` / `登录` / `SVIP` / `阅读全文` / `下载番茄` / `本章字数`。

### 5c. `/api/reader/full?itemId=` 已废弃

- 实测 HTTP 200, **0 字节 body**（与上一版调研一致）。
- ying-ck 代码作为 fallback 的这条路径**已不可用**。

### 5d. 实际可拿章节数

- **VIP 书**：web 前 10 章（`isChapterLock=false`）全文 + 第 11+ 章预览。
- **免费书**（番茄仍有大量全免费作品）：所有章 `isChapterLock=false`，理论上全可拿（未单测，但 `/api/rank/recommend/list` 推荐位多见免费书）。
- **「前 20 章」需求**：VIP 书不可达，建议目标改为「**前 N 个免费章节**（N≤10 for VIP, N=all for free）」。

---

## 6. PUA 字体解密 ✅ 当前 100% 覆盖（romcere 表稳定）

### 6a. 字体 URL（未轮换）

- 章节 HTML 内联 `@font-face`：
  ```
  font-family: DNMrHsV173Pd4pgy;
  src: url(https://lf6-awef.bytetos.com/obj/awesome-font/c/dc027189e0ba4cd.woff2)
  ```
- 文件名 `dc027189e0ba4cd` —— **与 romcere 2024 年抓取的字体同名**（仅后缀 `.otf→.woff2`），字形未变。

### 6b. romcere font_map（362 条，实测全解）

- 来源：[romcere/fanqienovel-decryptor `dicts/font_map.py`](https://github.com/romcere/fanqienovel-decryptor/blob/main/dicts/font_map.py)（7.1 KB）
- 格式：`{pua_codepoint_as_string: actual_char}`，PUA 范围 58353–58715（U+E441–U+E55B）
- **实测覆盖率**（《十日终焉》第 1 章 1456 个 PUA 字符）：**100% mapped, 0 unmapped**
- 备用表：[ying-ck `charset.json`](https://github.com/ying-ck/fanqienovel-downloader/blob/main/src/charset.json)，同范围

### 6c. 集成方式

```python
# 简化版解码
def decode_pua(text: str, font_map: dict) -> str:
    return ''.join(font_map.get(str(ord(c)), c) for c in text)
```

实测样本：
- raw：`旧钨丝灯黑线悬屋央，闪烁昏暗芒。`（混 PUA 码点）
- decoded：`一个老旧的钨丝灯被黑色的电线悬在屋子中央，闪烁着昏暗的光芒。`

### 6d. 轮换风险

- 字体 URL 自 2024 至今（2026-07）未变，romcere 表持续有效。
- ByteDance 保留轮换权，**建议**：
  - parser 内置静态表（romcere 362 条，~8 KB）
  - 加 sanity check：解码后若 PUA 残留率 > 5%，日志告警提示字表过期
  - 不内置动态字体解析（fontTools）——除非轮换真的发生

---

## 7. 反爬现状 ⚠️ 低-中（裸 requests 可用）

| 项 | 状态 | 说明 |
|---|---|---|
| 登录墙 | 无 | `/page/`, `/api/reader/directory/detail`, `/reader/{id}` 全可裸拿 |
| Cookie | 非必需 | 无 cookie: 45148 字节；带 `novel_web_id=...`: 45153 字节（差异可忽略） |
| User-Agent | 普通桌面浏览器 UA 即过 | Chrome 126 UA 全通 |
| 字体混淆 | PUA 字体 | romcere 表 100% 解 |
| Web XHR 签名 | `msToken`/`x-bogus`（secsdk 注入） | **只挡 `/api/author/*`**，不影响 `/api/reader/*` 与 `/api/rank/recommend/*` |
| APP API 签名 | x-argus/x-helios/x-medusa | 挡 `api5-normal-*.fqnovel.com`，不影响 web |
| 字体验证码 | 未触发 | 20+ 次探测 0 触发 |
| Rate limit | 未压测 | 保守 ≥1 s/req + 随机抖动 |

**裸 requests 能拿**：
- ✅ 书页详情（全字段元数据 + 全 chapter id 列表）
- ✅ 目录 JSON（含 isChapterLock）
- ✅ 前 10 章正文（解密后）
- ✅ 分类树 + `/api/rank/recommend/list`、`/api/rank/recent/update/list`

**裸 requests 拿不到**：
- ❌ `/search/{kw}` 的 XHR 结果（secsdk 锁空）
- ❌ APP 搜索/APP 章节 API（签名墙）
- ❌ VIP 书第 11 章起全文（业务侧 VIP 墙，非反爬）

---

## Parser 实现建议（FanqieParser）

### 应实现的方法

```python
class FanqieParser(BaseParser):
    headers = {"User-Agent": "Mozilla/5.0 ... Chrome/126 ..."}  # 桌面 UA

    @property
    def domain(self) -> str:
        return "fanqienovel.com"

    def parse_catalog(self, soup, base_url) -> list:
        """目录从 /page/{id} 内联 state.chapterListWithVolume 抽。
        沿用 QidianParser 套路：从 str(soup) 抽 __INITIAL_STATE__。
        返回 [(title, https://fanqienovel.com/reader/{itemId}), ...]。"""

    def parse_content(self, soup) -> str:
        """1. 抽 <div class="muye-reader-content noselect"> 内 <p> 文本
        2. 检测锁章：若 <p> 数 ≤ 2 或 HTML 含 'SVIP'/'下载番茄' → 返回 '' (或 '[VIP 锁章]')
        3. decode_pua(text, FONT_MAP)"""

    def get_blurb(self, url, fetch) -> str:
        """fetch /page/{id} → state.page.abstract"""

    def get_category(self, category, fetch) -> list:
        """category 形如 'male'/'female'/或 catId；
        走 /api/rank/recommend/list?gender={0|1}&aid=1967 → JSON list → SearchResult"""

    def get_rank(self, rank_type, fetch) -> list:
        """rank_type='recommend'|'recent'；对应 /api/rank/{recommend,recent/update}/list"""

    def get_chapter_titles(self, url, fetch, limit=20) -> list:
        """fetch /page/{id} → state.page.chapterListWithVolume 展平 → 取前 N 个 title"""

    def search(self, keyword, fetch) -> list:
        """❌ 不实现，返回 []（或抛 NotImplementedError）。
        原因：web XHR 被 secsdk 锁空，APP API 签名墙。
        建议主 agent 文档化「番茄搜索需 browser emulation」。"""
```

### 字体解密集成方案（推荐：静态表 + sanity check）

```python
# novel_crawler/sites/_fanqie_font_map.py（下划线前缀，registry 不当作 parser 加载）
FONT_MAP = {
    '58670': '0', '58413': '1', ...  # 362 条，从 romcere 复制
}

# novel_crawler/sites/fanqie.py
from ._fanqie_font_map import FONT_MAP

def _decode_pua(text: str) -> str:
    return ''.join(FONT_MAP.get(str(ord(c)), c) for c in text)

def parse_content(self, soup):
    # ... 抽 <p>
    raw = '\n'.join(p.get_text(strip=True) for p in ps)
    decoded = _decode_pua(raw)
    # ponytail: sanity check — 若 PUA 残留 >5% 提示字表过期
    pua_remain = sum(1 for c in decoded if 0xE000 <= ord(c) <= 0xF8FF)
    if pua_remain > len(decoded) * 0.05:
        log.warning("fanqie font_map 可能过期：%d/%d PUA 未解", pua_remain, len(decoded))
    return decoded
```

**为什么不用 fontTools 动态解**：字体 URL 两年未轮换，romcere 表 100% 覆盖；动态解析需额外依赖（fontTools）+ 字体下载 + 字形比对（OCR 或哈希），收益不抵成本。轮换真发生再加。

### 前 20 章 VIP 边界处理

```python
# get_chapter_titles 已知边界：
# - VIP 书：前 10 章可拿全文，11-20 章只能拿 title（来自目录 API）+ 50 字预览
# - 免费书：全部可拿
# 建议：
#   1. get_chapter_titles 返回全部 20 个 title（即使后 10 章锁）
#   2. parse_content 对锁章返回 '' 或 '[本章 VIP 锁，web 不可读]'
#   3. 调用方（main agent / 语义推断）按非空章节做风格分析
#   4. 若必须 20 章全文，改用免费书样本（rank/recommend 多见）
```

### 关键 URL 清单

| 用途 | URL | 方法 | 说明 |
|---|---|---|---|
| 书页详情 | `https://fanqienovel.com/page/{book_id}` | GET | 内联 `__INITIAL_STATE__.page` |
| 目录 JSON | `https://fanqienovel.com/api/reader/directory/detail?bookId={id}` | GET | 带 `isChapterLock`，可选（书页已含） |
| 章节正文 | `https://fanqienovel.com/reader/{chapter_id}` | GET | 需 font_map 解密 |
| 推荐榜 | `https://fanqienovel.com/api/rank/recommend/list?aid=1967&gender={0\|1}` | GET | 全字段 JSON |
| 最近更新 | `https://fanqienovel.com/api/rank/recent/update/list?aid=1967&gender={0\|1}&page_count=0` | GET | 分页 |
| ~~搜索~~ | ~~`/api/author/search/search_book/v1`~~ | ~~GET~~ | ❌ secsdk 锁空 |
| ~~APP 搜索~~ | ~~`api5-normal-lf.fqnovel.com/reading/bookapi/search/page/v/`~~ | ~~GET~~ | ❌ PARAM_INVALID |

---

## Caveats / Not Found

- **搜索是硬缺口**：web XHR（`/api/author/search/search_book/v1`）被 secsdk 锁 0 字节 body，无法裸 requests 复现。若必须搜索，路径只有两条：(a) browser emulation（playwright/selenium），(b) 逆向 secsdk msToken/x-bogus 生成（工程量大、易失效）。两者都超出 BaseParser 范围。
- **`/api/rank/category/list` 参数名变了**：旧文档的 `gender/rank_type/category_id` 组合均返回空 `book_list`；要接入需 chrome-devtools 抓真实 XHR（本任务不允许）。建议 parser 走 `/api/rank/recommend/list` 替代，不强求分类榜。
- **第 11 章起 VIP 墙是业务侧**，非反爬；无法绕过（除非登录 SVIP 账号 cookie）。
- **romcere font_map 字表当前 100% 覆盖**，但 ByteDance 保留字体轮换权；parser 应加 sanity-check 告警，不应静默失败。
- **未对完全免费书做单测**：推测所有章 `isChapterLock=false`，但 web 是否对全免费书有兜底策略（如读 50 章后弹登录）未验证。
- **rate limit 阈值未知**：保守 ≥1 s/req + 随机 UA + 失败重试（沿用 engine 默认）。

## 参考开源项目

| 项目 | 语言 | 关键贡献 | 当前可用性 |
|---|---|---|---|
| [ying-ck/fanqienovel-downloader](https://github.com/ying-ck/fanqienovel-downloader) (2149★) | Python | 标杆实现；`src/main.py:193` search 用 APP API（已失效）；cookie `novel_web_id` 实测非必需 | ⚠️ 搜索路径失效，下载路径可用 |
| [zhongbai2333/Tomato-Novel-Downloader](https://github.com/zhongbai2333/Tomato-Novel-Downloader) (3227★) | Rust | 最新活跃；README 明确 x-a/x-l 签名墙现状 | ⚠️ Rust 源在本环境拉取超时 |
| [romcere/fanqienovel-decryptor](https://github.com/romcere/fanqienovel-decryptor) (43★) | Python | **`dicts/font_map.py` 362 条 PUA→字映射，实测 100% 覆盖** | ✅ 字表可用 |
| [Dlmily/Tomato-Novel-Downloader-Lite](https://github.com/Dlmily/Tomato-Novel-Downloader-Lite) (479★) | Python | 明确「官方改鉴权算法，差 x-a/x-l」 | ❌ 鉴权未补全 |
