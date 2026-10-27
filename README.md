# 📚 HSK 4 级受控分级阅读与测评生成器

**Curriculum-Adaptive Reading & Exercise Generator (HSK 2.0 vs 3.0)**

本项目是一个面向国际中文教师的备课与测评原型系统。它基于 HSK 词汇大纲，在教师选定大纲版本、教学主题与目标词汇后，调用大模型自动生成受控分级阅读短文，并进一步生成高干扰效度的四选一阅读理解题（MCQ），形成“选词 -> 生成阅读 -> 合规度检测 -> 自动命题 -> 导出教案”的完整流程。

## 在线入口

| 入口 | 地址 | 用途 |
| --- | --- | --- |
| 成品展示页（壳页） | `https://zhangxykxa.github.io/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator/` | 面向评审/被试的正式入口。自建页头 + iframe 内嵌 Streamlit，隐藏一切平台痕迹 |
| Streamlit 应用（原页面） | `https://hsk-level-4-controlled-graded-reading-and-assessment-generator.streamlit.app/` | 保留全部原生功能的源站，便于排查问题 |

两个入口跑的是同一份 `app.py`。壳页通过 `?embed=true&hsk_shell=1` 进入「嵌入模式」，注入一套专用的紧凑样式；原页面不携带该参数，走原生样式。

## 主要功能

- **双轨大纲切换**：支持 HSK 2.0（1,200 词）与 HSK 3.0（2,000 词）两套 Level 4 词表。
- **目标词锁定**：按教学主题随机抽取 HSK 4 级目标词，支持 `Reshuffle` 重锁。
- **CTG 受控阅读生成**：按主题、字数与目标词白名单生成 HSK 4 级分级阅读。
- **AQG 自动命题**：为生成文章产出 1–2 道四选一阅读理解题，要求干扰项对齐，并在解析中标注干扰项类型（词性干扰 / 语意合理干扰 / 原词干扰 / 形近干扰）。
- **选项与答案随机化**：解析后对 A/B/C/D 做确定性洗牌，并把答案键均匀分散，避免正确答案长期固定在 A。
- **合规度检测报告**：统计总字数、大纲覆盖率、核心词融入率、语境重现率与疑似超纲词。
- **超纲词高亮与补全**：对疑似超纲词做正文高亮，并调用模型补全拼音、词性和英文释义。
- **教案导出**：一键导出 Markdown 教案，含生成时间（分钟级）、生成引擎、阅读文本、核心词、MCQ 与答案解析。
- **悬浮快捷工具栏**：右下角常驻「回到顶部」+「一键导出教案」。
- **专家评估闭环**：侧边栏与壳页顶栏均提供专家评估问卷入口。
- **去平台化外壳**：GitHub Pages 自建页头 + iframe 嵌入，访客看不到 Streamlit 工具栏与 GitHub 外链。
- **定时保活**：GitHub Actions 每 2 小时用真实无头浏览器访问一次应用（必要时自动点击唤醒），避免免费层休眠导致的首次访问白屏。

## 技术栈

- **前端框架**：Streamlit
- **语言**：Python 3.9+（开发验证环境为 3.13.2）
- **数据处理**：pandas
- **模型调用**：openai Python SDK（兼容 OpenAI-style API）
- **部署方式**：
  - Streamlit Community Cloud 承载应用
  - GitHub Pages 承载外壳展示页 `docs/index.html`
  - GitHub Actions 定时保活（`.github/workflows/keepalive.yml`）

## 界面与样式约定

`app.py` 顶部的 CSS 拆成三段，按访问入口分别注入：

| 样式块 | 生效范围 | 内容 |
| --- | --- | --- |
| `_common_css` | 两个入口都生效 | 隐藏 `#MainMenu` / `footer` / 装饰条 / GitHub 外链；标题字号层级（主标题 `2.2rem`，二级标题 `1.58rem`）；KPI 字号；悬浮工具栏；侧边栏问卷按钮 |
| `_embed_css` | 仅壳页（嵌入模式） | 压平 Streamlit header；侧边栏宽度锁定 `21rem`；竖向把手抽屉（`28px × 240px`，固定在视口中线）；侧边栏上下留白 `2rem`；收起态释放主区空间；禁用原生缩放手柄 |
| `_raw_css` | 仅原页面 | 把悬浮工具栏上抬到 `bottom: 84px`，避开 Streamlit 原生管理按钮 |

嵌入模式判定：壳页 iframe 的 src 带 `hsk_shell=1`。**注意** `?embed=true` 会被 Streamlit 内部消费掉，`st.query_params` 读不到，所以必须用自定义参数。

## 项目特点

- 不依赖重量级中文分词库，正文分析复用项目内的 HSK 词表最大匹配逻辑。
- 兼容 Windows 常见 CSV 编码，自动尝试 `utf-8-sig / gb18030 / gbk`。
- MCQ JSON 解析具备 Markdown 围栏清洗与结构校验兜底。
- 导出教案使用 UTF-8 BOM 编码，便于直接复制进 Word / OneNote / Notion。
- 选项洗牌使用 `hashlib.md5` 派生种子，rerun 时不会抖动。

## 目录结构

```text
.
├── app.py                                      # 主应用（UI + LLM 调用 + 合规度分析 + 导出）
├── docs/
│   ├── index.html                              # GitHub Pages 外壳页
│   └── .nojekyll
├── .github/
│   ├── scripts/
│   │   └── keepalive.py                        # 保活脚本（Playwright 真实浏览器访问）
│   └── workflows/
│       └── keepalive.yml                       # 定时保活工作流
├── requirements.txt                            # 依赖清单
├── diagnose_api_keys.py                        # API Key 诊断脚本
├── HSK 2.0 Level 4 vocabulary 1200.csv         # HSK 2.0 词表
├── HSK 3.0 Level 4 vocabulary 2000.csv         # HSK 3.0 词表
├── .streamlit/
│   └── config.toml                             # Streamlit 前端配置
├── README.md
└── PROJECT_HANDOVER.md                         # 交接文档（本地维护）
```

## 支持的模型服务商

当前界面内置以下预设：

| 服务商 | Base URL | 模型示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| SiliconFlow（国际站） | `https://api.siliconflow.com/v1` | `deepseek-ai/DeepSeek-V3` |
| 自定义 | 用户手动填写 | 任意 OpenAI 兼容模型 |

> 注意：项目已移除 SiliconFlow 国内站 `.cn` 预设，统一使用国际站 `siliconflow.com`。

## 本地运行

### 1. 克隆仓库

```bash
git clone https://github.com/zhangxykxa/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator.git
cd HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator
```

### 2. 创建虚拟环境

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 API Key

可选三种方式：

1. **侧边栏直接输入**
2. **环境变量**
3. **`.streamlit/secrets.toml`**

示例：

```toml
DEFAULT_PROVIDER = "DeepSeek"
DEEPSEEK_API_KEY = "sk-..."
SILICONFLOW_API_KEY = "sk-..."
```

### 5. 启动应用

```bash
streamlit run app.py
```

> **当前开发机的实际情况**：Python 装在 `C:\Users\ZhangXiao\python-sdk\python3.13.2`，已加入用户 PATH；但 `Scripts` 目录不在 PATH 中，所以 `pip` / `streamlit` 命令直接敲不到，需改用 `python -m pip` / `python -m streamlit`。仅需语法自检时可以跑 `python -m py_compile app.py`，无需安装任何依赖。

## 定时保活

Streamlit Community Cloud 免费层在**闲置 12 小时**后休眠（页面显示 `Zzzz`）。关键在于：休眠后**任何 HTTP 请求都打不醒它**——平台只把「执行了 JS 并建立 WebSocket 会话的浏览器访问」算作活动，`curl`、`UptimeRobot`、空提交都不算。所以保活必须由真实浏览器完成。

`.github/workflows/keepalive.yml` 每 2 小时跑一次 `.github/scripts/keepalive.py`：用 Playwright 无头 Chromium 打开应用页，若出现 `Yes, get this app back up!` 插页则自动点击唤醒，跨 frame 确认应用容器已渲染，最后复验 `/~/+/_stcore/health` 是否为 `ok`。

路径归属备忘（决定了「探测哪条路径才有意义」）：

| 路径 | 实际归属 | 能否反映应用状态 |
| --- | --- | --- |
| `/` | 平台 nginx 静态 SPA 外壳（约 9782 字节 HTML） | ❌ 不经过应用容器 |
| `/_stcore/health` | 同 被 nginx 兜底路由 | ❌ 不经过应用容器 |
| `/healthz` | nginx 边缘健康检查 | ❌ 与应用无关，永远 200 |
| `/~/+/` | 应用容器自身的 `index.html`（6467 字节） | ✅ |
| `/~/+/_stcore/health` | 应用运行时返回纯文本 `ok`，休眠时返回 400 | ✅（工作流据此判断存活） |

- 手动验证：仓库 `Actions` → `Streamlit Keep-Alive` → `Run workflow`
- 注意 1：GitHub 的 `schedule` 是 best-effort，高峰时段会被排队延迟数小时，故用 2 小时一次对冲 12 小时阈值
- 注意 2：GitHub 在仓库连续 60 天无提交后会停用定时工作流，有新 commit 即自动恢复
- 注意 3：应用本体被平台嵌在下一层的 `/~/+/` iframe 中，写自动化检查时必须跨 frame 查找，只看主 frame 永远找不到
- 注意 4：纯 HTTP 探测曾造成「假成功」——18 次 `success` 而应用仍在休眠，排查时务必以 `/~/+/_stcore/health` 的实际返回为准

## 使用流程

1. 在左侧选择大纲版本、主题、目标字数与目标词数量。
2. 系统自动锁定一组 HSK 4 级目标词。
3. 点击“生成 HSK 4 级阅读”，产出正文并自动生成合规度分析报告。
4. 点击“Generate MCQ”，生成配套四选一阅读理解题。
5. 提交答案查看解析。
6. 在页面底部或右下角悬浮工具栏导出完整教案。

## 合规度指标说明

- **总字数**：仅统计正文汉字，不含标点、空格、数字与“核心词回顾”列表。
- **大纲覆盖率**：参考 Laufer (1989) 的 95% 词汇覆盖率阈值。
- **核心词融入**：目标词命中数 / 目标词总数。
- **语境重现率**：目标词在正文中总出现次数 ÷ 目标词个数，用于观察词汇复现密度。
- **疑似超纲词**：按 HSK 词表最大匹配识别的非大纲词片段，仅作教学提示。

## 常见问题

| 问题 | 说明 |
| --- | --- |
| `401 AuthenticationError` | API Key 与服务商不匹配，或填错服务商预设。 |
| `402 Insufficient Balance` | 对应服务商账户余额不足。 |
| MCQ JSON 解析失败 | 模型输出了额外文本或代码围栏，系统会先自动清洗；若仍失败，请重试。 |
| CSV 读取报错 | 项目已内置多编码探测，若仍失败请确认词表文件名与仓库中的默认文件一致。 |
| 壳页显示为原生样式（工具栏冒出来） | iframe 的 src 丢了 `hsk_shell=1`，检查 `docs/index.html`。 |
| 首次打开长时间白屏 | Streamlit Cloud 免费层冷启动；壳页已加冷启动遮罩（最短展示 7 秒），保活工作流会尽量避免休眠。 |
| 原页面右下角悬浮按钮位置怪 | `_raw_css` 已把 `bottom` 抬到 `84px` 避开原生管理按钮；若 Streamlit 改版可再调。 |

## License

MIT
