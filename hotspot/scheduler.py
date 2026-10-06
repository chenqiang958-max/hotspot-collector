# -*- coding: utf-8 -*-
"""调度器：抓各平台，带日志和监控词标记"""
import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import logger
from tagger import tag_content
from config import WATCH_KEYWORDS

from scrapers import weibo, bilibili, zhihu, douyin

FETCHERS = {
    "weibo": weibo.fetch_weibo_all,
    "bilibili": bilibili.fetch_bilibili_all,
    "zhihu": zhihu.fetch_zhihu_all,
    "douyin": douyin.fetch_douyin_all,
    # 小红书的API方式会被签名校验拦截(406)，改用地址栏/读页面功能抓取
}


def is_watched(title):
    return any(kw in title for kw in WATCH_KEYWORDS)


def run_platform(platform):
    fetch_fn = FETCHERS.get(platform)
    if not fetch_fn:
        return False
    try:
        items = fetch_fn()
        for it in items:
            title = it["title"]
            tags = set(t for t in tag_content(title).split(",") if t)
            if is_watched(title):
                tags.add("重点关注")
            tag_str = ",".join(sorted(tags))
            db.upsert_item(
                platform=platform, title=title, url=it.get("url", ""),
                category=it.get("category", ""), extra=it.get("extra", ""),
                tags=tag_str,
                heat=it.get("heat", 0), likes=it.get("likes", 0),
                pub_time=it.get("pub_time", ""), rank_no=it.get("rank_no", 0),
            )
        db.log_fetch(platform, "success", item_count=len(items))
        logger.action(platform, "整轮抓取", f"成功{len(items)}条")
        print(f"[{platform}] 成功，{len(items)} 条")
        # 统计各榜单条数
        from collections import Counter
        cate_cnt = Counter(it.get("category","") for it in items)
        return {"ok": True, "platform": platform, "count": len(items), "by_category": dict(cate_cnt)}
    except Exception as e:
        db.log_fetch(platform, "fail", error_msg=str(e))
        logger.error(f"{platform}整轮抓取失败", e)
        print(f"[{platform}] 失败: {e}")
        return {"ok": False, "platform": platform, "count": 0, "error": str(e)}


def run_once(platforms=None):
    db.init_db()
    if platforms is None:
        platforms = list(FETCHERS.keys())
    logger.separator("开始一轮抓取")
    print(f"=== 开始抓取 {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    results = []
    for p in platforms:
        r = run_platform(p)
        results.append(r)
    try:
        db.snapshot_trends()
    except Exception as e:
        logger.error("趋势快照失败", e)
    print("=== 本轮抓取结束 ===")
    return results


def run_loop(interval_minutes=60):
    while True:
        run_once()
        print(f"休眠 {interval_minutes} 分钟...")
        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--only", type=str, default="")
    args = parser.parse_args()
    only = [p.strip() for p in args.only.split(",") if p.strip()] if args.only else None
    if args.loop:
        run_loop(args.interval)
    else:
        run_once(only)
