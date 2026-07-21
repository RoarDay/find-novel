---
name: find-novel
description: "自然语言找小说推荐。用户想找小说、描述阅读喜好（如『法师玄幻爽文』）、或要『类似《X》的书』时使用。聚合多站检索（纵横/起点/92yanqing/min-yuan 关键词搜，七猫/飞卢分类），Claude 读简介语义排序推荐 top-5，记住长期偏好。触发：找小说/推荐小说/类似某书/想看某类小说。"
---

# Find Novel（自然语言找小说推荐）

跨站检索 + Claude 语义推荐的找书工作流。**模型只在抉择点（意图理解、语义排序、反馈解读），检索/聚合交给代码（main.py CLI）**。少调用模型。

工作目录：`/Users/xinchao/work/mybook`（所有 `python main.py` 在此跑）。

## 工作流

### ①【模型】理解意图 + 读画像
- 读画像 memory：`/Users/xinchao/.claude/projects/-Users-xinchao-work-mybook/memory/novel-preferences.md`（题材偏好、雷点、风格）。
- 理解用户描述：抽**关键词**（「法师」「玄幻」）或**分类**（七猫/飞卢 catId）或**参考书**（「类似《诡秘之主》」→ 抽其特征）。
- 结合画像：偏好侧重、雷点规避。

### ③【代码】调 main.py CLI 拿候选（Bash 执行，json.loads 解析）

| 需求类型 | 命令 | 覆盖站 |
|----------|------|--------|
| 关键词（书名/题材） | `python main.py --search <词> --json` | 纵横/起点/92yanqing/min-yuan |
| 分类（七猫） | `python main.py --category 0-a-a --source qimao.com --json` | 七猫（cat1-cat2 可换） |
| 分类（飞卢） | `python main.py --category 44_69 --source faloo.com --json` | 飞卢（44=同人/69=动漫同人） |
| 排行兜底 | `python main.py --rank <type> --source <域名> --json` | 任意站 |

参考型（「类似《X》」）：先 `--search X` 拿 X 的简介/分类 → 抽特征 → 再按特征 search/category。

### ④【代码】聚合去重 + 补简介
- 合并候选，按 url 去重。
- 缺 blurb 的（七猫/飞卢 category 候选）：`python main.py --blurb <url1> <url2> ...`（限 top-K，K≈10）。

### ⑤【模型】语义排序 → top-5
- 读候选 blurb + 用户描述 + 画像，**语义匹配**排序。
- 不读全部 100+ 候选打分——先靠站内排序/热度筛到 top 候选，再精排 top-5。
- 每条想清「为什么推荐」（匹配了用户哪些点 + 画像偏好）。

### ⑥ 输出 + 反馈 + 下载
```
根据「<用户描述>」+ 你的偏好（<画像摘要>），推荐 top 5：

1. 《书名》[来源站] — <简介一句话>
   为什么推荐：<匹配点，如：法师主角+爽文节奏+非虐主>
2. ...
（输入编号：试读前20章 / 直接下载；或反馈：喜欢X / 不喜欢Y / 换一批）
```
- 反馈（喜欢/不喜欢/雷点）→ **更新画像 memory**（`novel-preferences.md`）：累积偏好，去重，雷点 ❌ 标注。
- 选号下载 → `python main.py <url>`（存 `novels/`）。

## 画像 memory 规则
- 文件：`/Users/xinchao/.claude/projects/-Users-xinchao-work-mybook/memory/novel-preferences.md`（user 类）。
- ① 读、⑥ 反馈写。保持简洁，一个偏好一行。
- `MEMORY.md` 有指针（首次创建时加）。

## 速查
- **飞卢 catId**：44=同人（69=动漫同人、68=都市同人）、97=轻小说。其他从 b.faloo.com 首页菜单枚举。
- **七猫分类**：`--category {channel}-{cat1}-{cat2}`，a=不限、0=男生。cat1/cat2 从首页 SSR categoryList。
- **七猫/飞卢无关键词 search**（走 category）。
- **七猫完整目录要 App API**（下载受限，主要作推荐源；试读仅最新章）。
- **前 20 章试读**：飞卢/纵横/起点/92yanqing/min-yuan 可。

## 边界
- 站点改版致 CLI 返回空 → 降级其它站/排行兜底，告知用户。
- 画像跑偏 → 用户口头纠正，更新 memory。
