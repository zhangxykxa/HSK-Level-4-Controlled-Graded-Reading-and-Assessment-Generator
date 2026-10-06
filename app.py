import hashlib
import os
from pathlib import Path

import streamlit as st
import pandas as pd
import openai

# 1. 页面基本配置
st.set_page_config(page_title="HSK 4 Graded Material Generator", layout="wide")

# 隐藏 Streamlit 开发痕迹（CSS 注入）
# 注意：不隐藏 header 和 stStatusWidget，否则 Streamlit Cloud 会导致页面白屏/无法交互
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .viewerBadge_container__17vsn {display: none !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

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
# 功能一：HSK 4 控词检测 / 生词率 / 大纲合规度分析
# ============================================================================
# 词汇检索策略（零第三方依赖，避免 jieba 等安装失败）：
#   1) 以词汇表内所有「目标词 + 前置 1~3 级词」为蓝本，构建最大匹配词典：
#      字典 key = 词，value = (Pinyin, POS, Definition)
#      以「按长度降序」依次尝试匹配，保证多字词优先命中（最大匹配 = 类分词效果）。
#   2) 同时构建「字集合」：任何出现在大纲词里的单字都算在「大纲字」里；
#      这样即便词未命中，单字也是大纲覆盖字，避免过度统计为「超纲」。
#   3) 对中文标点 / 空白 / 数字 单独处理：不计入「词数」也不计入「字数统计汉字部分」，
#      但保留在原文中用于阅读。
#   学术参考：
#      - Laufer (1989) 提出 95% 词汇覆盖率阈值才能流畅阅读。
#      - 本文「大纲覆盖率」定义 = (命中大纲词的词元数) / (总有效中文词元数)。
# ============================================================================

_CJK_RANGE = (0x4E00, 0x9FFF)            # CJK 统一汉字（含简繁）
_CJK_EXT_A = (0x3400, 0x4DBF)            # Ext A 扩展汉字
_PUNCT_CHARS = set("，。！？、；：""''（）《》【】,.!?;:\'\"()[]—-…· \t\n\r")


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return (_CJK_RANGE[0] <= cp <= _CJK_RANGE[1]) or (
        _CJK_EXT_A[0] <= cp <= _CJK_EXT_A[1]
    )


def _count_cjk_chars(text: str) -> int:
    return sum(1 for ch in text if _is_cjk_char(ch))


def _build_syllabus_dicts(vocab_df):
    """由词汇表 DataFrame 构造 3 份索引，供分析使用：

    Returns:
        (word_meta, syllable_words, syllable_chars)
        - word_meta: dict[str] = (pinyin, pos, definition)
          包含词汇表中全部词（含 1~4 级）
        - syllable_words: set[str]，全部大纲词（含前置级别），用于词覆盖率统计
        - syllable_chars: set[str]，全部大纲字，用于兜底的字覆盖率统计
    """
    word_meta = {}
    syllable_words = set()
    syllable_chars = set()
    if vocab_df is None or vocab_df.empty:
        return word_meta, syllable_words, syllable_chars

    for _, row in vocab_df.iterrows():
        word = str(row.get("Word", "") or "").strip()
        if not word:
            continue
        pinyin = str(row.get("Pinyin", "") or "").strip()
        pos = str(row.get("POS", "") or "").strip()
        definition = str(row.get("Definition", "") or "").strip()
        # 以第一次出现的释义为准；后续出现相同词的不同 POS/释义跳过（避免抖动）
        if word not in word_meta:
            word_meta[word] = (pinyin, pos, definition)
        syllable_words.add(word)
        for ch in word:
            if _is_cjk_char(ch):
                syllable_chars.add(ch)
    return word_meta, syllable_words, syllable_chars


def _max_match_tokenize(text: str, syllable_words):
    """基于「大纲词集合」的最大匹配切分。

    算法：
        设 L = 大纲词中的最大长度；
        对每个位置 i，尝试 j = min(L, len(text) - i) .. 1，取第一个命中
        ``syllable_words`` 的子串作为一个 token；否则「只取第一个字符」
        （若是中文单字，仍会在后续用字覆盖率兜底；若是标点/数字/字母直接单独返回）。

    Returns:
        List[Tuple[str, bool]] ： (token, 是否命中大纲词)
    """
    tokens = []
    i = 0
    n = len(text)
    max_word_len = max((len(w) for w in syllable_words), default=4)
    # 最小 4，防止词表里只有 1 字词导致多字词无法匹配
    max_word_len = max(max_word_len, 4)
    while i < n:
        ch = text[i]
        # 非 CJK：标点 / 数字 / 字母 单独成 token（用于还原原文，但不计入词数统计）
        if not _is_cjk_char(ch):
            # 把连续非 CJK 合并为一个 token，便于高亮/展示
            j = i
            while j < n and not _is_cjk_char(text[j]):
                j += 1
            tok = text[i:j]
            tokens.append((tok, False))
            i = j
            continue
        # CJK：最大匹配
        matched = False
        end = min(i + max_word_len, n)
        for j in range(end, i, -1):
            substr = text[i:j]
            if substr in syllable_words:
                tokens.append((substr, True))
                i = j
                matched = True
                break
        if not matched:
            # 单独一个汉字：作为单字 token，后续再判断是否在 syllable_chars 里
            tokens.append((ch, False))
            i += 1
    return tokens


def analyze_reading_compliance(text: str, locked_words_df, vocab_df):
    """对生成的分级阅读文章做全流程合规度分析。

    Returns:
        dict with keys:
            total_cjk_chars, total_token_count,
            target_words (list[dict]), all_targets_hit, target_hit_count, target_total,
            syllabus_hit_count, syllabus_coverage_pct,
            out_of_syllabus_words (list[dict]),
            highlighted_html
    """
    word_meta, syllable_words, syllable_chars = _build_syllabus_dicts(vocab_df)

    # 1) 总字数（汉字，不含标点/空格/数字；和 250–350 字目标对齐）
    total_cjk_chars = _count_cjk_chars(text)

    # 2) 最大匹配切分 + 高亮 + 统计
    tokens = _max_match_tokenize(text, syllable_words)

    total_token_count = 0        # 有效中文词元数（单字+多字词，不含标点）
    syllabus_hit_count = 0       # 命中大纲词（含单字命中 syllable_chars 的）
    oos_seen = {}                # 超纲词/字 -> 出现次数（去重）

    html_parts = []
    for tok, hit_word in tokens:
        # 判断是不是「有效中文词元」——只要包含一个汉字就算
        contains_cjk = any(_is_cjk_char(c) for c in tok)
        if not contains_cjk:
            # 标点 / 空格 / 数字 / 字母：原样输出，不统计
            html_parts.append(_html_escape(tok))
            continue

        total_token_count += 1

        # 命中规则：
        #   a) 多字词 -> syllable_words 命中就算
        #   b) 单字词 -> 在 syllable_chars 中就算（大量前置级单字可能没在词表里）
        if hit_word:
            syllabus_hit_count += 1
            html_parts.append(_html_escape(tok))
            continue

        # 没命中词，但单字全在 syllable_chars 里，也视为命中大纲（字级别兜底）
        if len(tok) == 1:
            if tok in syllable_chars:
                syllabus_hit_count += 1
                html_parts.append(_html_escape(tok))
                continue
        else:
            # 多字词拆分单字判断——如果全部 CJK 字都在大纲里，认为这些字「不超纲」，
            # 仅记一次「该多字组合未出现在大纲」，但覆盖率里按（命中单字的比例）算。
            covered_unichars = sum(1 for c in tok if _is_cjk_char(c) and c in syllable_chars)
            total_unichars_in_tok = sum(1 for c in tok if _is_cjk_char(c))
            # 覆盖率计数：分子按 (covered/total) 比例算进命中，避免虚高
            if total_unichars_in_tok > 0:
                syllabus_hit_count += covered_unichars / total_unichars_in_tok

        # 其余：超纲词 / 字
        if tok not in oos_seen:
            # 对多字超纲词：尝试逐字拼出拼音（字级元信息）
            pinyin_parts = []
            pos_tokens = []
            def_tokens = []
            # 对词级别的超纲，尝试查每个单字的拼音（若该单字作为大纲词）
            for c in tok:
                if c in word_meta:
                    py, po, df = word_meta[c]
                    if py:
                        pinyin_parts.append(py)
                    if po and po not in pos_tokens:
                        pos_tokens.append(po)
                    if df:
                        def_tokens.append(f"{c}:{df}")
            py = " ".join(p for p in pinyin_parts if p)
            oos_seen[tok] = {
                "word": tok,
                "pinyin": py or "",
                "pos": "；".join(pos_tokens) if pos_tokens else "",
                "definition": " ｜ ".join(def_tokens) if def_tokens else "",
                "count": 1,
            }
        else:
            oos_seen[tok]["count"] += 1

        # 高亮超纲词：橙色文字 + 下划线
        html_parts.append(
            f'<span style="color:#FF6B35;text-decoration:underline;text-decoration-color:#FF6B35;text-decoration-thickness:1.5px;text-underline-offset:3px;" title="疑似超纲词">{_html_escape(tok)}</span>'
        )

    highlighted_html = "".join(html_parts)

    # 覆盖率（Laufer 95% 阈值参考）
    if total_token_count > 0:
        coverage = (syllabus_hit_count / total_token_count) * 100
    else:
        coverage = 0.0

    # 3) 核心词融入率：locked_words 每个词是否出现在原文里（简单字符串包含即可）
    target_words = []
    target_hit_count = 0
    if locked_words_df is not None and not locked_words_df.empty:
        for _, r in locked_words_df.iterrows():
            w = str(r.get("Word", "") or "").strip()
            hit = bool(w) and (w in text)
            if hit:
                target_hit_count += 1
            target_words.append(
                {
                    "word": w,
                    "pinyin": str(r.get("Pinyin", "") or "").strip(),
                    "pos": str(r.get("POS", "") or "").strip(),
                    "definition": str(r.get("Definition", "") or "").strip(),
                    "hit": hit,
                }
            )
    target_total = max(len(target_words), 1)
    all_targets_hit = len(target_words) > 0 and target_hit_count == len(target_words)

    out_of_syllabus_words = sorted(
        oos_seen.values(), key=lambda x: (-x["count"], x["word"])
    )

    return {
        "total_cjk_chars": total_cjk_chars,
        "total_token_count": total_token_count,
        "target_words": target_words,
        "target_hit_count": target_hit_count,
        "target_total": len(target_words),
        "target_integration_pct": round(
            target_hit_count / target_total * 100 if target_total else 0.0, 1
        ),
        "all_targets_hit": all_targets_hit,
        "syllabus_hit_count": syllabus_hit_count,
        "syllabus_coverage_pct": round(coverage, 2),
        "out_of_syllabus_words": out_of_syllabus_words,
        "highlighted_html": highlighted_html,
    }


def _html_escape(s: str) -> str:
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_compliance_report(analysis: dict):
    """把 analyze_reading_compliance 的结果渲染为 st.expander 卡片。"""
    with st.expander("📊 本文 HSK 4 大纲合规度检测分析报告", expanded=True):
        # 指标卡片：每行 4 列
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        total_chars = analysis["total_cjk_chars"]
        with kpi1:
            # 字数目标 250–350
            ok = 250 <= total_chars <= 350
            delta = ""
            if total_chars < 250:
                delta = f"偏短，距离下限还需 {250 - total_chars} 字"
            elif total_chars > 350:
                delta = f"偏长，超出上限 {total_chars - 350} 字"
            else:
                delta = "在 250–350 字目标范围内 ✅"
            st.metric(
                "总字数 (Total Characters)",
                f"{total_chars} 字",
                delta=delta,
                delta_color="normal" if ok else "inverse",
            )
        with kpi2:
            pct = analysis["target_integration_pct"]
            st.metric(
                "核心词融入率 (Target Integration)",
                f"{pct}%  ({analysis['target_hit_count']}/{analysis['target_total']})",
                delta="✅ 5/5 全部命中" if analysis["all_targets_hit"] else "⚠️ 仍有缺失核心词",
                delta_color="normal" if analysis["all_targets_hit"] else "inverse",
            )
        with kpi3:
            cov = analysis["syllabus_coverage_pct"]
            ok95 = cov >= 95
            st.metric(
                "大纲词汇覆盖率 (Lexical Coverage)",
                f"{cov}%",
                delta=f"{'≥ 95% (Laufer 1989 阈值 ✅)' if ok95 else '< 95% 建议调整'}"
            )
        with kpi4:
            oosn = len(analysis["out_of_syllabus_words"])
            st.metric(
                "疑似超纲生词 (Out-of-Syllabus)",
                f"{oosn} 个",
                delta=None,
            )

        st.markdown("---")

        # 子报告 A：核心词融入检查
        st.markdown("### 🎯 核心词融入逐项检查")
        if analysis["target_words"]:
            rows_per = 4
            chunks = [
                analysis["target_words"][i : i + rows_per]
                for i in range(0, len(analysis["target_words"]), rows_per)
            ]
            for chunk in chunks:
                cols = st.columns(rows_per)
                for col, tw in zip(cols, chunk):
                    with col:
                        with st.container(border=True):
                            status = "✅ 命中" if tw["hit"] else "❌ 未命中"
                            st.markdown(f"#### {tw['word']} {status}")
                            st.caption(
                                f"{tw['pinyin']} · {tw['pos']}"
                                if tw["pinyin"] or tw["pos"]
                                else " "
                            )
                            st.write(tw["definition"] or "")
        else:
            st.info("当前锁定词汇为空，跳过核心词融入率展示。")

        st.markdown("---")

        # 子报告 B：高亮版正文 + 超纲生词表
        left_a, right_a = st.columns([2, 1])
        with left_a:
            st.markdown("### 📖 正文（橙色下划线标注疑似超纲词）")
            st.markdown(
                f'<div style="line-height:2;font-size:16px;padding:12px 14px;border:1px solid #eee;border-radius:8px;background:#fff;">{analysis["highlighted_html"]}</div>',
                unsafe_allow_html=True,
            )
        with right_a:
            st.markdown("### ⚠️ 疑似超纲生词卡")
            if not analysis["out_of_syllabus_words"]:
                st.success("🎉 未检测到疑似超纲词，完全在大纲字表内！")
            else:
                for w in analysis["out_of_syllabus_words"]:
                    with st.container(border=True):
                        sub = []
                        if w["pinyin"]:
                            sub.append(w["pinyin"])
                        if w["pos"]:
                            sub.append(w["pos"])
                        st.markdown(f"**{w['word']}**")
                        if sub:
                            st.caption(" · ".join(sub))
                        if w["definition"]:
                            st.write(w["definition"])
                        st.caption(f"出现次数：{w['count']}")

        # 学术注释
        st.markdown("---")
        st.caption(
            "📚 学术说明：\n"
            "• 「总字数」仅统计汉字（不含标点、空格、数字），与 HSK 阅读长度测量标准一致。\n"
            "• 「大纲词汇覆盖率」参考 Laufer (1989) 的 95% 阈值：≥95% 时学习者可在不查词典的情况下流畅理解语篇。\n"
            "• 疑似超纲词仅为提示，教师可根据学情决定是否替换为更常见的 4 级内同义词，或作为拓展性词汇处理。"
        )


# ============================================================================
# 功能二：一键导出 HSK 4 备课教案讲义（Markdown）
# ============================================================================


def build_lesson_plan_markdown(
    text: str,
    locked_words_df,
    syllabus_version: str,
    topic_label: str,
    mcq_questions,
    analysis=None,
):
    """将文章、生词卡、选择题 + 答案解析打包为一份 Markdown 教案。

    不引入任何额外依赖，仅字符串拼接；输出以 UTF-8 + BOM 编码，
    便于 Windows 下复制进 Word 或粘贴进 OneNote / Notion 不乱码。
    """
    lines = []
    # 标题元数据
    lines.append("# HSK 4 分级阅读 · 教师备课教案讲义")
    lines.append("")
    lines.append(f"- **大纲版本**：{syllabus_version}")
    lines.append(f"- **主题**：{_map_topic(topic_label)}（{topic_label}）")
    if analysis:
        lines.append(
            f"- **文章字数**：{analysis['total_cjk_chars']} 汉字"
            f" （目标 250–350）"
        )
        lines.append(
            f"- **大纲词汇覆盖率**：{analysis['syllabus_coverage_pct']}%"
            f" （Laufer 1989 阈值参考：≥ 95%）"
        )
        lines.append(
            f"- **核心词融入**：{analysis['target_hit_count']}/{analysis['target_total']}"
            f"（{analysis['target_integration_pct']}%）"
        )
    lines.append("---")
    lines.append("")

    # Part 1: 分级阅读短文
    lines.append("## 一、分级阅读短文")
    lines.append("")
    # 排版：去除首尾空白，段落间空行
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    # Markdown 段落 = 空行分隔
    paragraphs = [p.strip() for p in cleaned.split("\n") if p.strip()]
    for p in paragraphs:
        lines.append(p)
        lines.append("")
    lines.append("---")

    # Part 2: 融入的 HSK 核心生词表（词卡）
    lines.append("## 二、本课核心生词（HSK 目标词）")
    lines.append("")
    lines.append("| # | 词语 | 拼音 | 词性 | 英文释义 / 中文讲解 |")
    lines.append("|---|------|------|------|----------------------|")
    idx = 0
    if locked_words_df is not None and not locked_words_df.empty:
        for _, r in locked_words_df.iterrows():
            idx += 1
            w = str(r.get("Word", "") or "").strip()
            py = str(r.get("Pinyin", "") or "").strip()
            po = str(r.get("POS", "") or "").strip()
            df = str(r.get("Definition", "") or "").strip()
            # 转义 Markdown 表格分隔符
            def _md_table_escape(s: str) -> str:
                return s.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {idx} | {_md_table_escape(w)} | {_md_table_escape(py)} "
                f"| {_md_table_escape(po)} | {_md_table_escape(df)} |"
            )
    if analysis and analysis["out_of_syllabus_words"]:
        lines.append("")
        lines.append("### 附：文章中疑似超纲生词（可选择性讲解 / 替换）")
        lines.append("")
        lines.append("| # | 词语 | 拼音 | 词性 | 参考释义 | 出现次数 |")
        lines.append("|---|------|------|------|----------|----------|")
        idx2 = 0
        for w in analysis["out_of_syllabus_words"]:
            idx2 += 1

            def _esc(s):
                return (s or "").replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {idx2} | {_esc(w['word'])} | {_esc(w['pinyin'])} "
                f"| {_esc(w['pos'])} | {_esc(w['definition'])} | {w['count']} |"
            )
    lines.append("")
    lines.append("---")

    # Part 3: 配套单项选择题
    lines.append("## 三、阅读理解 · 配套单项选择题")
    lines.append("")
    if not mcq_questions:
        lines.append("> （当前还未生成 MCQ 题目。请返回系统点击「一键出题」后重新下载，或手动在此处补充。）")
        lines.append("")
    else:
        for i, q in enumerate(mcq_questions):
            lines.append(f"### 第 {i + 1} 题")
            lines.append("")
            lines.append(f"**Q{i + 1}. {str(q.get('question', '')).strip()}**")
            lines.append("")
            for key in ("A", "B", "C", "D"):
                opt = str(q.get("options", {}).get(key, "")).strip()
                lines.append(f"- **{key}.** {opt}")
            lines.append("")
    lines.append("---")

    # Part 4: 教师专用答案与解析
    lines.append("## 四、Answer Key & Explanations（教师专用 · 请勿分发给学生）")
    lines.append("")
    if not mcq_questions:
        lines.append("> 暂无题目，暂无答案解析。")
        lines.append("")
    else:
        for i, q in enumerate(mcq_questions):
            correct = str(q.get("answer", "")).strip()
            expl = str(q.get("explanation", "")).strip()
            lines.append(f"**第 {i + 1} 题 · 正确答案：{correct}**")
            if expl:
                lines.append("")
                lines.append(f"- **考点解析**：{expl}")
            # 附上选项方便对照
            lines.append("")
            opt_strs = []
            for k in ("A", "B", "C", "D"):
                opt = str(q.get("options", {}).get(k, "")).strip()
                opt_strs.append(f"**{k}**. {opt}")
            lines.append("    " + "　".join(opt_strs))
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"> 📚 本教案由「HSK 4 级受控分级阅读与测评生成器」自动生成，"
        f"请结合课堂学情对超纲词 / 题项难度进行二次微调。"
    )

    md = "\n".join(lines)
    # 加 UTF-8 BOM，Windows 下粘贴进 Word / Excel 不乱码
    return "\ufeff" + md


# ============================================================================
# 大模型 API 配置与调用（OpenAI 兼容：支持 OpenAI / DeepSeek / SiliconFlow 等）
# ============================================================================

# 服务商预设（均为 OpenAI 兼容端点，base_url / model 可在侧边栏手动覆盖）
# ⚠️ SiliconFlow 国际站唯一端点：https://api.siliconflow.com/v1
#    控制台：https://cloud.siliconflow.com/me/account/ak
LLM_PRESETS = {
    "SiliconFlow (siliconflow.com · 国际站)": {
        "base_url": "https://api.siliconflow.com/v1",
        "model": "deepseek-ai/DeepSeek-V3",
    },
    "DeepSeek (深度求索)": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "自定义 (Custom)": {"base_url": "", "model": ""},
}


def _fmt_key_tail(api_key: str, n: int = 4) -> str:
    """返回 API Key 的末 ``n`` 位用于展示比对（安全：不显示完整 Key）。"""
    s = str(api_key or "").strip()
    return s[-n:] if len(s) >= n else s or "(空)"


def _build_auth_error_msg(e, api_key_r: str, endpoint: str, model_r: str) -> str:
    """统一 401 鉴权失败提示：含 Key 末 4 位、端点、控制台直达链接，方便快速核对。"""
    msg = str(e)
    key_tail = _fmt_key_tail(api_key_r)
    endpoint_lower = str(endpoint or "").lower()

    # 根据端点推断控制台 URL
    if "siliconflow.com" in endpoint_lower:
        console = "https://cloud.siliconflow.com/me/account/ak"
        provider_note = (
            "1. 👉 当前端点是 **SiliconFlow 国际站 (siliconflow.com)**，\n"
            "   Key 必须从 👉 **https://cloud.siliconflow.com/me/account/ak** 获取；\n"
            "   若你是用国内站 siliconflow.cn 生成的 Key 则必然 401（两站用户体系 100% 独立！）。\n"
            "2. 复制时是否漏了字符？请点控制台「📋 复制」按钮，不要手动拖选。\n"
            "3. 该 Key 是否已在控制台被删除？\n"
            "4. 国际站账号是否已完成邮箱验证 / 手机号验证？"
        )
    elif "siliconflow.cn" in endpoint_lower:
        console = "https://cloud.siliconflow.cn/account/ak"
        provider_note = (
            "1. 👉 当前端点是 SiliconFlow 国内站 (siliconflow.cn)，\n"
            "   Key 必须从 👉 **https://cloud.siliconflow.cn/account/ak** 获取；\n"
            "   国际站 Key 用在这里也会 401（两站完全独立！）。\n"
            "2. 国内版需要完成**国内手机号实名**后 Key 才生效。\n"
            "3. 点「📋 复制」完整 Key，不要手动拖选字符。"
        )
    elif "deepseek.com" in endpoint_lower or "api.deepseek" in endpoint_lower:
        console = "https://platform.deepseek.com/api_keys"
        provider_note = (
            "1. 👉 当前端点是 **DeepSeek (deepseek.com)**，\n"
            "   Key 必须从 👉 **https://platform.deepseek.com/api_keys** 获取；\n"
            "   把 SiliconFlow / OpenAI 的 Key 填到这里必然 401。\n"
            "2. 复制时是否漏了字符？请点控制台「复制」按钮。\n"
            "3. 该 Key 是否已在控制台被删除？新生成一把后立即复制试试。"
        )
    else:
        console = "(未知自定义端点，请参考该服务商文档)"
        provider_note = (
            "1. Key 是否与当前自定义端点的服务商相匹配？\n"
            "2. Key 是否已过期 / 删除 / 复制不完整？"
        )

    # 401 提示：如果官方错误信息已经有 ****abcd，替换成真实末 4 位方便核对
    import re as _re

    masked_pattern = _re.compile(r"\*{2,}([A-Za-z0-9]{3,6})")
    msg_show = masked_pattern.sub(lambda m: f"****{key_tail}", msg)

    return (
        f"🔑 鉴权失败（HTTP 401）：服务商拒绝该 API Key。\n\n"
        f"🔍 诊断信息：\n"
        f"  • 实际使用的 Key 末 4 位：`{key_tail}`\n"
        f"  • 模型：`{model_r}`\n"
        f"  • 端点：`{endpoint}`\n"
        f"  • 对应控制台：{console}\n\n"
        "排查清单：\n"
        f"{provider_note}\n\n"
        "👉 【快速核对方法】：打开上面的控制台链接，对比你刚刚新建的那把 Key 的「末 4 位」，\n"
        f"   必须和这里显示的 `{key_tail}` 完全一致，不一致就是「保存错了 / 复制了旧 Key」。\n\n"
        f"原始报错：{msg_show}"
    )


def _build_balance_error_msg(e, endpoint: str, model_r: str) -> str:
    """统一 402 余额不足提示：区分服务商，不再让用户切到同一服务商自相矛盾。"""
    msg = str(e)
    endpoint_lower = str(endpoint or "").lower()

    if "siliconflow.com" in endpoint_lower or "siliconflow.cn" in endpoint_lower:
        sf_site = "国际站 siliconflow.com" if "siliconflow.com" in endpoint_lower else "国内站 siliconflow.cn"
        balance_url = (
            "https://cloud.siliconflow.com/me/wallet"
            if "siliconflow.com" in endpoint_lower
            else "https://cloud.siliconflow.cn/usercenter/wallet"
        )
        return (
            f"💸 账户余额不足（HTTP 402）：SiliconFlow {sf_site} 账户可用额度已用尽，请求被拒。\n\n"
            f"🔍 诊断信息：\n"
            f"  • 模型：`{model_r}`\n"
            f"  • 端点：`{endpoint}`\n"
            f"  • 余额 / 钱包：{balance_url}\n\n"
            "解决办法（任选其一）：\n"
            "1. 💰 充值：打开上面的钱包链接进行充值；\n"
            "2. 🔄 切换服务商：侧边栏选择「DeepSeek (深度求索)」并确保已配置有效的 DeepSeek Key\n"
            "   （DeepSeek 控制台：https://platform.deepseek.com/api_keys）；\n"
            "3. 🎁  SiliconFlow 新用户可关注官网是否有免费礼包 / 活动，可先完成实名获取赠送额度。\n\n"
            f"原始报错：{msg}"
        )

    if "deepseek.com" in endpoint_lower or "api.deepseek" in endpoint_lower:
        return (
            f"💸 账户余额不足（HTTP 402）：DeepSeek 账户可用额度已用尽，请求被拒。\n\n"
            f"🔍 诊断信息：\n"
            f"  • 模型：`{model_r}`\n"
            f"  • 端点：`{endpoint}`\n"
            "  • 充值链接：https://platform.deepseek.com/billing\n\n"
            "解决办法（任选其一）：\n"
            "1. 💰 充值：打开上面的充值链接；\n"
            "2. 🔄 切换服务商：侧边栏选择「SiliconFlow (siliconflow.com · 国际站)」，\n"
            "   该站有免费试用额度（控制台：https://cloud.siliconflow.com/me/account/ak）。\n\n"
            f"原始报错：{msg}"
        )

    return (
        f"💸 账户余额不足（HTTP 402）：当前服务商账户可用额度已用尽，请求被拒。\n\n"
        f"🔍 诊断信息：\n"
        f"  • 模型：`{model_r}`\n"
        f"  • 端点：`{endpoint}`\n\n"
        "解决办法：充值或切换到其他有额度的服务商 / 模型。\n\n"
        f"原始报错：{msg}"
    )
def _secret(key: str):
    """安全读取 st.secrets，缺失时返回 None（兼容本地无 secrets 文件的环境）。"""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return None


def _clean_token(v):
    """规整 API Key / 模型名：剥除 'Bearer ' 前缀，仅保留 ASCII 可见字符，
    剔除所有空白（含内部）与非 ASCII 字符。

    防止 httpx 编码 ``Authorization`` 头时抛 UnicodeEncodeError（典型现象：
    ``'ascii' codec can't encode characters in position 7-11``），常见于
    Key 粘贴时夹带全角空格 / 隐藏字符 / 中文标点。
    """
    if not v:
        return None
    s = str(v).strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    s = "".join(c for c in s if c.isascii() and c.isprintable() and not c.isspace())
    return s or None


def _clean_base_url(v):
    """规整 Base URL：仅保留 ASCII 可见字符，去末尾斜杠，避免拼接异常。"""
    if not v:
        return None
    s = "".join(c for c in str(v) if c.isascii() and c.isprintable() and not c.isspace())
    return s.rstrip("/") or None


def _has_cloud_api_key() -> bool:
    """检测云端 st.secrets 中是否已配置有效的 API Key。

    检查 ``DEEPSEEK_API_KEY`` / ``SILICONFLOW_API_KEY``
    / ``DEFAULT_API_KEY`` / ``OPENAI_API_KEY`` 任一键是否存在非空值。
    """
    for k in ("DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY", "DEFAULT_API_KEY", "OPENAI_API_KEY"):
        if _secret(k):
            return True
    return False


def _match_provider_label(provider_label: str):
    """根据侧边栏选中的服务商名/标签，返回 (provider_key: str, kind: str)。

    ``kind`` 取值 ``"siliconflow"`` / ``"deepseek"`` / ``"custom"``。
    provider_key 仅显示用，不会泄露。

    兼容中英文、不同历史写法，避免改名后配对失败。
    """
    s = str(provider_label or "").strip().lower()
    if not s:
        return (None, None)
    if "silicon" in s or "硅基" in s:
        return ("SILICONFLOW_API_KEY", "siliconflow")
    if "deep" in s or "深度" in s:
        return ("DEEPSEEK_API_KEY", "deepseek")
    if "custom" in s or "自定义" in s:
        return ("DEFAULT_API_KEY", "custom")
    return (None, None)


def _resolve_cloud_config(provider_label=None):
    """根据 ``provider_label``（侧边栏当前选中的服务商）优先匹配对应的云端密钥。

    当 ``provider_label`` 为空 / 未指定时，回退到 ``st.secrets["DEFAULT_PROVIDER"]``
    （默认 ``"SiliconFlow"``），用于首次加载/就绪提示等非生成场景。

    选择规则：
    - 侧边栏选 **SiliconFlow 国际站** → 只用 ``SILICONFLOW_API_KEY``（不再看 DEFAULT_PROVIDER）
    - 侧边栏选 **DeepSeek** → 只用 ``DEEPSEEK_API_KEY``
    - 侧边栏选 **自定义** → 用 ``DEFAULT_API_KEY`` 兜底
    - 始终支持用对应的 ``_BASE_URL`` / ``_MODEL`` 覆盖默认端点/模型。

    Returns:
        (api_key, base_url, model, provider_label)，若云端未配置则返回 ``(None, None, None, None)``
    """
    # 优先级 1：侧边栏当前实际选择的服务商（精准匹配专用 Key，避免切服务商时 Key 混用）
    if provider_label:
        _, kind = _match_provider_label(provider_label)
        if kind == "siliconflow":
            key = _secret("SILICONFLOW_API_KEY")
            if key:
                base_url = (
                    _secret("SILICONFLOW_BASE_URL") or "https://api.siliconflow.com/v1"
                )
                model = _secret("SILICONFLOW_MODEL") or "deepseek-ai/DeepSeek-V3"
                return (key, base_url, model, provider_label)
        elif kind == "deepseek":
            key = _secret("DEEPSEEK_API_KEY")
            if key:
                base_url = _secret("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
                model = _secret("DEEPSEEK_MODEL") or "deepseek-chat"
                return (key, base_url, model, provider_label)
        elif kind == "custom":
            key = _secret("DEFAULT_API_KEY")
            if key:
                base_url = _secret("OPENAI_BASE_URL") or _secret("DEFAULT_BASE_URL")
                model = _secret("OPENAI_MODEL") or _secret("DEFAULT_MODEL")
                return (key, base_url, model, provider_label)

    # 优先级 2：首次加载 / 就绪提示 → 按 DEFAULT_PROVIDER 确定默认服务商
    default_provider = _secret("DEFAULT_PROVIDER") or "SiliconFlow"
    p_lower = str(default_provider).strip().lower()
    if "silicon" in p_lower or "硅基" in p_lower:
        key = _secret("SILICONFLOW_API_KEY")
        if key:
            base_url = (
                _secret("SILICONFLOW_BASE_URL") or "https://api.siliconflow.com/v1"
            )
            model = _secret("SILICONFLOW_MODEL") or "deepseek-ai/DeepSeek-V3"
            label = "SiliconFlow (siliconflow.com · 国际站)"
            return (key, base_url, model, label)
    elif "deep" in p_lower or "深度" in p_lower:
        key = _secret("DEEPSEEK_API_KEY")
        if key:
            base_url = _secret("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
            model = _secret("DEEPSEEK_MODEL") or "deepseek-chat"
            return (key, base_url, model, "DeepSeek (深度求索)")
    return None, None, None, None


def _resolve_api_config(api_key_input, base_url_input, model_input, provider_label=None):
    """按优先级解析 API 配置：侧边栏手动输入 > 云端 st.secrets > 环境变量。

    云端配置由 :func:`_resolve_cloud_config` 处理。若传了 ``provider_label``
    （即侧边栏当前选中的服务商），会根据该服务商精准匹配对应的专用 Key：
    - 选 DeepSeek → 只用 ``DEEPSEEK_API_KEY``
    - 选 SiliconFlow → 只用 ``SILICONFLOW_API_KEY``

    避免了「DEFAULT_PROVIDER=SiliconFlow，但用户切到 DeepSeek 时仍拿错 Key」的混用 401。

    自动规整：Key 去空白/剥 ``Bearer `` 前缀、base_url 去末尾斜杠、
    model 去空白。这类粘贴瑕疵常导致 401 'Token is invalid'。

    Returns:
        (api_key, base_url, model)，缺失项为 ``None``。
    """
    cloud_key, cloud_url, cloud_model, _ = _resolve_cloud_config(provider_label)

    # 侧边栏优先级最高；空值回落到云端；再回落环境变量（兼容历史用法）
    raw_key = api_key_input or cloud_key or os.environ.get("OPENAI_API_KEY")
    raw_url = base_url_input or cloud_url or os.environ.get("OPENAI_BASE_URL") or _secret("OPENAI_BASE_URL")
    raw_model = model_input or cloud_model or os.environ.get("OPENAI_MODEL") or _secret("OPENAI_MODEL")
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

    供 ``st.write_stream`` 消费，实现逐字实时渲染。填入 DeepSeek / SiliconFlow
    等兼容端点即可切换服务商。
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


# ----------------------------------------------------------------------------
# MCQ（四选一阅读理解单选题）生成
# ----------------------------------------------------------------------------

def build_mcq_messages(
    article_text: str,
    words_df: pd.DataFrame,
    num_questions: int = 2,
) -> list[dict]:
    """组装 MCQ 生成的 System / User 提示词。

    要求大模型针对文章核心事实或目标词汇，出 ``num_questions`` 道四选一
    阅读理解题。严格约束干扰项须具备迷惑性，并以 JSON 格式返回。
    """
    word_list = []
    if words_df is not None and not words_df.empty:
        for _, r in words_df.iterrows():
            word_list.append(
                f"{r['Word']}（{r.get('Pinyin', '')}，{r.get('POS', '')}："
                f"{r.get('Definition', '')}）"
            )
    vocab_block = "\n".join(f"- {w}" for w in word_list) if word_list else "- （无）"

    system_prompt = f"""你是一名国际汉语教学测评专家，擅长为 HSK 4 级学习者设计高质量的阅读理解单项选择题（MCQ）。

请根据以下文章与目标词汇，出 {num_questions} 道四选一阅读理解题。

【文章内容】
{article_text}

【目标词汇（HSK 4 级）】
{vocab_block}

【出题要求】
1. 题目须针对文章核心事实或目标词汇的用法/含义设问，避免考查无关细节。
2. 每题提供 A/B/C/D 四个选项，其中只有一个正确答案。
3. **干扰项（Distractors）必须具备迷惑性**——干扰项应与文章内容相关、语义合理且语法正确，不得出现荒谬、无关或"一眼假"的选项。干扰项最好利用文章中的近似表达、同义词、或学习者的常见误解来设置。
4. 每题附上详细解析，说明正确答案为何正确、各干扰项为何不正确（引用文章原文或目标词汇释义）。
5. 选项文本语言为中文，难度控制在 HSK 4 级以内。

【输出格式】
请严格输出以下 JSON 数组（不要输出任何额外文字、Markdown 标记或解释）：

[
  {{
    "question": "题干文本",
    "options": {{
      "A": "选项A内容",
      "B": "选项B内容",
      "C": "选项C内容",
      "D": "选项D内容"
    }},
    "answer": "A",
    "explanation": "正确答案为A，因为……；B/C/D不正确，因为……。"
  }}
]"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请基于上述文章出 {num_questions} 道 MCQ，严格按 JSON 数组格式输出。"},
    ]


def generate_mcq(api_key, base_url, model, messages, temperature=0.5) -> str:
    """调用大模型生成 MCQ，返回完整的原始 JSON 文本字符串。

    与 :func:`stream_reading_text` 不同，MCQ 生成使用**非流式**调用，
    因为本场景需要一次性获取完整 JSON 后解析为结构化题目。
    """
    client = openai.OpenAI(api_key=api_key, base_url=base_url or None)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=False,
    )
    return resp.choices[0].message.content or ""


def parse_mcq_json(raw: str) -> list[dict]:
    """从大模型返回文本中解析 MCQ JSON 数组。

    自动剥离常见包裹：```json ... ``` 围栏、首尾多余文字。
    解析失败时返回空列表，调用方可据此展示友好错误提示。
    """
    import json
    import re

    text = raw.strip()
    # 剥离 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # 提取第一个 JSON 数组
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    # 校验每道题结构
    valid = []
    for item in data:
        if (
            isinstance(item, dict)
            and "question" in item
            and "options" in item
            and "answer" in item
            and "explanation" in item
            and all(k in item["options"] for k in ("A", "B", "C", "D"))
            and item["answer"] in ("A", "B", "C", "D")
        ):
            valid.append(item)
    return valid


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

# --- 大模型 API 配置（云端 secrets 优先，侧边栏手动输入兜底）---
st.sidebar.markdown("### 🤖 大模型 API 配置")

# 首次加载：根据云端 DEFAULT_PROVIDER 自动设置服务商 / base_url / model
_cloud_key, _cloud_url, _cloud_model, _cloud_label = _resolve_cloud_config()
_cloud_ready = _cloud_key is not None

if "cfg_provider" not in st.session_state:
    if _cloud_ready and _cloud_label in LLM_PRESETS:
        st.session_state["cfg_provider"] = _cloud_label
    else:
        st.session_state["cfg_provider"] = list(LLM_PRESETS.keys())[0]
if "cfg_base_url" not in st.session_state:
    st.session_state["cfg_base_url"] = LLM_PRESETS[st.session_state["cfg_provider"]]["base_url"]
if "cfg_model" not in st.session_state:
    st.session_state["cfg_model"] = LLM_PRESETS[st.session_state["cfg_provider"]]["model"]
# 首次加载且云端就绪：用云端配置覆盖 session_state 中的 base_url / model
if "cloud_initialized" not in st.session_state:
    if _cloud_ready:
        st.session_state["cfg_base_url"] = _cloud_url
        st.session_state["cfg_model"] = _cloud_model
    st.session_state["cloud_initialized"] = True


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
    help="选择 DeepSeek / SiliconFlow 等兼容服务商，或自定义端点",
)

# 云端服务就绪提示：亮起绿色，显示具体服务商名称
if _cloud_ready:
    st.sidebar.success(
        f"✅ 默认 {_cloud_label} 云端服务已就绪！\n"
        "您无需输入任何 API 密钥即可一键生成！"
    )
    # 云端已配置 Key：手动输入框放入默认折叠的高级设置中
    with st.sidebar.expander("🔑 高级设置：使用自定义 API Key", expanded=False):
        api_key = st.text_input(
            "覆盖云端 Key（留空则使用云端配置）:", type="password", key="cfg_api_key",
            help="⚠️ 只要这里填过任何内容，就会永久覆盖云端配置（哪怕现在看起来是空的，Streamlit session_state 可能仍保留旧值）。"
                 "如想回到云端 Key，先点浏览器 🔄 刷新整页，再来这里确认确实是空的再生成。",
        )
else:
    st.sidebar.warning("⚠️ 云端未检测到 API Key，请在下方手动输入。")
    api_key = st.sidebar.text_input(
        "🔑 请输入您的 API Key:", type="password", key="cfg_api_key",
        help="将部署到云端后可在 .streamlit/secrets.toml 中配置免填体验",
    )

base_url = st.sidebar.text_input(
    "🌐 Base URL", key="cfg_base_url",
    help="如 https://api.deepseek.com 或 https://api.siliconflow.com/v1",
)
model = st.sidebar.text_input(
    "🏷️ 模型名 (Model)", key="cfg_model",
    help="如 deepseek-chat / deepseek-ai/DeepSeek-V3",
)

# —— 🛠️ 调试面板：实时展示实际生效的配置（来自云端 / 侧边栏 / 环境变量）
with st.sidebar.expander("🛠️ 调试：查看当前实际生效的配置", expanded=False):
    # 必须把当前侧边栏选中的服务商 provider 传入，确保显示的 Key 和生成时使用的完全一致
    _dbg_key, _dbg_url, _dbg_mdl = _resolve_api_config(api_key, base_url, model, provider)
    _match_pk, _match_kind = _match_provider_label(provider)
    _src_key = []
    if api_key and _clean_token(api_key):
        _src_key.append("侧边栏手动输入(覆盖云端)")
    # 根据当前选中的服务商精准显示「对应哪把云端 Key」
    if _match_pk:
        _cloud_match_key = _secret(_match_pk)
        if _cloud_match_key:
            _src_key.append(f"云端 secrets:{_match_pk}（服务商【{provider}】专用）")
    # 兜底：如果当前服务商没有专用 Key，但 DEFAULT_PROVIDER 那套云 Key 存在，就保留 _cloud_label 的展示
    if not _src_key and _cloud_key:
        _src_key.append(f"云端 secrets:{_cloud_label or 'DEFAULT_API_KEY'}")
    if os.environ.get("OPENAI_API_KEY") and not (_clean_token(api_key) or _cloud_key):
        _src_key.append("环境变量 OPENAI_API_KEY")
    if not _src_key and _dbg_key:
        _src_key.append("未知来源(兜底)")

    st.info(
        "🔍 每次生成时实际发出请求的配置就是下面这组（随服务商下拉联动）：\n\n"
        f"**• 当前服务商预设**：`{provider}`\n"
        f"**• Key 来源优先级**：{' → '.join(_src_key) if _src_key else '(未获取到任何 Key)'}\n"
        f"**• API Key 末 4 位**：`{_fmt_key_tail(_dbg_key)}`\n"
        f"**• 🌐 Base URL**：`{_dbg_url or '(空)'}`\n"
        f"**• 🏷️ 模型名**：`{_dbg_mdl or '(空)'}`\n\n"
        "👉 用法：把「API Key 末 4 位」拿去和对应控制台 Key 的末 4 位对比，\n"
        "   不一致就说明当前生效的不是您以为的那把 Key，检查侧边栏 / Secrets 填写处。\n"
        "   ⚠️ 【关键】：切服务商时，云端 Key 会自动匹配到该服务商专用 Key，\n"
        "   不会再出现「选 DeepSeek 实际用 SiliconFlow Key」的混用 401。",
        icon="ℹ️",
    )

    # 如果侧边栏输入框「非空」（用户以为空但 session_state 可能残留旧值）提示
    if _clean_token(api_key):
        st.warning(
            "⚠️ 注意：「高级设置」里的 API Key 输入框当前**非空**（可能残留历史填过的旧 Key），\n"
            "   正在**优先使用这把 Key 覆盖云端配置**。\n"
            "   如果想切回云端 Secrets 的 Key → 先刷新整页 🔄，\n"
            "   或清空输入框内容再点一次生成。",
            icon="⚠️",
        )

st.sidebar.write("---")
st.sidebar.markdown("💡 *本原型专为语言教师备课设计，生成材料严格受控于所选大纲词库。*")

# ============================================================================
# 功能三：侧边栏挂载「教学效度评估反馈」——科研闭环入口
# ============================================================================
st.sidebar.write("---")
st.sidebar.subheader("📋 教学效度评估反馈（专家试用）")
st.sidebar.info(
    "🎓 尊敬的专家：\n\n"
    "本系统为 **香港理工大学（The Hong Kong Polytechnic University）** "
    "学位研究项目（MA Teaching Chinese as a Second Language / 汉语作为第二语言教学）"
    "开发的受控分级阅读与测评原型，旨在服务 HSK 4 级教学的教材开发与课堂实践。\n\n"
    "您的真实试用反馈对本研究的效度验证至关重要。"
    "诚邀您使用本系统生成一篇教案后，点击下方按钮填写 5 分制专家评估量表"
    "（约 5 分钟），以帮助完善本系统的课程适配性与学术可信度。",
    icon="ℹ️",
)
# TODO(zhangxykxa / 研究者)：把下面的 URL 替换为实际问卷星 / Google Forms 问卷链接
SURVEY_URL = "https://forms.gle/your-survey-link-here"
st.sidebar.link_button(
    "👉 点击填写 5 分制专家评估量表",
    SURVEY_URL,
    use_container_width=True,
    type="primary",
    help="新标签页打开问卷；如您还没创建问卷，先在问卷星 / Google Forms 建好，再把链接填到源码 SURVEY_URL 变量即可。",
)
st.sidebar.caption(
    "研究伦理说明：所有问卷数据仅作聚合统计与学位论文撰写，不收集任何可识别个人信息。"
)

# ============================================================================
# 锁定教学词汇：加载词库 -> 按主题+级别随机筛选 -> 主界面展示
# ============================================================================
# 加载当前大纲词库（缓存，切换版本自动重载）
try:
    vocab_df = load_vocab(syllabus_version)
except Exception as e:
    st.error(
        f"❌ 词汇表加载失败：{e}\n\n"
        "请确保仓库根目录下存在对应的 CSV 文件。"
    )
    st.stop()

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
                api_key_r, base_url_r, model_r = _resolve_api_config(
                    api_key, base_url, model, provider
                )
                if not api_key_r:
                    st.error(
                        "未获取到 API Key：请在侧边栏填写，或在云端 st.secrets 中"
                        "配置 DEFAULT_API_KEY / DEEPSEEK_API_KEY / SILICONFLOW_API_KEY。"
                    )
                elif not model_r:
                    st.error("未指定模型名：请在侧边栏填写模型名（如 deepseek-chat / deepseek-ai/DeepSeek-V3）。")
                else:
                    messages = build_generation_messages(
                        locked_words, theme_choice, syllabus_version, char_limit
                    )
                    endpoint = base_url_r or "(未配置 Base URL)"
                    st.caption(f"📡 调用：{model_r} @ {endpoint}")
                    try:
                        text = st.write_stream(
                            stream_reading_text(api_key_r, base_url_r, model_r, messages)
                        )
                    except openai.AuthenticationError as e:
                        st.error(
                            _build_auth_error_msg(
                                e, api_key_r, endpoint, model_r
                            )
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
                            st.error(_build_balance_error_msg(e, endpoint, model_r))
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
                    except UnicodeEncodeError as e:
                        st.error(
                            "🔤 编码错误：配置中含非 ASCII 字符（常见于 Key 粘贴时夹带\n"
                            "全角空格 / 隐藏字符 / 中文标点）。已自动清洗 Key/Base URL/Model\n"
                            "的非 ASCII 字符；若仍失败请重新复制纯净的 Key。\n\n"
                            f"原始报错：{e}"
                        )
                        text = ""
                    except Exception as e:  # 兜底：其它服务商返回的非标准异常
                        import traceback as _tb
                        st.error(f"生成失败（{type(e).__name__}）：{e}")
                        with st.expander("🔎 查看完整错误堆栈 (Traceback)", expanded=False):
                            st.code(_tb.format_exc(), language="python")
                        text = ""

                    if text:
                        st.session_state["generated_text"] = text
                        st.session_state["generated_topic"] = theme_choice
                        # —— 功能一：自动分析合规度并缓存，后续 rerun 复用
                        compliance = analyze_reading_compliance(
                            text, locked_words, vocab_df
                        )
                        st.session_state["compliance_analysis"] = compliance
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
                        # —— 功能一：在正文下方直接展示合规度分析报告
                        st.markdown("---")
                        render_compliance_report(compliance)
        elif st.session_state.get("generated_text"):
            # 非生成轮次：持久展示上一次生成结果，避免跨 rerun 丢失
            _persisted_text = st.session_state["generated_text"]
            st.markdown(_persisted_text)
            st.download_button(
                "⬇️ 下载文章 (TXT)",
                _persisted_text.encode("utf-8"),
                file_name="hsk4_reading.txt",
                mime="text/plain",
            )
            # 合规度报告：如果之前生成过，也持久展示（若会话里没有，再实时算一次）
            _persisted_cmp = st.session_state.get("compliance_analysis")
            if _persisted_cmp is None:
                _persisted_cmp = analyze_reading_compliance(
                    _persisted_text, locked_words, vocab_df
                )
                st.session_state["compliance_analysis"] = _persisted_cmp
            st.markdown("---")
            render_compliance_report(_persisted_cmp)

with col2:
    st.header("✍️ 2. 生成 HSK 4 单项选择题")
    st.write("根据左侧生成的文章，自动调用大模型出 1–2 道具有高干扰效度的四选一阅读理解题：")

    gen_mcq_clicked = st.button("❓ 一键出题 (Generate MCQ)", type="primary")

    # 出题按钮触发：提取左侧文章 + 目标词汇 -> 调用大模型生成 MCQ
    if gen_mcq_clicked:
        article_text = st.session_state.get("generated_text", "")
        if not article_text:
            st.warning("⚠️ 左侧尚未生成文章，请先点击「一键生成 HSK 4 级阅读」。")
        else:
            api_key_r, base_url_r, model_r = _resolve_api_config(
                api_key, base_url, model, provider
            )
            if not api_key_r:
                st.error("未获取到 API Key：请在侧边栏填写，或在云端 st.secrets 中配置 DEFAULT_API_KEY / DEEPSEEK_API_KEY / SILICONFLOW_API_KEY。")
            elif not model_r:
                st.error("未指定模型名：请在侧边栏填写模型名（如 deepseek-chat / deepseek-ai/DeepSeek-V3）。")
            else:
                mcq_messages = build_mcq_messages(article_text, locked_words, num_questions=2)
                endpoint = base_url_r or "(未配置 Base URL)"
                st.caption(f"📡 调用：{model_r} @ {endpoint}")
                with st.spinner("🔄 正在生成四选一阅读理解题（含高干扰项与解析）…"):
                    try:
                        raw_mcq = generate_mcq(api_key_r, base_url_r, model_r, mcq_messages)
                    except openai.AuthenticationError as e:
                        st.error(
                            _build_auth_error_msg(e, api_key_r, endpoint, model_r)
                        )
                        raw_mcq = ""
                    except openai.APIConnectionError as e:
                        st.error(f"🔌 无法连接 API（{endpoint}）：请检查 Base URL、网络或代理设置。\n\n{e}")
                        raw_mcq = ""
                    except openai.APIStatusError as e:
                        code = getattr(e, "status_code", None) or 0
                        if code == 402 or "Insufficient Balance" in str(e) or "insufficient_quota" in str(e):
                            st.error(_build_balance_error_msg(e, endpoint, model_r))
                        else:
                            st.error(f"API 调用失败（HTTP {code}）：{e}")
                        raw_mcq = ""
                    except Exception as e:
                        st.error(f"出题失败（{type(e).__name__}）：{e}")
                        raw_mcq = ""

                if raw_mcq:
                    mcq_list = parse_mcq_json(raw_mcq)
                    if not mcq_list:
                        st.error("⚠️ 大模型返回内容无法解析为有效题目 JSON，请重试。")
                        with st.expander("🔎 查看原始返回内容", expanded=False):
                            st.code(raw_mcq, language="json")
                    else:
                        st.session_state["mcq_questions"] = mcq_list
                        st.session_state["mcq_submitted"] = False
                        st.session_state["mcq_answers"] = {}
                        st.success(f"✨ 成功生成 {len(mcq_list)} 道题目！请作答后提交查看解析。")

    # —— 渲染交互式答题区 ——
    mcq_list = st.session_state.get("mcq_questions")
    if mcq_list:
        for idx, q in enumerate(mcq_list):
            st.markdown("---")
            st.markdown(f"#### 第 {idx + 1} 题")
            st.markdown(f"**{q['question']}**")
            option_labels = [
                f"{k}. {q['options'][k]}" for k in ("A", "B", "C", "D")
            ]
            selected = st.radio(
                f"选择你的答案（第 {idx + 1} 题）：",
                option_labels,
                key=f"mcq_radio_{idx}",
                index=None,  # 不预选
                label_visibility="collapsed",
            )
            # 记录用户选择
            if selected:
                st.session_state["mcq_answers"][idx] = selected[0]  # "A. ..." -> "A"

        st.markdown("---")
        submit_clicked = st.button("✅ 提交答案并查看解析", type="primary")

        if submit_clicked:
            st.session_state["mcq_submitted"] = True

        if st.session_state.get("mcq_submitted"):
            correct_count = 0
            for idx, q in enumerate(mcq_list):
                user_ans = st.session_state.get("mcq_answers", {}).get(idx)
                correct_ans = q["answer"]
                is_correct = user_ans == correct_ans
                if is_correct:
                    correct_count += 1

                with st.container(border=True):
                    if is_correct:
                        st.success(f"✅ 第 {idx + 1} 题 回答正确！")
                    else:
                        st.error(f"❌ 第 {idx + 1} 题回答不正确。")
                    st.markdown(
                        f"- 你的答案：**{user_ans or '（未作答）'}**"
                        f"  ｜  正确答案：**{correct_ans}**"
                    )
                    st.markdown(f"- **解析：** {q['explanation']}")
                    st.markdown(
                        f"  - **A.** {q['options']['A']}　"
                        f"**B.** {q['options']['B']}　"
                        f"**C.** {q['options']['C']}　"
                        f"**D.** {q['options']['D']}"
                    )

            score_pct = round(correct_count / len(mcq_list) * 100)
            st.markdown("---")
            if score_pct == 100:
                st.balloons()
                st.success(f"🏆 全部正确！得分 {correct_count}/{len(mcq_list)}（{score_pct}%）")
            else:
                st.info(f"📊 得分 {correct_count}/{len(mcq_list)}（{score_pct}%），再接再厉！")
    elif not gen_mcq_clicked:
        st.info("👆 请先在左侧生成文章后，点击「一键出题」生成阅读理解题。")


# ============================================================================
# 功能二：页面底部 —— 一键导出 HSK 4 备课教案讲义（Markdown）
# ============================================================================
st.write("---")
export_zone = st.container()
with export_zone:
    st.header("🧾 一键导出 HSK 4 备课教案讲义")
    st.write(
        "打包下载：分级阅读短文 + 核心生词表 + 配套单项选择题 + 教师答案解析"
        " 为一份 Markdown (.md) 文件，UTF-8 BOM 编码，复制进 Word / 粘贴进"
        " OneNote / Notion 不乱码，直接可用于备课。"
    )

    _txt = st.session_state.get("generated_text", "")
    _mcq = st.session_state.get("mcq_questions") or []
    _cmp = st.session_state.get("compliance_analysis")
    if not _txt:
        st.info(
            "👆 上方尚未生成分级阅读短文，请先在左侧点击「🚀 一键生成 HSK 4 级阅读」。"
            "（若想要 MCQ 也导出，出题后再点这里的下载按钮。）"
        )
    else:
        md_data = build_lesson_plan_markdown(
            text=_txt,
            locked_words_df=locked_words,
            syllabus_version=syllabus_version,
            topic_label=theme_choice,
            mcq_questions=_mcq,
            analysis=_cmp,
        )
        # 文件名加时间戳，避免浏览器重名覆盖；主题英文名避免中文文件名部分浏览器下载变问号
        topic_slug = "".join(
            c if c.isalnum() or c in "-_()" else "-"
            for c in _map_topic(theme_choice)
        ).strip("-_") or "theme"
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        fname = f"HSK4_Lesson_Plan_{topic_slug}_{ts}.md"

        left_btn, right_hint = st.columns([3, 2])
        with left_btn:
            st.download_button(
                label="📥 一键导出完整教案 (Markdown · 可复制进 Word)",
                data=md_data.encode("utf-8-sig"),
                file_name=fname,
                mime="text/markdown; charset=utf-8",
                type="primary",
                use_container_width=True,
                help=(
                    "建议：直接用 VSCode / Typora / Notion 打开 .md 文件，"
                    "或全选复制粘贴进 Word / PPT 排版。若您想拿给学生版（删答案），"
                    "请用任何文本编辑器打开后删除最末章节「四、Answer Key & Explanations」即可。"
                ),
            )
        with right_hint:
            mcq_ok = "✅ 已生成 MCQ" if _mcq else "⚠️ 暂未生成 MCQ（出题后再次下载会自动包含题目与解析）"
            cmp_ok = "✅ 已生成合规度报告" if _cmp else "—"
            st.markdown(
                f"- 📄 当前文章：**{_count_cjk_chars(_txt)}** 汉字\n"
                f"- 🎯 核心目标词：**{len(locked_words) if locked_words is not None else 0}** 个\n"
                f"- ❓ 选择题：**{len(_mcq)}** 道 {mcq_ok}\n"
                f"- 📊 合规度分析：{cmp_ok}"
            )
