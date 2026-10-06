# -*- coding: utf-8 -*-
"""
B站五个榜单抓取器：综合热门、每周必看、入站必刷、排行榜、全站音乐榜
每个榜用各自的接口，带详细日志。
"""
import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import USER_AGENT, REQUEST_TIMEOUT
import db
import logger


def _headers():
    h = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"}
    cred = db.get_credential("bilibili")
    if cred and cred.get("cookie"):
        h["Cookie"] = cred["cookie"]
    return h


def _video_item(item, category, rank_no=0):
    title = item.get("title", "")
    if not title:
        return None
    stat = item.get("stat", {})
    bvid = item.get("bvid", "")
    play = stat.get("view", 0)
    like = stat.get("like", 0)
    danmaku = stat.get("danmaku", 0)
    # 发布时间（pubdate是时间戳）
    pubdate = item.get("pubdate", 0)
    pub_time = ""
    if pubdate:
        from datetime import datetime as _dt
        try:
            pub_time = _dt.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pub_time = ""
    return {
        "title": title,
        "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
        "category": category,
        "heat": play,          # 用播放量当热度
        "likes": like,
        "pub_time": pub_time,
        "rank_no": rank_no,
        "extra": json.dumps({"play": play, "like": like, "danmaku": danmaku}, ensure_ascii=False),
    }


def fetch_popular():
    """综合热门"""
    url = "https://api.bilibili.com/x/web-interface/popular"
    resp = requests.get(url, headers=_headers(), params={"ps": 30, "pn": 1}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"综合热门接口错误: {data.get('message')}")
    out = []
    for i, item in enumerate(data.get("data", {}).get("list", [])):
        v = _video_item(item, "综合热门", i+1)
        if v: out.append(v)
    return out


def fetch_weekly():
    """每周必看（取最新一期）"""
    url = "https://api.bilibili.com/x/web-interface/popular/series/list"
    resp = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"每周必看列表接口错误: {data.get('message')}")
    series_list = data.get("data", {}).get("list", [])
    if not series_list:
        return []
    latest = series_list[0].get("number")
    # 取最新一期的视频
    url2 = "https://api.bilibili.com/x/web-interface/popular/series/one"
    resp2 = requests.get(url2, headers=_headers(), params={"number": latest}, timeout=REQUEST_TIMEOUT)
    resp2.raise_for_status()
    data2 = resp2.json()
    out = []
    for i, item in enumerate(data2.get("data", {}).get("list", [])):
        v = _video_item(item, "每周必看", i+1)
        if v: out.append(v)
    return out


def fetch_precious():
    """入站必刷"""
    url = "https://api.bilibili.com/x/web-interface/popular/precious"
    resp = requests.get(url, headers=_headers(), params={"page_size": 30, "page": 1}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"入站必刷接口错误: {data.get('message')}")
    out = []
    for i, item in enumerate(data.get("data", {}).get("list", [])):
        v = _video_item(item, "入站必刷", i+1)
        if v: out.append(v)
    return out


def fetch_ranking():
    """排行榜（全站）"""
    url = "https://api.bilibili.com/x/web-interface/ranking/v2"
    resp = requests.get(url, headers=_headers(), params={"rid": 0, "type": "all"}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"排行榜接口错误: {data.get('message')}")
    out = []
    for i, item in enumerate(data.get("data", {}).get("list", [])):
        v = _video_item(item, "排行榜", i+1)
        if v: out.append(v)
    return out


def fetch_music():
    """全站音乐榜"""
    url = "https://api.bilibili.com/x/web-interface/ranking/v2"
    resp = requests.get(url, headers=_headers(), params={"rid": 3, "type": "all"}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"音乐榜接口错误: {data.get('message')}")
    out = []
    for i, item in enumerate(data.get("data", {}).get("list", [])):
        v = _video_item(item, "音乐榜", i+1)
        if v: out.append(v)
    return out


BOARDS = [
    ("综合热门", fetch_popular),
    ("每周必看", fetch_weekly),
    ("入站必刷", fetch_precious),
    ("排行榜", fetch_ranking),
    ("音乐榜", fetch_music),
]


def fetch_bilibili_all():
    """抓B站五个榜，每个独立try，一个失败不影响其他，全部记日志"""
    all_results = []
    for name, fn in BOARDS:
        try:
            items = fn()
            all_results.extend(items)
            logger.action("bilibili", f"抓取{name}", f"成功{len(items)}条")
        except Exception as e:
            logger.error(f"B站[{name}]抓取失败", e)
            print(f"  B站[{name}]失败: {e}")
    return all_results


if __name__ == "__main__":
    items = fetch_bilibili_all()
    print(f"B站五榜共抓到 {len(items)} 条")
    from collections import Counter
    for cate, n in Counter(it["category"] for it in items).items():
        print(f"  {cate}: {n}条")
