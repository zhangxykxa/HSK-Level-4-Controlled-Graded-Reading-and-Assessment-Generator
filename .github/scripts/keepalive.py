"""用真实浏览器访问 Streamlit 应用，防止免费层因闲置进入休眠（Zzz）。

为什么不能只用 curl / UptimeRobot：
    Streamlit Community Cloud 的应用闲置 12 小时即休眠。休眠后返回的任何
    HTTP 200 都只是平台 nginx 托管的静态 SPA 外壳，Python 进程根本没启动，
    因此纯 HTTP 探测既不能保活也不能唤醒（会得到一个"假成功"）。
    只有真正执行 JS 并建立 WebSocket 会话的浏览器访问才算"活动"。

本脚本用 Playwright 无头 Chromium：
    1. 打开应用页面；
    2. 若出现 "Yes, get this app back up!" 插页按钮，说明已休眠 -> 自动点击唤醒；
    3. 等待应用容器渲染完成；
    4. 复验应用容器健康接口 /~/+/_stcore/health 是否为 ok。
"""

import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

APP_URL = (
    "https://hsk-level-4-controlled-graded-reading-and-assessment-generator.streamlit.app"
)
# 注意：必须带 /~/+/ 前缀。不带前缀的 /_stcore/health 会被平台 nginx 兜底路由到
# 静态外壳，永远返回 200，无法反映应用容器状态。
HEALTH_URL = APP_URL + "/~/+/_stcore/health"

WAKE_BUTTON = "Yes, get this app back up!"
APP_CONTAINER = "[data-testid='stAppViewContainer']"


def health_text() -> str:
    """读取应用容器健康接口；异常时返回可读的错误描述而不是抛出。"""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001 - 诊断用途，需要保留任何异常文本
        return f"<{type(exc).__name__}: {exc}>"


def app_rendered(page) -> bool:
    """判断应用是否真的渲染完成。

    注意：页面顶部是平台 SPA，应用本体被嵌在下一层的 /~/+/ iframe 里，
    所以必须跨帧查找，只看主 frame 会永远找不到。
    """
    for frame in page.frames:
        try:
            if frame.locator(APP_CONTAINER).count() > 0:
                return True
        except Exception:  # noqa: BLE001 - 跨域帧查询失败时跳过
            continue
    return False


def probe_state(page, timeout_ms: int) -> str:
    """轮询页面，判断它最终停在哪个已知状态。

    返回 "running"（应用已渲染）/ "sleeping"（休眠插页）/ "unknown"（超时）。
    """
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if app_rendered(page):
            return "running"
        if page.get_by_role("button", name=WAKE_BUTTON).count() > 0:
            return "sleeping"
        page.wait_for_timeout(1_000)
    return "unknown"


def main() -> int:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 访问前 health: {health_text()}")

    rendered = False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=120_000)

        state = probe_state(page, 30_000)

        if state == "sleeping":
            print("检测到应用已休眠（Zzz）—— 自动点击唤醒按钮")
            page.get_by_role("button", name=WAKE_BUTTON).first.click()
            state = probe_state(page, 180_000)
        elif state == "running":
            print("应用未休眠，正常渲染")
        else:
            print("::warning::30 秒内未识别到明确状态，继续等待渲染")

        if state == "running":
            rendered = True
        else:
            rendered = app_rendered(page)

        browser.close()

    if rendered:
        print("页面已渲染（stAppViewContainer 出现）")
    else:
        print("::warning::未检测到页面渲染，应用可能仍在唤醒中")

    # 复验容器健康接口：这是唯一能确认"Python 进程真的活着"的信号。
    for _ in range(12):  # 最多再等约 1 分钟
        if health_text() == "ok":
            print("✅ 保活成功：/~/+/_stcore/health = ok")
            return 0
        time.sleep(5)

    print(f"::error::保活失败：health 未返回 ok（实际: {health_text()}）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
