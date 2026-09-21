import hashlib
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

# API 密钥配置 (可输入你自己的 Key)
api_key = st.sidebar.text_input("🔑 输入 OpenAI/API Key (或使用默认):", type="password")

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
    st.write("点击下方按钮，系统将根据设置的大纲和主题生成受控文章：")
    
    # 临时占位，后续在此接入真实的词汇库抽取逻辑
    if st.button("🚀 一键生成 HSK 4 级阅读 (Generate Text)", type="primary"):
        st.info("🔄 正在调用大模型 API 并根据大纲词库进行受控生成...")
        
        # 模拟展示，第5-6周我们会把这里替换为真实的 API 调用和 Prompt
        st.success("✨ 文章生成成功！(当前为测试模拟预览)")
        simulated_text = """    小明在一家电脑公司工作。他觉得自己的**工作**很有意思，但是最近公司有很多新**安排**。因为公司要**招聘**新的职员，所以小明需要准备很多**简历**。他的经理对他说：“如果你这次面试准备得好，我相信你一定会非常**顺利**地通过考核，成为合格的部门主管。”"""
        st.write(simulated_text)
        
        st.write("---")
        st.markdown("**💡 融入的 HSK 4 核心词提示 (Vocabulary Tooltips):**")
        st.caption("• **安排 (ān pái)**: to arrange; to plan")
        st.caption("• **简历 (jiǎn lì)**: resume; CV")
        st.caption("• **顺利 (shùn lì)**: smoothly; successfully")

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
