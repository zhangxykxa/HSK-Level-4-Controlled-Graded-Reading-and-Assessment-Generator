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


def _resolve_cloud_config():
    """根据云端 ``DEFAULT_PROVIDER`` 自动解析完整 API 配置。

    读取 ``st.secrets["DEFAULT_PROVIDER"]``（默认 ``"SiliconFlow"``）确定默认服务商，
    再匹配对应的专用 Key，返回一键配置好的 (api_key, base_url, model, provider_label)。

    - SiliconFlow（只要含 ``silicon`` / ``硅基`` 任一关键字，均走国际站唯一端点）
      ``https://api.siliconflow.com/v1``（控制台：https://cloud.siliconflow.com/me/account/ak）
      也可单独用 ``SILICONFLOW_BASE_URL`` / ``SILICONFLOW_MODEL`` 覆盖默认端点/模型。
    - DeepSeek：含 ``deep`` / ``深度`` 任一关键字，需配置 ``DEEPSEEK_API_KEY``

    Returns:
        (api_key, base_url, model, provider_label)，若云端未配置则返回 ``(None, None, None, None)``
    """
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


def _resolve_api_config(api_key_input, base_url_input, model_input):
    """按优先级解析 API 配置：侧边栏手动输入 > 云端 st.secrets > 环境变量。

    云端配置由 :func:`_resolve_cloud_config` 根据 ``DEFAULT_PROVIDER``
    自动匹配服务商专用 Key 与对应 base_url / model。

    自动规整：Key 去空白/剥 ``Bearer `` 前缀、base_url 去末尾斜杠、
    model 去空白。这类粘贴瑕疵常导致 401 'Token is invalid'。

    Returns:
        (api_key, base_url, model)，缺失项为 ``None``。
    """
    cloud_key, cloud_url, cloud_model, _ = _resolve_cloud_config()

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
    _dbg_key, _dbg_url, _dbg_mdl = _resolve_api_config(api_key, base_url, model)
    _src_key = []
    if api_key and _clean_token(api_key):
        _src_key.append("侧边栏手动输入(覆盖云端)")
    if _cloud_key:
        _src_key.append(f"云端 secrets:{_cloud_label or 'DEFAULT_API_KEY'}")
    if os.environ.get("OPENAI_API_KEY") and not (_clean_token(api_key) or _cloud_key):
        _src_key.append("环境变量 OPENAI_API_KEY")
    if not _src_key and _dbg_key:
        _src_key.append("未知来源(兜底)")

    st.info(
        "🔍 每次生成时实际发出请求的配置就是下面这组：\n\n"
        f"**• Key 来源优先级**：{' → '.join(_src_key) if _src_key else '(未获取到任何 Key)'}\n"
        f"**• API Key 末 4 位**：`{_fmt_key_tail(_dbg_key)}`\n"
        f"**• 🌐 Base URL**：`{_dbg_url or '(空)'}`\n"
        f"**• 🏷️ 模型名**：`{_dbg_mdl or '(空)'}`\n\n"
        "👉 用法：把「API Key 末 4 位」拿去和对应控制台 Key 的末 4 位对比，\n"
        "   不一致就说明当前生效的不是您以为的那把 Key，检查侧边栏 / Secrets 填写处。",
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
                api_key_r, base_url_r, model_r = _resolve_api_config(api_key, base_url, model)
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
    st.write("根据左侧生成的文章，自动调用大模型出 1–2 道具有高干扰效度的四选一阅读理解题：")

    gen_mcq_clicked = st.button("❓ 一键出题 (Generate MCQ)", type="primary")

    # 出题按钮触发：提取左侧文章 + 目标词汇 -> 调用大模型生成 MCQ
    if gen_mcq_clicked:
        article_text = st.session_state.get("generated_text", "")
        if not article_text:
            st.warning("⚠️ 左侧尚未生成文章，请先点击「一键生成 HSK 4 级阅读」。")
        else:
            api_key_r, base_url_r, model_r = _resolve_api_config(api_key, base_url, model)
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
