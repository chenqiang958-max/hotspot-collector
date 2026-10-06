# -*- coding: utf-8 -*-
"""
统一启动入口：
- 后台起Flask（数据面板）
- 用一个独立的调试浏览器打开操作页面（127.0.0.1:5000）
- 之后所有登录都在这同一个浏览器里进行，不跟你平时的Chrome混
"""
import sys
import os
import time
import threading
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import logger
from login import find_browser, DEBUG_PORT, USER_DATA_DIR


def start_flask():
    try:
        from webapp import app
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        logger.error("Flask启动失败", e)
        print(f"数据面板启动失败: {e}")


def debug_port_alive():
    try:
        import requests
        requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def main():
    logger.separator("软件启动")
    db.init_db()
    db.seed_default_filter_words()
    try:
        removed = db.prune_old_data()
        if removed:
            logger.info(f"启动清理：删除了{removed}条超过保留天数的老数据")
    except Exception as e:
        logger.error("启动清理老数据失败", e)
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    print("正在启动数据面板...")
    time.sleep(2)

    # 2. 用独立调试浏览器打开操作页面
    browser = find_browser()
    panel_url = "http://127.0.0.1:5000"

    if not browser:
        print("没找到Chrome/Edge，请用普通浏览器手动打开：" + panel_url)
        logger.warn("没找到浏览器，用户需手动打开面板")
    else:
        if debug_port_alive():
            # 调试浏览器已在跑，新开标签打开面板
            try:
                import requests
                requests.put(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{panel_url}", timeout=3)
            except Exception:
                try:
                    requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{panel_url}", timeout=3)
                except Exception:
                    pass
            print("已在登录浏览器里打开操作页面")
        else:
            # 启动独立调试浏览器，打开操作页面
            subprocess.Popen([
                browser,
                f"--remote-debugging-port={DEBUG_PORT}",
                f"--user-data-dir={USER_DATA_DIR}",
                "--remote-allow-origins=*",
                panel_url,
            ])
            print("已用独立浏览器打开操作页面")
        logger.action("软件", "启动并打开操作页面", "成功")

    print()
    print("=" * 50)
    print("软件已启动！操作页面在刚打开的浏览器窗口里。")
    print("在那个窗口里：点平台登录 → 登录 → 点完成 → 抓取")
    print("本命令行窗口请勿关闭（关了软件就停了）")
    print("=" * 50)

    # 保持运行
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("软件已停止")


if __name__ == "__main__":
    main()
