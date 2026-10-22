# 📚 HSK 4 级受控分级阅读与测评生成器

**Curriculum-Adaptive Reading & Exercise Generator (HSK 2.0 vs 3.0)**

本项目是一个面向国际中文教师的备课与测评原型系统。它基于 HSK 词汇大纲，在教师选定大纲版本、教学主题与目标词汇后，调用大模型自动生成受控分级阅读短文，并进一步生成高干扰效度的四选一阅读理解题（MCQ），形成“选词 -> 生成阅读 -> 合规度检测 -> 自动命题 -> 导出教案”的完整流程。

## 在线入口

- 成品展示页：`https://zhangxykxa.github.io/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator/`
- Streamlit 应用：`https://hsk-level-4-controlled-graded-reading-and-assessment-generator.streamlit.app/`

## 主要功能

- **双轨大纲切换**：支持 HSK 2.0（1,200 词）与 HSK 3.0（2,000 词）两套 Level 4 词表。
- **目标词锁定**：按教学主题随机抽取 HSK 4 级目标词，支持 `Reshuffle` 重锁。
- **CTG 受控阅读生成**：按主题、字数与目标词白名单生成 HSK 4 级分级阅读。
- **AQG 自动命题**：为生成文章产出 1–2 道四选一阅读理解题，并要求干扰项对齐。
- **合规度检测报告**：统计总字数、大纲覆盖率、核心词融入率、语境重现率与疑似超纲词。
- **超纲词高亮与补全**：对疑似超纲词做正文高亮，并尝试补全拼音、词性和英文释义。
- **教案导出**：一键导出 Markdown 教案，包含生成时间、生成引擎、阅读文本、核心词、MCQ 与答案解析。
- **专家评估闭环**：侧边栏与壳页面均提供专家评估问卷入口。

## 技术栈

- **前端框架**：Streamlit
- **语言**：Python 3.9+
- **数据处理**：pandas
- **模型调用**：openai Python SDK（兼容 OpenAI-style API）
- **部署方式**：
  - Streamlit Community Cloud 承载应用
  - GitHub Pages 承载外壳展示页 `docs/index.html`

## 项目特点

- 不依赖重量级中文分词库，正文分析复用项目内的 HSK 词表最大匹配逻辑。
- 兼容 Windows 常见 CSV 编码，自动尝试 `utf-8-sig / gb18030 / gbk`。
- MCQ JSON 解析具备 Markdown 围栏清洗与结构校验兜底。
- 导出教案使用 UTF-8 BOM 编码，便于直接复制进 Word / OneNote / Notion。

## 目录结构

```text
.
├── app.py                                      # 主应用（UI + LLM 调用 + 合规度分析 + 导出）
├── docs/
│   ├── index.html                              # GitHub Pages 外壳页
│   └── .nojekyll
├── requirements.txt                            # 依赖清单
├── HSK 2.0 Level 4 vocabulary 1200.csv         # HSK 2.0 词表
├── HSK 3.0 Level 4 vocabulary 2000.csv         # HSK 3.0 词表
├── .streamlit/
│   └── config.toml                             # Streamlit 前端配置
├── README.md
└── PROJECT_HANDOVER.md
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

## License

MIT
