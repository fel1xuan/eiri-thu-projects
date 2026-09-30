# 清华数据分析软件

基于 Python + PySide6 开发的本地科研数据处理桌面软件，用于海螺水泥碳排放数据处理流程。当前版本为 **1.0.0 / 詹宇轩1.0版**，支持单月内指定日期范围处理。

## 处理流程

**0号 日报提取与审核 → 1号 低频汇总 → 2号 秒级核算与异常检测 → 3号 15min 聚合 → 结果查看与图表分析**

0号结果的自动检查与人工审核相互独立。用户确认人工审核通过后，才能一键运行后续 1→2→3 流程。软件提供后台运行进度、运行记录、结果文件查看及分类图表分析。

## 技术栈

- Python 3.11、PySide6
- pandas、numpy、matplotlib
- openpyxl、xlrd、tqdm
- PyInstaller（可选打包工具，不是源码启动依赖）

## 安装与启动

在项目根目录创建虚拟环境，并安装运行依赖。

macOS / Linux：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Windows：

```bat
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

已激活虚拟环境时，也可直接运行 `python main.py`。程序打开本地桌面窗口，不需要浏览器服务。

`requirements-lock.txt` 保留已有 macOS arm64 打包环境的版本记录，不是跨平台通用锁文件；日常安装使用 `requirements.txt`。

## 数据与配置

首次启动后，在“项目配置”中选择自己的数据项目根目录、处理月份及输入文件。仓库不包含科研原始数据、用户配置或历史计算结果。

`config/default_config.json` 是空路径配置模板，`config/version.json` 保存版本信息。实际用户配置与日志保存在系统用户目录，由公共路径工具定位；不要将它们提交到 Git。

结果遵循数据项目内的标准目录体系：

- 0号：`1.原始数据/(3)低频数据/YYYYMM/`
- 1号：`1.原始数据/(3)低频数据/`
- 2号：`2.秒级核算数据/` 和 `3.秒级异常数据统计/`
- 3号：`4.15min核算数据/`

执行前核对输入、日期范围和覆盖风险，运行后在“结果查看”和“运行记录”中检查结果。

## 项目结构

```text
main.py             桌面程序入口
core/               业务计算与流程编排
ui/                 PySide6 桌面界面
utils/              配置、路径、日志、审核状态及图表工具
assets/             正式 Logo、图标和思维导图图片
config/             默认配置模板与版本信息
packaging/          PyInstaller 配置与打包测试说明
tests/              自动化测试
scripts/            开发辅助工具
```

`scripts/render_xmind_mindmaps.py` 是 macOS 字体环境下的可选资源制作工具，源码启动不依赖它；正式界面直接使用已提供的 PNG。

## 基础检查

在已激活的虚拟环境中执行：

```bash
python -m compileall main.py core ui utils tests
python -m unittest discover -s tests
python -m pip check
```

无显示器的测试环境可设置 `QT_QPA_PLATFORM=offscreen`。测试使用临时目录和测试数据，不应指向正式生产结果。

## 打包与仓库边界

`packaging/` 保留现有 PyInstaller spec。需要构建时单独安装 `pyinstaller`，并在目标操作系统验证；现有 Mac spec 不代表 Windows 发布包已验证。

仓库只保存代码、必要资源和文档。虚拟环境、`build/`、`dist/`、App、可执行文件、私人配置、日志和业务数据均由 `.gitignore` 排除。旧 Streamlit 原型不属于此项目，也不继续在这里维护。
