# -*- coding: utf-8 -*-
"""
微博热搜抓取器（只抓热搜总榜，已含各类热词）
带详细日志：成功记条数，失败记状态码+返回内容片段，方便排查。
"""
import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import USER_AGENT, REQUEST_TIMEOUT
import db
import logger

HOT_SEARCH_URL = "https://weibo.com/ajax/side/hotSearch"


def _headers():
    h = {"User-Agent": USER_AGENT, "Referer": "https://weibo.com/"}
    cred = db.get_credential("weibo")
    if cred and cred.get("cookie"):
        h["Cookie"] = cred["cookie"]
    return h


# 微博分类榜（文娱/社会等）用 hottimeline 接口，不同 containerid
WEIBO_CATEGORIES = {
    "文娱": "v2_ctg1_4288",
    "社会": "v2_ctg1_5088",
    "科技": "v2_ctg1_5069",
    "体育": "v2_ctg1_1288",
    "游戏": "v2_ctg1_5169",
}


def fetch_category(cate_name, cid):
    """抓某个分类的热门（失败返回空列表，不影响热搜总榜）"""
    url = "https://weibo.com/ajax/feed/hottimeline"
    params = {"since_id": 0, "refresh": 0, "group_id": cid, "containerid": cid, "extparam": "discover", "max_id": 0, "count": 15}
    resp = requests.get(url, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
    if resp.status_code != 200:
        logger.warn(f"微博分类[{cate_name}]状态码{resp.status_code}")
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    results = []
    for item in data.get("statuses", [])[:15]:
        text = item.get("text_raw", "") or item.get("text", "")
        import re as _re
        text = _re.sub(r"<[^>]+>", "", text)  # 去HTML标签
        title = text[:50].replace("\n", " ").strip()
        if title:
            results.append({"title": title, "url": "", "category": f"微博-{cate_name}", "extra": ""})
    return results


def fetch_weibo_all():
    """抓微博热搜总榜。失败时抛异常，异常信息含详细诊断。"""
    try:
        resp = requests.get(HOT_SEARCH_URL, headers=_headers(), timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        logger.error(f"微博热搜请求失败（网络层）: {type(e).__name__}", e)
        raise

    if resp.status_code != 200:
        detail = f"微博热搜返回状态码{resp.status_code}，内容片段: {resp.text[:200]}"
        logger.error(detail)
        resp.raise_for_status()

    try:
        data = resp.json()
    except Exception as e:
        logger.error(f"微博热搜返回的不是JSON，内容片段: {resp.text[:200]}", e)
        raise

    results = []
    realtime = data.get("data", {}).get("realtime", [])
    if not realtime:
        logger.warn(f"微博热搜返回了但realtime为空，可能接口结构变了。data键: {list(data.get('data', {}).keys())}")

    for i, item in enumerate(realtime):
        title = item.get("word") or item.get("word_scheme", "")
        if not title:
            continue
        results.append({
            "title": title,
            "url": f"https://s.weibo.com/weibo?q={requests.utils.quote(title)}",
            "category": "微博-热搜",
            "heat": item.get("num", 0),   # 热搜热度值
            "rank_no": i + 1,             # 榜单排名
            "extra": json.dumps({"hot": item.get("num", 0)}, ensure_ascii=False),
        })

    logger.action("weibo", "抓取热搜", f"成功{len(results)}条")
    # 分类改用地址栏手动抓（在浏览器打开分类页面更可靠），不再自动抓那些容易失效的接口
    return results


if __name__ == "__main__":
    try:
        items = fetch_weibo_all()
        print(f"微博热搜抓到 {len(items)} 条")
        for it in items[:5]:
            print(f"  {it['title']}")
    except Exception as e:
        print(f"抓取失败: {e}")
