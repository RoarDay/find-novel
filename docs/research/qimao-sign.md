# Research: 七猫 App API 签名方案（完整目录 / 全本下载）

- **Query**: 七猫 App API 签名算法 + chapter-list endpoint + 现成实现 + 2026 有效性
- **Scope**: external（GitHub 开源 + 实网实测）
- **Date**: 2026-07-21
- **方法**: `curl/jsdelivr` 拉 `shing-yu/swiftcat-downloader-flutter` Dart 源码 + 本地 Python 复刻签名实网验证（非 chrome）

## 关键结论（先看这条）

**签名 2026-07-21 仍有效**，三件套实测全部 200 OK：

| 用途 | 端点 | 2026 实测 |
|---|---|---|
| 完整目录 | `GET https://api-ks.wtzw.com/api/v1/chapter/chapter-list?id={book_id}&chapter_ver=0&sign=...` | ✅ 拿到 1063 章 |
| 全本加密 zip 链接 | `GET https://api-bc.wtzw.com/api/v1/book/download?id={book_id}&source=1&type=2&is_vip=1&sign=...` | ✅ 拿到 CDN zip 直链 |
| AES 解密 zip | key=`32343263636238323330643730396531` CBC，IV=base64 解码后前 16 字节 | ✅ 解出 UTF-8 中文 |

样本：book_id `1860026`（共 1063 章，8.6 MiB zip，解出第一章 3055 字明文）。

---

## 1. 签名算法（精确伪代码）

来源：`shing-yu/swiftcat-downloader-flutter/lib/core/api_client.dart:23-27`，本地复刻字字对齐。

```python
SIGN_KEY = 'd3dGiJc651gSQ8w1'  # 公共常量，dart 源码硬编码

def qimao_sign(params: dict, key: str = SIGN_KEY) -> str:
    # 1) 按 key 字典序排序
    # 2) 每项拼成 "k=v"（无 & 分隔，无 url encode）
    # 3) 末尾追加 signKey
    # 4) md5 hex 小写
    sign_str = ''.join(f"{k}={params[k]}" for k in sorted(params)) + key
    return hashlib.md5(sign_str.encode('utf-8')).hexdigest()
```

**坑点**：
- 是 `k=v` 紧挨拼接，**不是 querystring**（没有 `&`）。例：params `{b:2, a:1}` → `"a=1b=2" + key`。
- 值原样字符串化，**不 url encode**（签名计算用的是原始字符串）。
- url 里的 query 参数本身要正常 urlencode（`id=1860026&chapter_ver=0&sign=xxx`），签名只决定 `sign=` 那一项。
- `sign` 自身在计算时**不放入 params**（先把其他参数签名，再写回 `params['sign']`）。

### 必需请求头（`api_client.dart:29-41`）

```python
def qimao_headers(book_id: str) -> dict:
    # app-version 从硬编码池随机抽（用 book_id 做 seed 保持稳定也行）
    version = random.choice(VERSION_LIST)
    h = {
        "AUTHORIZATION": "",
        "app-version": version,                  # 必填，从池里抽
        "application-id": "com.****.reader",     # 字面量（就是 4 个星号）
        "channel": "unknown",
        "net-env": "1",
        "platform": "android",
        "qm-params": "",
        "reg": "0",
    }
    h['sign'] = qimao_sign(h)   # 头部整体也签一次，签名算法同上
    return h
```

`VERSION_LIST`（21 个，`api_client.dart:15-19`，2026 仍可用）：
```
73720 73700 73620 73600 73500 73420 73400
73328 73325 73320 73300 73220 73200 73100
73000 72900 72820 72800 70720 62010 62112
```

**实测**：`app-version` 池里随便挑一个就过；`application-id` 字面量就是 `com.****.reader`（四个 ASCII 星号，不是占位符）。

---

## 2. chapter-list endpoint 字段 + 响应结构

**请求**：
```
GET https://api-ks.wtzw.com/api/v1/chapter/chapter-list
  ?chapter_ver=0
  &id={book_id}
  &sign={md5(chapter_ver=0id={book_id}SIGN_KEY)}
Headers: 见上 qimao_headers(book_id)
```

**响应**（实测 book_id=1860026 摘录）：
```json
{
  "data": {
    "id": "1860026",
    "type": "chapter_lists",
    "chapter_lists": [
      {
        "id": "17231076120001",                 // 章节 ID（字符串）
        "content_md5": "8fda9fc82481950696a4fcb54cf0057e",
        "index": "1",                            // 字符串序号
        "title": "第1章  青楼猝死，世子无双",
        "words": "2947",                         // 字数（字符串）
        "chapter_sort": 1                        // 排序键（整数）
      },
      ...
    ]
  }
}
```

**注意字段名纠正**：`find-novel` 旧 research 写的是 `chapter_id/title/sort`，**实际字段是 `id` / `title` / `chapter_sort`**（不是 `chapter_id`，不是 `sort`）。`words` 是字符串。

**排序**：直接按 `chapter_sort` 升序就是阅读顺序（dart 代码 `api_client.dart:102` 做了 `(a,b) => a['chapter_sort'].compareTo(b['chapter_sort'])`）。

---

## 3. 现成实现引用

| 项目 | 语言 | 状态 | 价值 |
|---|---|---|---|
| `shing-yu/swiftcat-downloader-flutter` | Dart/Flutter | 活跃开源（main 分支），140⭐ | **首选参考** — `lib/core/api_client.dart`（139 行）含完整签名+AES+chapter-list+download，本调研字字对齐复刻 |
| `shing-yu/swiftcat-downloader` | Python | 归档/闭源（仅发二进制），43⭐ | 无源码可用 |
| `FrankMilesFrms/KMaoDecode` | Kotlin/Android | 未深入（35⭐） | 备选 |
| `qisumi/fanqie-qimao-downloader` | Python | 活跃（13⭐，2026-05 更新） | **不直连** App API，走第三方付费 "Rain API V3" 代理；签名细节不可见，仅作字段名交叉验证（确认 `chapter_lists[].id`） |

**Python 直连实现**：GitHub Code Search 需登录无法批量搜；目前没找到公开的 Python 直连实现（除 Dart 版自己翻译）。本调研即为一个。

**2026 有效性**：✅ 实测通过（见「关键结论」），无 IP 封、无 token、无一次性 nonce。

---

## 4. AES 解密（章节内容加密）

来源：`api_client.dart:126-139`。本调研本地用 `pycryptodome` 复刻验证。

```python
AES_KEY = bytes.fromhex('32343263636238323330643730396531')  # 16 字节
def decrypt_chapter(b64_body: str) -> str:
    raw = base64.b64decode(b64_body)        # 整个 .txt 文件内容是 base64
    iv, payload = raw[:16], raw[16:]        # IV = 前 16 字节
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    dec = cipher.decrypt(payload)
    pad = dec[-1]                            # PKCS7 unpad
    dec = dec[:-pad]
    return dec.decode('utf-8')
```

**重要**：AES **仅用于 `book/download` 返回的 ZIP 内章节内容**。`chapter-list` 返回的是明文标题，**不涉及 AES**。

**ZIP 结构**（实测 book 1860026）：
- `book_download/01/18600266a4f307aa3fd4_2.zip`（8.6 MiB）
- 内含 1063 个文件，命名 `{chapter_id}.txt`（chapter_id **= chapter-list 返回的 `id` 字段**，一一对应）
- 每个文件整体是 base64，解 base64 后 [前16, 尾] = [IV, 密文]，AES-CBC 解出 UTF-8 中文

---

## 5. 替代路径评估（非 App API）

| 路径 | 完整目录？ | 备注 |
|---|---|---|
| Web 详情页 SSR HTML | ❌ 只露 ~13 个最新章 `/shuku/{short_id}/` 链接 | 实测 `/shuku/1860026/` 只出现 13 个章节 URL |
| Web SSR `__NUXT__` state | ❌ 未发现 `chapter_lists` / `allChapter` 等全目录字段 | 关键词扫描无命中 |
| Web `/api/...` 隐藏接口 | ❓ 未探到 | 七猫 Web 是 Nuxt SSR，目录数据不预取 |
| **结论** | — | **完整目录 = 必须 App API + 签名**，无 Web 替代 |

**额外坑点（实测）**：App API 返回的 `chapter_lists[].id`（如 `17231076120001`）**不能直接拼到 Web `/shuku/{id}/`**（404）。Web 用的是另一套短数字 chapter ID（如 `10330749`）。两套 ID 不互通。所以：

- **想要完整目录 + 全本正文**：必须走 App API（catalog + encrypted zip + AES），不能「目录走 API、正文走 Web」混搭。
- **只想要「最新 N 章」**：Web 详情页已经露 13 章，直接复用现有 `parse_content`。

---

## 实现建议（QimaoParser 增强）

### 值得做吗？

| 维度 | 评估 |
|---|---|
| 价值 | README 已标注「完整目录需 App API」是痛点；当前 `parse_catalog` 只取第 1 章；下载流程实际上只能下最新 1 章 — 价值高 |
| 复杂度 | 签名 + AES ≈ 50 行代码，无需新依赖（`hashlib` stdlib 即可签 chapter-list；AES 仅 `pycryptodome` 一个包，下载流程已经在 `requirements.txt` 里没有，但添加成本极低） |
| 维护成本 | 签名常量是公开开源项目验证过的，3 年内未变；七猫改签风险存在但可控（失效时 `code:44010120 验签失败` 会明确报错） |
| **结论** | **值得做，且 ponytail 友好**（最小代码：< 100 行解锁 1000+ 章下载） |

### API 范围（最小可用）

只做两件事就够「完整目录 + 全本下载」：
1. `get_full_catalog(book_id, fetch) -> list[(title, chapter_id)]` — 走 chapter-list
2. `download_full_content(book_id, fetch) -> dict[chapter_id, text]` — 走 download+AES

### 代码放哪（ponytail：最少文件）

```
novel_crawler/
├── sites/
│   └── qimao.py           # 现有 QimaoParser + 新增 get_full_catalog/download_full_content 方法
└── _qimao_appapi.py       # 新增小模块（仅签名+AES+两个 endpoint 调用，<100 行）
```

**理由**：
- 签名 + AES 是七猫专属魔法，**不通用**，不放 `base.py` 也不放新通用 util。
- 单独一个 `_qimao_appapi.py` 模块（下划线前缀=包私有），`QimaoParser` import 它即可。
- 不要在 `qimao.py` 里塞大段签名代码（会让 parser 文件臃杂）；但**也别**为了 1 个调用方搞 abstract API client 框架（YAGNI）。
- `db.py` 是 SQLite 持久化层，与 App API 无关，**不要放这里**。

### fetch 复用 vs 直连

现有 `DownloadEngine.fetch` 已支持 `headers=` 参数，可复用调用 App API。但注意：
- App API URL 已经带 `?sign=...`，不要让 engine 再额外加 query。
- App API 响应是 JSON 不是 HTML，engine.fetch 返回的是 `resp.text`（字符串），调用方自己 `json.loads`。
- 建议在 `_qimao_appapi.py` 里**直接用 `requests`**（与 engine 解耦，便于单测），不强行复用 engine。`requests` 已是项目依赖。

### parse_catalog 的角色

保留现有 `parse_catalog`（从 HTML 拿最新 1 章，用于「下载入口」触发的快速路径）。新增的 `get_full_catalog` 是**独立方法**，在用户明确要全本时调用。不要替换 `parse_catalog`（会破坏 web 下载入口）。

### 调用入口

`main.py` / `interactive.py` 在选择七猫书籍时增加一个 `--full` 开关（或交互问「完整目录?(y/N)」），走 `get_full_catalog` + `download_full_content`；否则维持现有 web 流程。**不要**默认走 App API（增加复杂度、签名可能某天失效）。

### 测试自检（ponytail 强制）

`_qimao_appapi.py` 末尾加 `if __name__ == "__main__":` 烟测块：
```python
# 真连网烟测：book 1860026
cat = get_full_catalog("1860026")
assert len(cat) > 100, f"catalog too short: {len(cat)}"
text = download_full_content("1860026")[cat[0][1]]
assert len(text) > 1000 and "卫渊" in text
print(f"OK: {len(cat)} chapters, ch1 {len(text)} chars")
```
无需框架/fixture — 签名挂了立即 fail。

---

## Caveats / 未深入

- **`get_chapter_content` 单章 API**：七猫 App 有单章明文内容 API，但路径未公开（试了 5 个变体均 `44010102 参数错误`，需要更多参数如 `sign` 之外的 `imei_ip` / `teeny_mode` / `timestamp`）。**当前实现路径（download zip + AES）已足够**，不追单章 API。
- **VIP 章节**：`is_vip=1` 参数实测对 book 1860026（免费书）无影响；对真正 VIP 书是否会返回加密更强的内容未测。建议生产中遇到 VIP 书时 fall back 到「Web 已免费章节 + 提示用户 VIP 部分跳过」。
- **签名失效风险**：`d3dGiJc651gSQ8w1` 是 2023+ 开源项目通用常量，七猫若封禁需改算法（可能升级到 HMAC-SHA256 或加 timestamp）。失效时 API 返回 `{"code":"44010120","message":"验签失败"}`，易检测。
- **频控**：实测同 IP 连发 5+ 次 App API 无拦截；但生产建议 1-2s 间隔。
- **app-version 池时效**：池内版本对应 2023-2024 客户端；2026 实测仍接受（七猫服务端未强制升级）。若某天要求新版，需抓新版客户端补 version 号。
- **`content_md5` 字段**：chapter-list 返回每章 md5，未用到（推测用于增量更新对比），本方案忽略。
