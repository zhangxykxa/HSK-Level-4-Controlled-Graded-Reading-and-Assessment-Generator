# 📚 HSK 4 级受控分级阅读与测评生成器
## Curriculum-Adaptive Reading & Exercise Generator (HSK 2.0 vs. 3.0)

[![Live Demo](https://img.shields.io/badge/Demo-GitHub%20Pages-blue)](https://zhangxykxa.github.io/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator/)
[![Streamlit App](https://img.shields.io/badge/Streamlit-App-FF4B4B)](https://hsk-level-4-controlled-graded-reading-and-assessment-generator.streamlit.app/)

---

## 1. 项目简介 | Project Overview

本项目是一个面向国际中文教师的 AI 辅助备课与测评原型系统（LCS5026 顶石研究项目）。系统基于《国际中文教育中文水平等级标准》（GF 0025-2021）与《HSK 考试大纲》，支持在 **HSK 2.0（1,200 词）** 与 **HSK 3.0（2,000 词）** 双轨词汇大纲间一键切换。教师选定大纲版本、教学主题与目标词汇后，系统调用大语言模型自动生成受控分级阅读短文，并产出具备合理迷惑度的四选一阅读理解题（MCQ），形成"选词锁定 -> 受控生成 -> 词汇合规检测 -> 自动命题 -> 教案导出"的完整备课闭环。

This project is an AI-assisted instructional design and assessment prototype developed for international Chinese language teachers (LCS5026 Capstone Project). Grounded in the *Chinese Proficiency Grading Standards* (GF 0025-2021) and the *HSK Syllabus*, the system enables seamless switching between dual-track HSK Level 4 lexicons: **HSK 2.0 (1,200 words)** and **HSK 3.0 (2,000 words)**. Once an instructor selects the syllabus version, pedagogical topic, and target vocabulary, the system leverages Large Language Models (LLMs) to generate curriculum-controlled graded reading passages and distractor-aligned multiple-choice questions (MCQs), establishing an end-to-end workflow from vocabulary locking and lexical compliance auditing to automated item generation and lesson handout export.

---

## 2. 在线演示入口 | Live Access

* **成品展示页（包装外壳入口 / Embedded Shell View）**：
  https://zhangxykxa.github.io/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator/
* **原生应用源站（Streamlit Cloud Direct App）**：
  https://hsk-level-4-controlled-graded-reading-and-assessment-generator.streamlit.app/

---

## 3. 核心教学与技术功能 | Core Pedagogical & Technical Features

* **双轨大纲自适应（Dual-Syllabus Adaptation）**：支持 HSK 2.0（1,200 词）与 HSK 3.0（2,000 词）两套 Level 4 累计词库切换，并按八大语义功能主题随机抽取与锁定核心目标词。
* **受控文本生成（Controlled Text Generation, CTG）**：依据选定主题、目标字数与大纲词汇白名单生成适切的中级阅读短文。
* **词汇合规度即时审计（Lexical Compliance Auditing）**：内置基于词表最大正向匹配（FMM）的纯 Python 分词器，自动测算大纲词汇覆盖率（参考 Laufer 95% 阈值）、核心词融入率与语境重现率，并对疑似超纲词进行高亮标注及词性/释义补全。
* **词性对齐自动命题（Automatic Question Generation, AQG）**：生成 1–2 道四选一阅读理解题，内置干扰项逻辑约束（词性对齐、语意合理干扰等）与确定性选项洗牌机制，附带完整解析。
* **一键导出教案（One-Click Handout Export）**：支持将阅读文本、目标词表、选择题及答案解析导出为 UTF-8 编码的 Markdown 教学讲义（兼容 Word 直接编辑）。

---

## 4. 目录结构 | Repository Structure

```text
.
├── app.py                                  # 主应用程序（UI、LLM 调用、FMM 词汇合规检测、教案导出）
├── HSK 2.0 Level 4 vocabulary 1200.csv     # 清洗与标注后的 HSK 2.0 四级词库（1,200 词）
├── HSK 3.0 Level 4 vocabulary 2000.csv     # 清洗与标注后的 HSK 3.0 四级词库（2,000 词）
├── docs/                                   # GitHub Pages 展示外壳页面（index.html）
├── .github/                                # 自动化保活工作流（Playwright 无头浏览器探测）
├── .streamlit/                             # Streamlit 前端界面配置文件
├── diagnose_api_keys.py                    # API 密钥与服务商连通性诊断脚本
├── requirements.txt                        # Python 依赖包清单
└── README.md                               # 项目说明文档
```

---

## 5. 本地部署运行 | Local Installation & Execution

**环境要求 / Prerequisites**：Python 3.9+（兼容 OpenAI SDK 格式的 API Key，如 DeepSeek 或 SiliconFlow）。

```bash
# 1. 克隆仓库 / Clone repository
git clone https://github.com/zhangxykxa/HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator.git
cd HSK-Level-4-Controlled-Graded-Reading-and-Assessment-Generator

# 2. 安装依赖 / Install dependencies
pip install -r requirements.txt

# 3. 启动应用 / Run Streamlit application
streamlit run app.py
```
> **提示**：启动后可直接在应用左侧边栏输入 API Key，或通过 `.streamlit/secrets.toml` 配置环境变量。

---

## 6. 学术规范与 AI 辅助声明 | Academic Integrity & AI Disclosure

* 本研究原型系统的教学框架设计、双轨词库筛选标准、提示词工程（Prompt Engineering）策略及评估指标均由研究者独立制定与验证。部分前端样式代码、辅助脚本及技术文档在生成式 AI 编程工具（如 Gemini / AI Coding Assistants）的辅助下编写，并经由研究者完成全面测试与人工校验，符合 LCS5026 顶石项目学术诚信与透明性规范。
* The pedagogical architecture, dual-syllabus lexical criteria, prompt engineering strategies, and evaluation metrics of this prototype were independently designed and validated by the student researcher. Portions of the boilerplate UI code, utility scripts, and technical documentation were drafted with the assistance of generative AI coding tools (e.g., Gemini and AI coding assistants) and were thoroughly audited, tested, and verified by the researcher in accordance with the academic integrity and transparency guidelines of the LCS5026 Capstone Project.

---

## License
MIT
