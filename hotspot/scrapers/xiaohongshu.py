# -*- coding: utf-8 -*-
"""
小红书频道抓取器：抓首页各频道（穿搭/美食/职场等，除"推荐"外）
必须登录（cookie从数据库读，用Chrome调试端口方案登录后存进来）。
小红书反爬严，即使登录也可能被签名校验拦，抓不到会详细记日志。
"""
import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import USER_AGENT, REQUEST_TIMEOUT, XIAOHONGSHU_CHANNELS
import db
import logger


def _headers():
    h = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.xiaohongshu.com/",
        "Content-Type": "application/json;charset=UTF-8",
    }
    cred = db.get_credential("xiaohongshu")
    if cred and cred.get("cookie"):
        h["Cookie"] = cred["cookie"]
    return h


# 小红书频道对应的channel_id（首页频道）
CHANNEL_IDS = {
    "穿搭": "homefeed.fashion_v3",
    "美食": "homefeed.food_v3",
    "彩妆": "homefeed.cosmetics_v3",
    "影视": "homefeed.movie_and_tv_v3",
    "职场": "homefeed.career_v3",
    "情感": "homefeed.love_v3",
    "家居": "homefeed.household_product_v3",
    "游戏": "homefeed.gaming_v3",
    "旅行": "homefeed.travel_v3",
    "健身": "homefeed.fitness_v3",
}


def fetch_channel(channel_name, channel_id):
    """抓某个频道的内容"""
    cred = db.get_credential("xiaohongshu")
    if not cred or not cred.get("cookie"):
        raise RuntimeError("小红书未登录，请先登录小红书")

    url = "https://edith.xiaohongshu.com/api/sns/web/v1/homefeed"
    payload = {
        "cursor_score": "",
        "num": 20,
        "refresh_type": 1,
        "note_index": 0,
        "unread_begin_note_id": "",
        "unread_end_note_id": "",
        "unread_note_count": 0,
        "category": channel_id,
        "search_key": "",
        "need_num": 20,
        "image_formats": ["jpg", "webp", "avif"],
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=REQUEST_TIMEOUT)

    if resp.status_code in (401, 403, 406):
        raise RuntimeError(f"小红书[{channel_name}]被拒(状态码{resp.status_code})，可能是登录过期或签名校验拦截")
    resp.raise_for_status()

    data = resp.json()
    if not data.get("success", True):
        raise RuntimeError(f"小红书[{channel_name}]接口返回失败: {data.get('msg', '未知')}")

    results = []
    for item in data.get("data", {}).get("items", []):
        note = item.get("note_card", {})
        title = note.get("display_title", "")
        if not title:
            continue
        results.append({
            "title": title,
            "url": f"https://www.xiaohongshu.com/explore/{item.get('id', '')}",
            "category": f"小红书-{channel_name}",
            "extra": "",
        })
    return results


def fetch_xiaohongshu_all():
    """抓小红书各频道（除推荐外）。每个频道独立try，详细记日志。"""
    all_results = []
    cred = db.get_credential("xiaohongshu")
    if not cred or not cred.get("cookie"):
        logger.warn("小红书未登录，跳过。请先在软件里登录小红书")
        raise RuntimeError("小红书未登录，请先点小红书的登录按钮")

    for channel_name in XIAOHONGSHU_CHANNELS:
        channel_id = CHANNEL_IDS.get(channel_name)
        if not channel_id:
            continue
        try:
            items = fetch_channel(channel_name, channel_id)
            all_results.extend(items)
            logger.action("xiaohongshu", f"抓取{channel_name}", f"成功{len(items)}条")
        except Exception as e:
            logger.error(f"小红书[{channel_name}]抓取失败", e)
            print(f"  小红书[{channel_name}]失败: {e}")

    return all_results


if __name__ == "__main__":
    try:
        items = fetch_xiaohongshu_all()
        print(f"小红书共抓到 {len(items)} 条")
    except Exception as e:
        print(f"抓取失败: {e}")
