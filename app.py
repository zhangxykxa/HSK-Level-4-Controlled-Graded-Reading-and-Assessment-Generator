import streamlit as st
import pandas as pd
import openai

# 1. 页面基本配置
st.set_page_config(page_title="HSK 4 Graded Material Generator", layout="wide")

st.title("📚 HSK 4 级受控分级阅读与测评生成器")
st.subheader("Curriculum-Adaptive Reading & Exercise Generator (HSK 2.0 vs 3.0)")
st.write("---")

# 2. 侧边栏（Sidebar）- 教学参数控制面板
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

# API 密钥配置 (可输入你自己的 Key)
api_key = st.sidebar.text_input("🔑 输入 OpenAI/API Key (或使用默认):", type="password")

st.sidebar.write("---")
st.sidebar.markdown("💡 *本原型专为语言教师备课设计，生成材料严格受控于所选大纲词库。*")

# 3. 主界面布局 - 左右分栏
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
