# 发版流程（PyPI）

> `novel-crawler` 通过 `git tag vX.Y.Z` 触发 `.github/workflows/publish.yml` 自动构建并上传 PyPI。

## 一次性配置

1. 注册 [PyPI](https://pypi.org) 账号；首次发版需先在 PyPI 手动建项目（首次 upload 会自动建）。
2. 生成 API token：PyPI → Account settings → API tokens，scope 选 "Entire account" 或指定项目 `novel-crawler`。
3. 在 GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret：
   - Name: `PYPI_API_TOKEN`
   - Value: 上一步的 token（含 `pypi-` 前缀）。

## 每次发版

```bash
# 1. 确认主干绿
python3 -m pytest && ruff check novel_crawler/ tests/ && mypy novel_crawler/

# 2. bump 版本（novel_crawler/__init__.py 的 __version__）
#    语义化：不兼容/大功能 → 升主；新增功能 → 升次；修复 → 升补丁。

# 3. 提交 + 打 tag + 推送
git add -A && git commit -m "release vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

推送 tag 后，GitHub Actions 会：
- `python -m build` 生成 `dist/*.{tar.gz,whl}`
- `twine check` 校验元数据
- `twine upload --skip-existing` 上传 PyPI

在 Actions 页确认任务绿；几分钟内 `pip install novel-crawler==X.Y.Z` 即可装。

## 校验本地打包（不发版）

```bash
pip install build twine
python -m build
python -m twine check dist/*
```

## 回滚

PyPI 不允许重新上传同版本号。发坏的版本：bump 一个补丁号重发；yank 旧版
（`pip index` 不再默认选中）：`pypi --yank novel-crawler X.Y.Z`（网页操作）。
