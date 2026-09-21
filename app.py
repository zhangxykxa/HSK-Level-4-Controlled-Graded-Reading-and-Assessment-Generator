import hashlib
import os
from pathlib import Path

import streamlit as st
import pandas as pd
import openai

# 1. 页面基本配置
st.set_page_config(page_title="HSK 4 Graded Material Generator", layout="wide")

st.title("📚 HSK 4 级受控分级阅读与测评生成器")
st.subheader("Curriculum-Adaptive Reading & Exercise Generator (HSK 2.0 vs 3.0)")
st.write("---")

# ============================================================================
# 词汇表配置与核心函数
# ============================================================================

# 大纲版本（侧边栏标签）-> 对应 CSV 文件名
VOCAB_FILES = {
    "HSK 2.0 经典版 (1,200词)": "HSK 2.0 Level 4 vocabulary 1200.csv",
    "HSK 3.0 新课标 (2,000词)": "HSK 3.0 Level 4 vocabulary 2000.csv",
}
# app.py 所在目录即仓库根目录，CSV 文件存放于此
REPO_ROOT = Path(__file__).resolve().parent
# 仅锁定 HSK 4 级目标词汇（CSV 中含 1~4 级，需按级别筛选）
TARGET_LEVEL_KEYWORD = "Level 4"


def _map_topic(topic_label: str) -> str:
    """将侧边栏主题标签（含英文注释）映射为 CSV 中的 Topic 值（纯中文）。

    例：'职场与教育 (Work & Education)' -> '职场与教育'
    """
    return topic_label.split(" (")[0].strip()


def _read_csv_robust(path: Path) -> pd.DataFrame:
    """自动探测编码读取 CSV，兼容 UTF-8 与 GBK/GB18030（Windows 导出常见）。"""
    for enc in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    # 兜底：忽略无法解码的字节
    return pd.read_csv(path, encoding="gb18030", errors="replace")


@st.cache_data(show_spinner="正在加载词汇表…")
def load_vocab(syllabus_version: str) -> pd.DataFrame:
    """缓存数据加载函数：根据侧边栏选择的 HSK 大纲版本动态读取对应 CSV。

    使用 ``@st.cache_data`` 装饰，Streamlit 以 ``syllabus_version`` 为键做结果缓存——
    同一大纲版本在一次会话中只会真正读取一次磁盘文件，切换版本时自动加载
    另一份词库而不会重复 IO。

    Args:
        syllabus_version: 侧边栏选择的大纲版本，取值为
            ``"HSK 2.0 经典版 (1,200词)"`` 或 ``"HSK 3.0 新课标 (2,000词)"``。

    Returns:
        完整词汇表（含全部级别）的 DataFrame，已规范列名、去除 Topic 为空的行、
        并对 Word / Topic 做首尾去空白。后续由 :func:`select_target_words`
        进一步筛选 HSK 4 级目标词。
    """
    if syllabus_version not in VOCAB_FILES:
        raise ValueError(f"未知的大纲版本：{syllabus_version}")
    csv_path = REPO_ROOT / VOCAB_FILES[syllabus_version]
    if not csv_path.exists():
        raise FileNotFoundError(f"未找到词汇表文件：{csv_path}")

    df = _read_csv_robust(csv_path)
    # 规范列名，去掉首尾空白，避免大小写 / 空格差异
    df.columns = [str(c).strip() for c in df.columns]
    # 去掉 Topic 为空的行，保证后续按主题筛选不会误伤
    df = df.dropna(subset=["Topic"]).reset_index(drop=True)
    # 去除 Word / Topic 首尾空白，保证匹配与展示稳定
    df["Word"] = df["Word"].astype(str).str.strip()
    df["Topic"] = df["Topic"].astype(str).str.strip()
    return df


def select_target_words(
    vocab_df: pd.DataFrame,
    topic_label: str,
    n: int,
    random_seed: int | None = None,
) -> pd.DataFrame:
    """从当前词汇表中随机筛选出指定数量、符合该主题的 HSK 4 级目标词汇。

    Args:
        vocab_df:    :func:`load_vocab` 返回的完整词汇表。
        topic_label: 侧边栏主题标签（含英文注释），内部经 :func:`_map_topic`
                     映射为 CSV 中的 Topic 值。
        n:           需要融入的核心词数量。
        random_seed: 随机种子。传入整数则结果可复现；``None`` 表示纯随机。

    Returns:
        随机筛选出的目标词汇子集（列结构与 ``vocab_df`` 一致）。当该主题下
        HSK 4 级词汇不足 ``n`` 个时，返回全部可用词汇。
    """
    topic = _map_topic(topic_label)
    # 同时按「主题」与「HSK 4 级」筛选，确保是 Level 4 目标词
    pool = vocab_df[
        (vocab_df["Topic"] == topic)
        & (vocab_df["HSK Level"].astype(str).str.contains(TARGET_LEVEL_KEYWORD, na=False))
    ]
    if pool.empty:
        return pd.DataFrame(columns=vocab_df.columns)

    k = min(int(n), len(pool))
    sampled = pool.sample(n=k, random_state=random_seed).reset_index(drop=True)
    return sampled


def _combo_seed(syllabus_version: str, topic_label: str, n: int) -> int:
    """由 (大纲版本, 主题, 词数) 生成稳定的随机种子，保证同一组合结果可复现。"""
    sig = f"{syllabus_version}|{topic_label}|{n}"
    return int.from_bytes(hashlib.md5(sig.encode("utf-8")).digest()[:4], "big")


def render_locked_words(words_df: pd.DataFrame, topic_label: str) -> None:
    """在主界面上展示「当前锁定的教学词汇」。"""
    st.subheader("📌 当前锁定的教学词汇 (Locked Target Vocabulary)")

    if words_df is None or words_df.empty:
        st.info(
            f"当前大纲在主题「{_map_topic(topic_label)}」下没有 HSK 4 级词汇，"
            "请更换主题或大纲版本。"
        )
        return

    st.caption(
        f"主题：{_map_topic(topic_label)} ｜ 已锁定 {len(words_df)} 个 HSK 4 级目标词汇"
    )

    # —— 卡片式展示：每行 4 个词卡 ——
    cards_per_row = 4
    show_cols = ["Word", "Pinyin", "POS", "Definition"]
    rows = [words_df.iloc[i : i + cards_per_row] for i in range(0, len(words_df), cards_per_row)]
    for row in rows:
        cols = st.columns(cards_per_row)
        for col, (_, item) in zip(cols, row.iterrows()):
            with col:
                with st.container(border=True):
                    st.markdown(f"#### {item['Word']}")
                    st.caption(f"{item.get('Pinyin', '')} · {item.get('POS', '')}")
                    st.write(item.get("Definition", ""))

    # —— 完整表格，便于复制 / 排查 ——
    with st.expander("查看完整词汇表", expanded=False):
        st.dataframe(words_df[show_cols], use_container_width=True, hide_index=True)

    # —— 下载为 CSV，方便后续环节使用 ——
    st.download_button(
        label="⬇️ 下载锁定词汇 (CSV)",
        data=words_df[show_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name="locked_hsk4_words.csv",
        mime="text/csv",
    )


# ============================================================================
# 大模型 API 配置与调用（OpenAI 兼容：支持 OpenAI / DeepSeek / SiliconFlow 等）
# ============================================================================

# 服务商预设（均为 OpenAI 兼容端点，base_url / model 可在侧边栏手动覆盖）
LLM_PRESETS = {
    "OpenAI (官方)": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "DeepSeek (深度求索)": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "SiliconFlow (硅基流动)": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    "自定义 (Custom)": {"base_url": "", "model": ""},
}


def _secret(key: str):
    """安全读取 st.secrets，缺失时返回 None（兼容本地无 secrets 文件的环境）。"""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return None


def _clean_token(v):
    """规整 API Key / 模型名：去首尾空白，剥除误粘贴的 'Bearer ' 前缀。"""
    if not v:
        return None
    s = str(v).strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    return s or None


def _clean_base_url(v):
    """规整 Base URL：去首尾空白与末尾斜杠，避免拼接双斜杠导致鉴权异常。"""
    if not v:
        return None
    s = str(v).strip().rstrip("/")
    return s or None


def _resolve_api_config(api_key_input, base_url_input, model_input):
    """按优先级解析 API 配置：侧边栏输入 > 环境变量 > st.secrets。

    自动规整：Key 去空白/剥 ``Bearer `` 前缀、base_url 去末尾斜杠、
    model 去空白。这类粘贴瑕疵常导致 401 'Token is invalid'。

    Returns:
        (api_key, base_url, model)，缺失项为 ``None``。其中 ``base_url`` 为
        ``None`` 时由 ``openai`` 库回退到 OpenAI 官方端点。
    """
    raw_key = api_key_input or os.environ.get("OPENAI_API_KEY") or _secret("OPENAI_API_KEY")
    raw_url = base_url_input or os.environ.get("OPENAI_BASE_URL") or _secret("OPENAI_BASE_URL")
    raw_model = model_input or os.environ.get("OPENAI_MODEL") or _secret("OPENAI_MODEL")
    return _clean_token(raw_key), _clean_base_url(raw_url), _clean_token(raw_model)


def build_generation_messages(
    words_df: pd.DataFrame,
    topic_label: str,
    syllabus_version: str,
    char_limit: int,
) -> list[dict]:
    """组装分级阅读生成的 System / User 提示词。

    将大纲版本、教学主题、字数限制与锁定的核心词汇列表（含拼音、词性、
    释义）一并注入 System Prompt，约束模型在 HSK 1–4 级词汇范围内创作，
    并在文末附「核心词回顾」。
    """
    topic = _map_topic(topic_label)
    version_short = "2.0" if "2.0" in syllabus_version else "3.0"
    word_list = []
    if words_df is not None and not words_df.empty:
        for _, r in words_df.iterrows():
            word_list.append(
                f"{r['Word']}（{r.get('Pinyin', '')}，{r.get('POS', '')}："
                f"{r.get('Definition', '')}）"
            )
    vocab_block = "\n".join(f"- {w}" for w in word_list) if word_list else "- （无）"

    system_prompt = f"""你是一名资深的国际中文教师与分级阅读材料编写专家，精通 HSK（汉语水平考试）词汇大纲。请根据以下教学约束，创作一篇适合 HSK 4 级学习者的中文分级阅读短文。

【大纲版本】HSK {version_short}
【教学主题】{topic}
【目标字数】约 {char_limit} 个汉字（允许 ±10% 浮动）
【必须融入的核心词汇】以下 {len(word_list)} 个 HSK 4 级目标词，须自然、准确地融入文中（可变形但不改变词义核心）：
{vocab_block}

【写作要求】
1. 词汇难度严格控制在 HSK 1–4 级范围内，不得使用 HSK 5/6 级超纲词。
2. 句式多样但规范，避免过长嵌套，适合中级学习者阅读。
3. 内容紧扣「{topic}」主题，情节完整、逻辑连贯、有真实生活气息。
4. 全部核心词须在文中出现，并在文末以「核心词回顾」列表形式再次列出（词 + 拼音 + 简释）。
5. 仅输出短文正文与「核心词回顾」两段，不要输出任何额外解释、标题编号或英文翻译。

现在请开始创作。"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请直接输出分级阅读短文。"},
    ]


def stream_reading_text(api_key, base_url, model, messages, temperature=0.7):
    """调用 OpenAI 兼容接口，以流式生成器逐段 yield 文本片段。

    供 ``st.write_stream`` 消费，实现逐字实时渲染。``base_url`` 为 ``None`` 时
    使用 OpenAI 官方端点；填入 DeepSeek / SiliconFlow 等兼容端点即可切换服务商。
    """
    client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
    stream = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


# ============================================================================
# 2. 侧边栏（Sidebar）- 教学参数控制面板
# ============================================================================
st.sidebar.header("⚙️ 教学参数设置 (Pedagogical Parameters)")

# 亮点：双轨大纲版本一键切换
syllabus_version = st.sidebar.radio(
    "1. 选择 HSK 大纲版本:",
    ("HSK 2.0 经典版 (1,200词)", "HSK 3.0 新课标 (2,000词)")
)

# 亮点：8大情境主题选择
theme_choice = st.sidebar.selectbox(
    "2. 选择教学主题 (Topic):",
    [
        "日常生活与情感 (Daily Life & Emotion)",
        "职场与教育 (Work & Education)",
        "消费与休闲 (Shopping & Leisure)",
        "科技与环境 (Tech & Environment)",
        "旅行与交通 (Travel & Transport)",
        "健康与运动 (Health & Sports)",
        "人际交往 (Interpersonal Communication)",
        "语法功能词 (Grammar & Connectives)"
    ]
)

# 控制文章字数与生词量
char_limit = st.sidebar.slider("3. 目标文章字数 (Characters):", 200, 400, 300, step=50)
target_vocab_count = st.sidebar.slider("4. 融入核心词数量 (Target Vocabulary):", 3, 8, 5)

# 重新随机锁定：保持当前大纲/主题/词数不变，换一组目标词
if st.sidebar.button("🔄 重新随机锁定 (Reshuffle)", use_container_width=True):
    st.session_state["lock_seed"] = st.session_state.get("lock_seed", 0) + 1

# --- 大模型 API 配置（侧边栏输入优先，回退 env / st.secrets）---
st.sidebar.markdown("### 🤖 大模型 API 配置")

# 初始化预设字段，使服务商切换时自动填充 base_url / model
if "cfg_provider" not in st.session_state:
    st.session_state["cfg_provider"] = list(LLM_PRESETS.keys())[0]
if "cfg_base_url" not in st.session_state:
    st.session_state["cfg_base_url"] = LLM_PRESETS[st.session_state["cfg_provider"]]["base_url"]
if "cfg_model" not in st.session_state:
    st.session_state["cfg_model"] = LLM_PRESETS[st.session_state["cfg_provider"]]["model"]


def _apply_provider_preset():
    """服务商切换时，把 base_url / model 同步为该服务商预设值。"""
    p = LLM_PRESETS[st.session_state["cfg_provider"]]
    st.session_state["cfg_base_url"] = p["base_url"]
    st.session_state["cfg_model"] = p["model"]


provider = st.sidebar.selectbox(
    "服务商预设 (Provider):",
    list(LLM_PRESETS.keys()),
    key="cfg_provider",
    on_change=_apply_provider_preset,
    help="选择 OpenAI / DeepSeek / SiliconFlow 等兼容服务商；下方字段可手动覆盖",
)
api_key = st.sidebar.text_input(
    "🔑 API Key", type="password", key="cfg_api_key",
    help="留空则依次读取环境变量 OPENAI_API_KEY / st.secrets",
)
base_url = st.sidebar.text_input(
    "🌐 Base URL (OpenAI 兼容)", key="cfg_base_url",
    help="如 https://api.deepseek.com 或 https://api.siliconflow.cn/v1",
)
model = st.sidebar.text_input(
    "🏷️ 模型名 (Model)", key="cfg_model",
    help="如 gpt-4o-mini / deepseek-chat / Qwen/Qwen2.5-7B-Instruct",
)

st.sidebar.write("---")
st.sidebar.markdown("💡 *本原型专为语言教师备课设计，生成材料严格受控于所选大纲词库。*")

# ============================================================================
# 锁定教学词汇：加载词库 -> 按主题+级别随机筛选 -> 主界面展示
# ============================================================================
# 加载当前大纲词库（缓存，切换版本自动重载）
vocab_df = load_vocab(syllabus_version)

# 组合（大纲/主题/词数）变化时，重置「重新随机」计数器
combo_sig = _combo_seed(syllabus_version, theme_choice, target_vocab_count)
if st.session_state.get("locked_sig") != combo_sig:
    st.session_state["locked_sig"] = combo_sig
    st.session_state["lock_seed"] = 0

# 有效种子 = 组合种子 + 重新随机计数；同一组合结果稳定，点「重新随机」换一组
effective_seed = combo_sig + st.session_state.get("lock_seed", 0)
locked_words = select_target_words(
    vocab_df, theme_choice, target_vocab_count, random_seed=effective_seed
)
render_locked_words(locked_words, theme_choice)

st.write("---")

# ============================================================================
# 3. 主界面布局 - 左右分栏
# ============================================================================
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📝 1. 生成分级阅读材料")
    st.write("点击下方按钮，系统将根据大纲、主题与锁定词汇调用大模型生成受控文章：")

    gen_clicked = st.button("🚀 一键生成 HSK 4 级阅读 (Generate Text)", type="primary")

    # 输出区：生成时流式写入；非生成轮次持久展示上一次结果
    out = st.container(border=True)
    with out:
        if gen_clicked:
            # —— 前置校验：锁定词汇 ——
            if locked_words is None or locked_words.empty:
                st.warning("当前主题下没有可用的 HSK 4 级核心词，请先更换主题/大纲或重新锁定。")
            else:
                api_key_r, base_url_r, model_r = _resolve_api_config(api_key, base_url, model)
                if not api_key_r:
                    st.error(
                        "未获取到 API Key：请在侧边栏填写，或在环境变量 / st.secrets 中"
                        "设置 OPENAI_API_KEY。"
                    )
                elif not model_r:
                    st.error("未指定模型名：请在侧边栏填写模型名（如 gpt-4o-mini / deepseek-chat）。")
                else:
                    messages = build_generation_messages(
                        locked_words, theme_choice, syllabus_version, char_limit
                    )
                    endpoint = base_url_r or "OpenAI 官方端点"
                    st.caption(f"📡 调用：{model_r} @ {endpoint}")
                    try:
                        text = st.write_stream(
                            stream_reading_text(api_key_r, base_url_r, model_r, messages)
                        )
                    except openai.AuthenticationError as e:
                        msg = str(e)
                        st.error(
                            "🔑 鉴权失败（HTTP 401）：服务商拒绝该 API Key。\n\n"
                            "常见原因与排查：\n"
                            "1. Key 夓带了首尾空格 / `Bearer ` 前缀 → 已自动清洗，若仍失败请重新复制完整 Key；\n"
                            "2. Key 与所选服务商不匹配（OpenAI 的 Key 不能用于 SiliconFlow/DeepSeek，反之亦然）；\n"
                            "3. Key 已被删除/过期 → 前往对应控制台重新生成；\n"
                            "4. 账号未实名/未激活 → SiliconFlow 需完成手机号验证后 Key 才生效。\n\n"
                            f"原始报错：{msg}"
                        )
                        text = ""
                    except openai.APIConnectionError as e:
                        st.error(
                            f"🔌 无法连接 API（{endpoint}）：请检查 Base URL、网络或代理设置。\n\n"
                            f"原始报错：{e}"
                        )
                        text = ""
                    except openai.APIStatusError as e:
                        code = getattr(e, "status_code", None) or 0
                        msg = str(e)
                        if code == 402 or "Insufficient Balance" in msg or "insufficient_quota" in msg:
                            st.error(
                                "💸 账户余额不足（HTTP 402 Insufficient Balance）：\n"
                                "该服务商账户可用额度已用尽，请求被拒。\n\n"
                                "解决办法（任选其一）：\n"
                                "1. 前往对应服务商控制台充值（DeepSeek / SiliconFlow / OpenAI）；\n"
                                "2. 切换到有免费额度的服务商——侧边栏选 **SiliconFlow (硅基流动)**，\n"
                                "   模型填 `Qwen/Qwen2.5-7B-Instruct` 等免费模型即可。\n\n"
                                f"原始报错：{msg}"
                            )
                        elif code == 429:
                            st.error(
                                "⏳ 请求过于频繁或触发限额（HTTP 429）：\n"
                                "请稍候几秒再试，或降低生成频率 / 切换模型。\n\n"
                                f"原始报错：{msg}"
                            )
                        elif code and 500 <= code < 600:
                            st.error(
                                f"⚙️ 服务端临时故障（HTTP {code}）：\n{msg}\n"
                                "稍后重试即可；若持续出现请更换服务商或模型。"
                            )
                        else:
                            st.error(f"API 调用失败（HTTP {code}）：{msg}")
                        text = ""
                    except openai.APIError as e:
                        # 兜底：非 HTTP 状态类的 openai 异常（如请求构造错误）
                        st.error(f"API 调用失败：{e}")
                        text = ""
                    except Exception as e:  # 兜底：其它服务商返回的非标准异常
                        st.error(f"生成失败：{e}")
                        text = ""

                    if text:
                        st.session_state["generated_text"] = text
                        st.session_state["generated_topic"] = theme_choice
                        st.success("✨ 文章生成成功！")
                        st.markdown("---")
                        st.markdown("**💡 本轮锁定的核心词 (Vocabulary Tooltips):**")
                        tips = [
                            f"**{r['Word']}** ({r.get('Pinyin', '')})："
                            f"{r.get('Definition', '')}"
                            for _, r in locked_words.iterrows()
                        ]
                        st.markdown("\n".join(f"- {t}" for t in tips))
                        st.download_button(
                            "⬇️ 下载文章 (TXT)",
                            text.encode("utf-8"),
                            file_name="hsk4_reading.txt",
                            mime="text/plain",
                        )
        elif st.session_state.get("generated_text"):
            # 非生成轮次：持久展示上一次生成结果，避免跨 rerun 丢失
            st.markdown(st.session_state["generated_text"])
            st.download_button(
                "⬇️ 下载文章 (TXT)",
                st.session_state["generated_text"].encode("utf-8"),
                file_name="hsk4_reading.txt",
                mime="text/plain",
            )

with col2:
    st.header("✍️ 2. 生成 HSK 4 单项选择题")
    st.write("根据左侧生成的文章，自动配置具有高干扰效度的四选一阅读理解题：")
    
    if st.button("❓ 一键出题 (Generate MCQ)"):
        st.info("🔄 正在提取核心词，并根据相同词性与语义生成干扰项...")
        
        # 模拟展示，第5-6周我们会在这里接入自动干扰项生成算法
        st.success("✨ 习题生成成功！(当前为测试模拟预览)")
        st.markdown("**问题：根据文章，小明最近为什么需要准备很多简历？**")
        st.radio(
            "选择你的答案：",
            [
                "A. 因为公司最近有很多新【安排】",
                "B. 因为公司正在【招聘】新职员",
                "C. 因为他的工作没有意思",
                "D. 因为他想离开这家公司"
            ]
        )
        if st.button("提交答案"):
            st.write("🎉 回答正确！考点解析：文章中提到‘因为公司要招聘新的职员，所以小明需要准备很多简历’。")
