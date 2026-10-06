# -*- coding: utf-8 -*-
"""
登录模块：用你自己的Chrome/Edge（调试端口方式）登录并读cookie。
这个方案已验证可行，不用会崩溃的内置浏览器，不破解加密存储。

流程：
1. open_browser(platform) 用调试端口启动浏览器打开平台网页
2. 你在浏览器里正常登录
3. read_cookie(platform) 通过调试端口读cookie存进数据库
"""
import sys
import os
import time
import json
import subprocess

import db
import logger
from config import PLATFORM_NAMES

DEBUG_PORT = 9222
USER_DATA_DIR = os.path.join(os.path.expanduser("~"), "hotspot_browser_profile")

PLATFORM_URLS = {
    "weibo": "https://weibo.com",
    "bilibili": "https://www.bilibili.com",
    "zhihu": "https://www.zhihu.com",
    "xiaohongshu": "https://www.xiaohongshu.com",
    "douyin": "https://www.douyin.com",
}

# 判断登录成功的关键cookie（域名 + 字段）
LOGIN_CHECK = {
    "weibo": ("weibo.com", "SUB"),
    "bilibili": ("bilibili.com", "SESSDATA"),
    "zhihu": ("zhihu.com", "z_c0"),
    "xiaohongshu": ("xiaohongshu.com", "web_session"),
}

_browser_proc = None


def find_browser():
    """找Chrome或Edge"""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _debug_port_alive():
    """检查调试端口是否已有浏览器在跑"""
    try:
        import requests
        requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def open_browser(platform):
    """用调试端口启动浏览器打开平台网页。如果调试浏览器已在跑，复用它开新标签。"""
    global _browser_proc
    try:
        browser = find_browser()
        if not browser:
            logger.error("没找到Chrome或Edge浏览器")
            return {"ok": False, "msg": "没找到Chrome或Edge，请确认已安装其中一个"}

        url = PLATFORM_URLS.get(platform, "https://www.baidu.com")
        db.save_credential(platform, "", status="登录中")

        if _debug_port_alive():
            # 调试浏览器已在运行，用它开新标签（不再启动新进程，避免端口冲突）
            try:
                import requests
                requests.put(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", timeout=3)
            except Exception:
                # 有些版本要GET
                try:
                    requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", timeout=3)
                except Exception:
                    pass
            logger.action(platform, "打开登录标签(复用调试浏览器)", "成功")
            return {"ok": True, "msg": f"已在登录浏览器里打开{PLATFORM_NAMES.get(platform, platform)}，请登录后回来点【完成】"}
        else:
            # 首次启动调试浏览器
            _browser_proc = subprocess.Popen([
                browser,
                f"--remote-debugging-port={DEBUG_PORT}",
                f"--user-data-dir={USER_DATA_DIR}",
                "--remote-allow-origins=*",
                url,
            ])
            logger.action(platform, "启动登录浏览器", "成功")
            return {"ok": True, "msg": f"已弹出登录浏览器窗口，请在【那个窗口】里登录{PLATFORM_NAMES.get(platform, platform)}，登录后回来点【完成】"}
    except Exception as e:
        logger.error(f"打开{platform}登录浏览器失败", e)
        return {"ok": False, "msg": f"打开浏览器出错: {type(e).__name__}"}


def read_cookie(platform):
    """
    通过调试端口读cookie。用CDP的HTTP-over-websocket，但对连接失败给清楚提示。
    """
    try:
        import requests
    except ImportError:
        return {"ok": False, "msg": "缺少requests库，请重新运行首次安装.bat"}

    # 1. 先确认调试端口活着
    try:
        version = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=5).json()
    except Exception:
        logger.error(f"调试端口{DEBUG_PORT}连不上，浏览器可能已关闭或不是用调试端口启动的")
        return {"ok": False, "msg": "读不到浏览器。请确认：你是点软件的【登录】按钮打开的那个浏览器窗口里登录的，而且那个窗口还开着。如果你关了它，请重新点【登录】。"}

    domain, check_field = LOGIN_CHECK.get(platform, ("", ""))

    try:
        from websocket import create_connection
    except ImportError:
        return {"ok": False, "msg": "缺少websocket-client库，请重新运行首次安装.bat"}

    # 优先连该平台对应的标签页；标签页读不到再用浏览器级
    cookies = []
    tried_detail = []

    def read_via_ws(ws_url, use_storage=False):
        """连一个ws，用Storage.getCookies（浏览器级）或Network.getAllCookies读cookie"""
        ws = create_connection(ws_url, timeout=10)
        try:
            # 先启用Network域（有些版本不启用读不到）
            ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
            ws.recv()
            # 方法A: Storage.getCookies（不带browserContextId=整个浏览器）
            ws.send(json.dumps({"id": 2, "method": "Storage.getCookies"}))
            r = json.loads(ws.recv())
            ck = r.get("result", {}).get("cookies", [])
            if ck:
                return ck
            # 方法B: Network.getAllCookies
            ws.send(json.dumps({"id": 3, "method": "Network.getAllCookies"}))
            r = json.loads(ws.recv())
            ck = r.get("result", {}).get("cookies", [])
            return ck
        finally:
            try: ws.close()
            except Exception: pass

    # 1) 连目标平台的标签页
    try:
        tabs = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5).json()
        page_tabs = [t for t in tabs if t.get("type") == "page"]
        target = None
        for tab in page_tabs:
            if domain and domain in tab.get("url", ""):
                target = tab; break
        if target and target.get("webSocketDebuggerUrl"):
            try:
                cookies = read_via_ws(target["webSocketDebuggerUrl"])
                tried_detail.append(f"标签页读到{len(cookies)}个")
            except Exception as e:
                tried_detail.append(f"标签页读取异常:{type(e).__name__}")
    except Exception as e:
        tried_detail.append(f"取标签页列表失败:{type(e).__name__}")

    # 2) 标签页没读到，用浏览器级连接
    if not cookies:
        ws_url = version.get("webSocketDebuggerUrl")
        if ws_url:
            try:
                cookies = read_via_ws(ws_url)
                tried_detail.append(f"浏览器级读到{len(cookies)}个")
            except Exception as e:
                tried_detail.append(f"浏览器级读取异常:{type(e).__name__}")

    logger.info(f"{platform}读cookie尝试详情: {'; '.join(tried_detail)}")

    if not cookies:
        return {"ok": False, "msg": f"没读到任何cookie。诊断: {'; '.join(tried_detail)}。请确认登录浏览器窗口开着且该平台标签页在。"}
    plat_cookies = [c for c in cookies if domain in c.get("domain", "")]
    if not plat_cookies:
        plat_cookies = cookies

    names = [c["name"] for c in plat_cookies]
    if check_field and check_field not in names:
        logger.action(platform, "读取cookie", f"未检测到登录标志{check_field}，共{len(plat_cookies)}个cookie")
        return {"ok": False, "msg": f"读到了{len(plat_cookies)}个cookie，但没有登录标志({check_field})，说明这个浏览器里还没登录{PLATFORM_NAMES.get(platform, platform)}。请在软件打开的那个浏览器里登录后再点完成。"}

    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in plat_cookies)
    db.save_credential(platform, cookie_str, status="有效")
    logger.action(platform, "读取cookie", f"成功{len(plat_cookies)}个")
    return {"ok": True, "msg": f"登录成功！读到{len(plat_cookies)}个cookie已保存"}


def logout(platform):
    """
    退出登录：
    1. 删掉数据库里存的该平台cookie（状态改回“未登录”）
    2. 通过调试端口清掉浏览器里该平台域名下的cookie，
       这样别人用这台电脑打开该平台不会自动是你的账号。
    如果浏览器没开着，也至少完成第1步（数据库层面已退出）。
    """
    # 1. 数据库层面退出
    try:
        db.clear_credential(platform)
    except Exception as e:
        logger.error(f"清除{platform}数据库cookie失败", e)

    # 2. 浏览器层面清cookie
    domain, _ = LOGIN_CHECK.get(platform, ("", ""))
    browser_cleared = False
    try:
        import requests
        requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=3)
        try:
            from websocket import create_connection
            ver = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=3).json()
            ws_url = ver.get("webSocketDebuggerUrl")
            if ws_url:
                ws = create_connection(ws_url, timeout=10)
                try:
                    ws.send(json.dumps({"id": 1, "method": "Network.enable"})); ws.recv()
                    # 取全部cookie，删掉该平台域名下的
                    ws.send(json.dumps({"id": 2, "method": "Network.getAllCookies"}))
                    r = json.loads(ws.recv())
                    cookies = r.get("result", {}).get("cookies", [])
                    del_id = 3
                    for c in cookies:
                        if domain and domain in c.get("domain", ""):
                            ws.send(json.dumps({
                                "id": del_id, "method": "Network.deleteCookies",
                                "params": {"name": c.get("name"), "domain": c.get("domain"),
                                           "path": c.get("path", "/")}
                            }))
                            try: ws.recv()
                            except Exception: pass
                            del_id += 1
                    browser_cleared = True
                finally:
                    try: ws.close()
                    except Exception: pass
        except Exception as e:
            logger.warn(f"浏览器清cookie未完成（数据库已退出）: {type(e).__name__}")
    except Exception:
        pass  # 浏览器没开，数据库退出即可

    logger.action(platform, "退出登录", "浏览器cookie已清" if browser_cleared else "仅数据库退出")
    if browser_cleared:
        msg = f"已退出{PLATFORM_NAMES.get(platform, platform)}，浏览器里的登录也清掉了，别人打开不会是你的账号。"
    else:
        msg = f"已退出{PLATFORM_NAMES.get(platform, platform)}（软件层面）。浏览器窗口没开着，如需彻底清除浏览器登录，请打开软件浏览器后再点一次退出。"
    return {"ok": True, "msg": msg}


if __name__ == "__main__":
    plat = sys.argv[1] if len(sys.argv) > 1 else "weibo"
    print(open_browser(plat))
    input("登录后按回车读cookie...")
    print(read_cookie(plat))
