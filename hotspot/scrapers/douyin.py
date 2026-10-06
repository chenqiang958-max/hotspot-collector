# -*- coding: utf-8 -*-
"""
抖音榜单抓取器：热点榜、种草榜、娱乐榜、社会榜、挑战榜
走抖音热榜落地页用的官方接口，不需要登录/cookie。
接口结构参考自用户自测过的 hot_test.py，这里改造成跟 bilibili.py 一样的
"每个榜独立try、一个失败不影响其他"的写法，接入到主软件的抓取流程里。
"""
import sys
import os
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import REQUEST_TIMEOUT
import logger

DOUYIN_OFFICIAL_LIST = (
    "https://so-landing.douyin.com/aweme/v1/hot/search/list/"
    "?aid=581610&detail_list=1&board_type={bt}&board_sub_type={bst}"
    "&need_board_tab=true&need_covid_tab=false&version_code=32.3.0"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://so-landing.douyin.com/landings/hotlist",
}

# 榜单名 -> (board_type, board_sub_type)
BOARD_PARAM = {
    "热点榜": ("0", ""),
    "种草榜": ("2", "seeding"),
    "娱乐榜": ("2", "2"),
    "社会榜": ("2", "4"),
    "挑战榜": ("2", "hotspot_challenge"),
}


def _fetch_board(board_name):
    bt, bst = BOARD_PARAM[board_name]
    url = DOUYIN_OFFICIAL_LIST.format(bt=bt, bst=bst)
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status_code") not in (0, None):
        raise RuntimeError(f"抖音[{board_name}]接口返回status_code={payload.get('status_code')}")

    rows = (payload.get("data") or {}).get("word_list") or []
    if not rows:
        raise RuntimeError(f"抖音[{board_name}]word_list为空，可能接口结构变了")

    out = []
    for i, row in enumerate(rows, 1):
        title = (row.get("word") or row.get("sentence") or row.get("title") or "").strip()
        if not title:
            continue
        sid = str(row.get("sentence_id") or "")
        # 只有"热点榜"有 /hot/ID 专题页，其余榜单没有对应专题页，只能跳转到搜索页
        if board_name == "热点榜" and sid:
            link = f"https://www.douyin.com/hot/{sid}"
        else:
            link = f"https://www.douyin.com/search/{requests.utils.quote(title)}"
        hot_value = row.get("hot_value") or row.get("view_count") or 0
        try:
            hot_value = int(hot_value)
        except (TypeError, ValueError):
            hot_value = 0
        out.append({
            "title": title,
            "url": link,
            "category": f"抖音-{board_name}",
            "heat": hot_value,
            "rank_no": i,
            "extra": json.dumps({"hot_value": hot_value}, ensure_ascii=False),
        })
    return out


def fetch_douyin_all():
    """抓抖音五个榜，每个独立try，一个失败不影响其他，全部记日志"""
    all_results = []
    for board_name in BOARD_PARAM:
        try:
            items = _fetch_board(board_name)
            all_results.extend(items)
            logger.action("douyin", f"抓取{board_name}", f"成功{len(items)}条")
        except Exception as e:
            logger.error(f"抖音[{board_name}]抓取失败", e)
            print(f"  抖音[{board_name}]失败: {e}")
    return all_results


if __name__ == "__main__":
    items = fetch_douyin_all()
    print(f"抖音五榜共抓到 {len(items)} 条")
    from collections import Counter
    for cate, n in Counter(it["category"] for it in items).items():
        print(f"  {cate}: {n}条")
