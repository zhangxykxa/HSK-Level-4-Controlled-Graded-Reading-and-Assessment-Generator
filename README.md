# 📚 HSK 4 级受控分级阅读与测评生成器

**Curriculum-Adaptive Reading & Exercise Generator (HSK 2.0 vs 3.0)**

一个基于 HSK 词汇大纲的语言教师备课工具。根据教师选择的大纲版本（HSK 2.0 / 3.0）、教学主题与核心词汇，调用大模型自动生成受控分级阅读材料，并配套生成四选一阅读理解单项选择题（MCQ），实现"阅读材料生成 → 测评题目生成 → 交互式答题与解析"的完整教学闭环。

---

## ✨ 核心功能

| 模块 | 功能 |
|------|------|
| **双轨大纲切换** | 一键切换 HSK 2.0（1,200 词）与 HSK 3.0（2,000 词）词汇大纲 |
| **词汇锁定** | 按教学主题 + HSK 4 级随机筛选目标词汇，支持重新随机锁定（Reshuffle） |
| **分级阅读生成** | 将大纲、主题、字数限制与核心词汇注入 System Prompt，调用大模型流式生成受控短文 |
| **MCQ 出题** | 基于生成文章与目标词汇，二次调用大模型出 1–2 道四选一阅读理解题，干扰项具备高迷惑性 |
| **交互式答题** | `st.radio` 渲染选项，提交后即时判对错、展示解析与得分 |

---

## 🛠️ 技术栈

- **前端/UI**：[Streamlit](https://streamlit.io/) — Python Web 应用框架
- **数据处理**：[Pandas](https://pandas.pydata.org/) — CSV 词汇表读取与筛选
- **大模型调用**：[OpenAI Python SDK](https://github.com/openai/openai-python) — 兼容 OpenAI / DeepSeek / SiliconFlow 等服务商

---

## 📋 环境要求

- **Python** ≥ 3.10（使用了 `int | None` 类型注解语法）
- **操作系统**：Windows / macOS / Linux 均可

---

## 🚀 本地运行指引

### 1. 克隆仓库

```bash
git clone https://github.com/zhangxykxa/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator.git
cd HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator
```

### 2. 创建虚拟环境（推荐）

**Windows (PowerShell)：**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux：**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

> 依赖列表见 [`requirements.txt`](./requirements.txt)，包含 streamlit、pandas、openai 三个包。

### 4. 配置大模型 API Key（三选一）

本工具兼容所有 OpenAI 兼容端点，以下任选其一：

#### 方式 A：侧边栏直接输入（推荐试用）

启动应用后，在左侧边栏的「🤖 大模型 API 配置」区域填写 API Key、Base URL 和模型名。

#### 方式 B：环境变量

```bash
# Windows (PowerShell)
$env:OPENAI_API_KEY = "sk-your-api-key"
$env:OPENAI_BASE_URL = "https://api.deepseek.com"   # 可选，留空用 OpenAI 官方
$env:OPENAI_MODEL = "deepseek-chat"                  # 可选

# macOS / Linux
export OPENAI_API_KEY="sk-your-api-key"
export OPENAI_BASE_URL="https://api.deepseek.com"
export OPENAI_MODEL="deepseek-chat"
```

#### 方式 C：Streamlit Secrets 文件

在项目根目录创建 `.streamlit/secrets.toml`：

```toml
OPENAI_API_KEY = "sk-your-api-key"
OPENAI_BASE_URL = "https://api.deepseek.com"
OPENAI_MODEL = "deepseek-chat"
```

#### 支持的服务商预设

| 服务商 | Base URL | 模型示例 |
|--------|----------|----------|
| OpenAI (官方) | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek (深度求索) | `https://api.deepseek.com` | `deepseek-chat` |
| SiliconFlow (硅基流动) | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |

### 5. 启动应用

```bash
streamlit run app.py
```

浏览器将自动打开 `http://localhost:8501`。

---

## 📖 使用流程

```
侧边栏选择大纲版本 & 主题 & 字数 & 核心词数量
            │
            ▼
   📌 系统锁定 HSK 4 级目标词汇（卡片展示 + 可下载 CSV）
            │
     ┌──────┴──────┐
     ▼             ▼
  左侧栏          右侧栏
  📝 一键        ❓ 一键
  生成文章       出题(MCQ)
     │             │
     │   文章+词汇  │
     └──────►──────┤
                   ▼
            st.radio 交互答题
                   │
                   ▼
            ✅ 提交答案 → 判对错 + 解析 + 得分
```

1. 在左侧边栏配置教学参数（大纲版本、主题、字数、核心词数量）
2. 点击 **🚀 一键生成 HSK 4 级阅读**，流式生成分级阅读短文
3. 文章生成后，在右侧点击 **❓ 一键出题**，大模型自动生成 1–2 道 MCQ
4. 通过 `st.radio` 选择答案，点击 **✅ 提交答案并查看解析** 查看对错与详细解析

---

## 📂 项目结构

```
.
├── app.py                                      # 主应用（UI + 大模型调用 + MCQ 生成）
├── requirements.txt                            # Python 依赖
├── HSK 2.0 Level 4 vocabulary 1200.csv         # HSK 2.0 大纲词汇表
├── HSK 3.0 Level 4 vocabulary 2000.csv         # HSK 3.0 大纲词汇表
├── .gitignore
└── README.md
```

---

## ⚠️ 常见问题

| 问题 | 解决方案 |
|------|----------|
| **HTTP 401 鉴权失败** | API Key 与服务商不匹配，或 Key 夹带了空格/`Bearer `前缀（已自动清洗，若仍失败请重新复制） |
| **HTTP 402 余额不足** | 前往对应服务商控制台充值，或切换到 SiliconFlow 免费模型（`Qwen/Qwen2.5-7B-Instruct`） |
| **HTTP 429 限流** | 请求过于频繁，稍候重试 |
| **CSV 编码错误** | 已内置 UTF-8 / GB18030 自动探测，一般无需手动处理 |
| **MCQ JSON 解析失败** | 大模型返回格式异常，重试即可；可在界面展开「查看原始返回内容」排查 |

---

## 📄 License

MIT
