"""HSK 分级阅读生成器 - API Key 快速诊断工具

使用方法：
  1. 先在 .streamlit/secrets.toml 中填入真实 API Key
  2. 运行: python diagnose_api_keys.py
  3. 根据输出判断 Key 是否有效

注意：本脚本仅做最小化调用（模型列表查询 + 1 token 测试），不会产生明显费用。
"""

import sys
from pathlib import Path

import httpx

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # Python 3.10 及以下：pip install tomli
    except ModuleNotFoundError:
        print("[X] 缺少 TOML 解析库。")
        print("    解决方案：pip install tomli")
        sys.exit(1)

SECRETS_PATH = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"


def load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        print(f"[X] 未找到 secrets 文件：{SECRETS_PATH}")
        print("    请先创建 .streamlit/secrets.toml 并填入 API Key。")
        sys.exit(1)
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f)


PLACEHOLDERS = ("<替换为您的",)  # 任何以该前缀开头视为未填写


def is_placeholder(v: str) -> bool:
    return (not v) or any(v.startswith(p) for p in PLACEHOLDERS)


def test_deepseek(api_key: str):
    print("\n=== 测试 DeepSeek API ===")
    base = "https://api.deepseek.com"
    headers = {"Authorization": f"Bearer {api_key.strip()}"}

    # 1) 查模型列表（轻量，可验证 Key 是否有效）
    try:
        r = httpx.get(f"{base}/models", headers=headers, timeout=15)
        code = r.status_code
        print(f"  查询模型列表：HTTP {code}")
        if code == 200:
            data = r.json()
            models = [m["id"] for m in data.get("data", [])]
            print(f"  ✅ Key 有效！可用模型：{', '.join(models[:8])}{'...' if len(models) > 8 else ''}")
        elif code == 401:
            body = r.text[:500]
            print(f"  ❌ 鉴权失败 (401)：{body}")
            print("     常见原因：")
            print("     1. Key 填写错误 / 复制不完整（请检查首尾是否有隐藏字符）")
            print("     2. 该 Key 已在 DeepSeek 控制台被删除")
            print("     3. 这不是 DeepSeek 的 Key（把 SiliconFlow/OpenAI 的 Key 填到了 DEEPSEEK_API_KEY）")
        else:
            print(f"  ⚠️  其他错误：HTTP {code} -> {r.text[:500]}")
    except Exception as e:
        print(f"  ⚠️  请求异常：{e}")


def test_siliconflow(api_key: str):
    """测试 SiliconFlow 国际站 Key。

    唯一站点：控制台 https://cloud.siliconflow.com/me/account/ak
              API Base URL = https://api.siliconflow.com/v1
    """
    label = "国际站 (siliconflow.com)"
    base = "https://api.siliconflow.com/v1"
    print(f"\n=== 测试 SiliconFlow {label} API ===")
    print(f"  端点：{base}")
    headers = {"Authorization": f"Bearer {api_key.strip()}"}

    try:
        r = httpx.get(f"{base}/models", headers=headers, timeout=15)
        code = r.status_code
        print(f"  查询模型列表：HTTP {code}")
        if code == 200:
            data = r.json()
            models = [m["id"] for m in data.get("data", [])]
            print(
                f"  ✅ Key 有效！可用模型：{', '.join(models[:8])}{'...' if len(models) > 8 else ''}"
            )
        elif code == 401:
            body = r.text[:500]
            print(f"  ❌ 鉴权失败 (401)：{body}")
            print("     常见原因：")
            print("     1. Key 不是从国际站控制台获取的（Key 仅在对应站点有效）")
            print("        → 请确认：控制台必须是 cloud.siliconflow.com（国际站）")
            print("     2. Key 已被删除 / 复制不完整 / 被修改")
            print("     3. 账号未完成邮箱验证 / 手机号验证")
        else:
            print(f"  ⚠️  其他错误：HTTP {code} -> {r.text[:500]}")
    except Exception as e:
        print(f"  ⚠️  请求异常：{e}")


def main():
    cfg = load_secrets()
    default_provider = cfg.get("DEFAULT_PROVIDER", "SiliconFlow")
    print(f"默认服务商（DEFAULT_PROVIDER）：{default_provider}")

    deepseek_key = cfg.get("DEEPSEEK_API_KEY", "")
    siliconflow_key = cfg.get("SILICONFLOW_API_KEY", "")

    if is_placeholder(deepseek_key):
        print("\n⚠️  DEEPSEEK_API_KEY 尚未填写，跳过 DeepSeek 测试。")
    else:
        test_deepseek(deepseek_key)

    if is_placeholder(siliconflow_key):
        print("\n⚠️  SILICONFLOW_API_KEY 尚未填写，跳过 SiliconFlow 测试。")
    else:
        # 仅测国际站 siliconflow.com
        test_siliconflow(siliconflow_key)

    print("\n=== 下一步建议 ===")
    print("  Key 验证通过后，启动应用：")
    print("    streamlit run app.py")
    print("  侧边栏将自动显示「✅ 默认云端服务已就绪」，无需再手动填 Key。")


if __name__ == "__main__":
    main()
