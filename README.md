# 多站小说爬虫 + 自然语言找书

一个 Python 多站小说爬虫，支持按目录页 URL 下载、按书名聚合搜索，以及**用自然语言描述喜好找书**（Claude 语义推荐 skill）。

## 功能

- **多站下载**：给目录页 URL，并发下载全本，合并为 TXT（存 `novels/`）。
- **关键词搜索**：按书名/题材聚合搜所有站，交互式选号下载。
- **自然语言找书**（`/find-novel` skill）：用一句话描述需求（「法师玄幻爽文」「类似《诡秘之主》」），Claude 跨站检索 + 读简介语义排序推荐 top-5，并记住你的长期偏好。
- **统一 JSON CLI**：供程序/Claude 调用的非交互出口（搜索/分类/排行/简介）。

## 支持站点

| 站 | 域名 | 检索能力 | 下载 |
|----|------|----------|------|
| 就爱言情 | 92yanqing.com | 关键词搜（带简介） | 全本 |
| 小原文学 | min-yuan.com | 关键词搜 | 全本 |
| 纵横中文网 | zongheng.com | 关键词搜（JSON API，带简介） | 全本 |
| 起点中文网 | qidian.com | 关键词搜（移动站，带简介） | 前 20 章（VIP 锁） |
| 七猫小说 | qimao.com | 分类筛选 + 相似推荐 | 最新章（完整目录需 App API） |
| 飞卢小说 | faloo.com | 分类筛选（同人 catId 强） | 前 20 章 |

> 新增站点只需在 `novel_crawler/sites/` 加一个 `BaseParser` 子类，注册中心自动加载。

## 安装

```bash
git clone <repo>
cd mybook
pip install -r requirements.txt
```

依赖：`requests`、`beautifulsoup4`、`lxml`。Python ≥ 3.10。

## 用法

### 1. 直接下载（给目录页 URL）

```bash
python main.py https://www.92yanqing.com/read/36979/
python main.py https://www.92yanqing.com/read/36979/ --workers 10 --start 1 --end 50
```

### 2. 关键词搜索（交互式选书）

```bash
python main.py --search 斗破苍穹
# 列出各站匹配结果 → 输入编号下载
```

### 3. 自然语言找书（Claude skill）

见下方 [find-novel Skill](#find-novel-skill-安装与使用)。

### CLI 完整参数

```
python main.py <url>                          # 直接下载
python main.py --search <书名>                 # 交互搜索选书
python main.py --search <词> --json            # 非交互 JSON 候选（给程序/Claude）
python main.py --blurb <url> [<url>...]        # 批量取详情页简介 JSON
python main.py --category <cat> --source <域名> --json   # 单站分类 JSON
python main.py --rank <type> --source <域名> --json      # 单站排行 JSON

选项：--workers N    并发线程数（默认 8）
      --start/--end  章节范围（从 1 开始）
      --output NAME  自定义输出文件名（默认存 novels/<书名>.txt）
```

## find-novel Skill 安装与使用

`find-novel` 是 Claude Code 的 skill：**检索/聚合由本项目的 `main.py` CLI 完成，语义理解与排序由 Claude 完成**（模型只在意图理解、排序、反馈抉择点；少调用模型）。

### 前提

1. 安装 [Claude Code](https://claude.ai/code)（CLI / 桌面 / IDE 插件均可）。
2. 装好本项目依赖（见上「安装」）—— skill 通过 `python main.py` 调用爬虫。

### 安装 skill

skill **源文件在仓库的 `skills/` 目录**（入 git），`.claude/` 不上传（gitignore）。clone 后跑安装脚本，把 skill 链接到本地 `.claude/skills/`：

```bash
./install_skills.sh
# 为每个 skill 建 symlink（单一源，改 skills/ 自动反映；系统不支持 symlink 则拷贝）
```

然后在本项目目录启动 Claude Code 即可用：
```bash
claude
# 输入：/find-novel 想看法师玄幻爽文
```

- **全局可用**（任意项目下都能调）：`cp -r skills/find-novel ~/.claude/skills/`
- **手动安装**（不用脚本）：`mkdir -p .claude/skills && ln -s ../../skills/find-novel .claude/skills/find-novel`
- **更新 skill**：直接改 `skills/find-novel/SKILL.md`（symlink 自动反映；拷贝安装的需重跑 `install_skills.sh`）

### 使用

在 Claude Code 里输入 `/find-novel` + 你的需求：

```
/find-novel 想看主角是法师的玄幻爽文，不虐
/find-novel 类似《诡秘之主》的
/find-novel 来本西游题材的系统爽文
```

Claude 会：
1. 读你的阅读偏好画像 → 理解需求，抽关键词/分类；
2. 跨站调 `main.py` 检索（关键词搜 / 分类 / 排行）+ 补简介；
3. 读简介语义排序，推荐 top-5，每条附「为什么推荐」；
4. 你**选号下载**（存 `novels/`）或**反馈**（喜欢/不喜欢/雷点）。

### 偏好画像

你的长期阅读偏好存在 `~/.claude/projects/<本项目>/memory/novel-preferences.md`，**跨 session 持久**。反馈会增量更新画像，下次推荐更准。首次使用为空，随交互沉淀。

## 项目结构

```
mybook/
├── main.py                      # 入口（下载/搜索/JSON CLI）
├── novel_crawler/
│   ├── base.py                  # BaseParser + SearchResult
│   ├── engine.py                # HTTP/重试/并发/写入（UA 覆盖 + 编码修正）
│   ├── registry.py              # 按域名自动匹配 parser
│   └── sites/                   # 各站 parser（新增站点加这里）
│       ├── yanqing92.py  min_yuan.py
│       ├── zongheng.py   qidian.py
│       └── qimao.py      faloo.py
├── novels/                      # 下载产物（已 gitignore）
├── .claude/skills/find-novel/   # 自然语言找书 skill
└── requirements.txt
```

## 已知限制

- 七猫完整目录需 App API 签名 → 下载受限（主要作推荐源，试读仅最新章）。
- 起点/飞卢 VIP 章节 → 仅前若干章免费试读。
- 番茄小说暂未接入（PUA 字体解密 + 搜索 XHR，计划第二批）。

## 许可

仅供学习交流，请遵守各站点 robots/服务条款，勿用于商业或大规模抓取。
