# -*- coding: utf-8 -*-
"""
知乎抓取器：热榜 + 大家都在搜
cookie从数据库读（知乎需要登录才能稳定抓，用验证过的Chrome方案登录后存进来）。
带详细日志。
"""
import sys
import os
import re
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import USER_AGENT, REQUEST_TIMEOUT
import db
import logger


def _headers():
    h = {"User-Agent": USER_AGENT, "Referer": "https://www.zhihu.com/"}
    cred = db.get_credential("zhihu")
    if cred and cred.get("cookie"):
        h["Cookie"] = cred["cookie"]
    return h


def fetch_hot_list():
    """
    知乎热榜。优先用不需要登录的 billboard 网页（解析内嵌JSON），
    失败再试需要登录的API。这样没登录也能抓到热榜。
    """
    # 方式1：billboard网页，解析内嵌的 js-initialData（不需要登录）
    try:
        url = "https://www.zhihu.com/billboard"
        resp = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            m = re.search(r'<script id="js-initialData"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                initial = data.get("initialState", {})
                hot_list = initial.get("topstory", {}).get("hotList", [])
                results = []
                for entry in hot_list:
                    target = entry.get("target", {}) if isinstance(entry, dict) else {}
                    title = target.get("titleArea", {}).get("text", "") or target.get("title", "")
                    if not title:
                        # 再尝试别的字段结构
                        title = entry.get("titleArea", {}).get("text", "") if isinstance(entry, dict) else ""
                    if title:
                        link = target.get("link", {}).get("url", "") if isinstance(target, dict) else ""
                        results.append({"title": title, "url": link, "category": "热榜", "extra": ""})
                if results:
                    return results
    except Exception as e:
        logger.warn(f"知乎billboard网页解析失败，尝试其他方式: {e}")

    # 方式2：热榜HTML页面正则提取
    try:
        url = "https://www.zhihu.com/hot"
        resp = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            results = []
            for m in re.finditer(r'"target":\{[^}]*"title":"([^"]+)"', resp.text):
                title = m.group(1).strip()
                if title and len(title) > 2:
                    results.append({"title": title, "url": "", "category": "热榜", "extra": ""})
            if results:
                return results[:50]
    except Exception as e:
        logger.warn(f"知乎hot网页解析失败: {e}")

    # 方式3：登录API（需要cookie）
    url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"
    resp = requests.get(url, headers=_headers(), params={"limit": 50}, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 403:
        raise RuntimeError("知乎热榜需要登录（前面几种免登录方式都没成功），请登录知乎后重试")
    resp.raise_for_status()
    data = resp.json()
    results = []
    for item in data.get("data", []):
        target = item.get("target", {})
        title = target.get("title", "")
        if not title:
            continue
        results.append({
            "title": title,
            "url": f"https://www.zhihu.com/question/{target.get('id', '')}",
            "category": "热榜",
            "extra": json.dumps({"heat": item.get("detail_text", "")}, ensure_ascii=False),
        })
    return results


def fetch_search_hot():
    """大家都在搜。多重尝试：API + 网页解析。"""
    results = []

    # 方式1: API接口
    try:
        url = "https://www.zhihu.com/api/v4/search/top_search"
        resp = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            words = data.get("data", {}).get("top_search", {}).get("words", [])
            if not words:
                words = data.get("top_search", {}).get("words", [])
            if not words:
                words = []
            for w in words:
                title = w.get("query", "") if isinstance(w, dict) else str(w)
                # query可能是带高亮标签的，清理下
                import re as _re
                title = _re.sub(r"<[^>]+>", "", str(title)).strip()
                if title:
                    results.append({
                        "title": title,
                        "url": f"https://www.zhihu.com/search?q={requests.utils.quote(title)}",
                        "category": "大家都在搜", "extra": "",
                    })
            if results:
                return results
    except Exception as e:
        logger.warn(f"知乎大家都在搜API失败，尝试网页: {e}")

    # 方式2: billboard网页里也有"大家都在搜"数据
    try:
        url = "https://www.zhihu.com/billboard"
        resp = requests.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            m = re.search(r'<script id="js-initialData"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                # 搜索热词通常在 initialState.topsearch 或 searchTop
                initial = data.get("initialState", {})
                # 尝试多个可能的位置
                for path in [["topsearch", "words"], ["searchTopSearch", "words"], ["topSearch", "words"]]:
                    node = initial
                    for key in path:
                        node = node.get(key, {}) if isinstance(node, dict) else {}
                    if isinstance(node, list) and node:
                        for w in node:
                            title = w.get("query", "") if isinstance(w, dict) else str(w)
                            import re as _re
                            title = _re.sub(r"<[^>]+>", "", str(title)).strip()
                            if title:
                                results.append({"title": title, "url": f"https://www.zhihu.com/search?q={requests.utils.quote(title)}", "category": "大家都在搜", "extra": ""})
                        if results:
                            return results
    except Exception as e:
        logger.warn(f"知乎大家都在搜网页解析失败: {e}")

    if not results:
        raise RuntimeError("大家都在搜：API和网页都没拿到数据（可用地址栏抓知乎首页作为替代）")
    return results


def fetch_zhihu_all():
    """抓知乎两块，各自独立try，记日志"""
    all_results = []
    try:
        items = fetch_hot_list()
        all_results.extend(items)
        logger.action("zhihu", "抓取热榜", f"成功{len(items)}条")
    except Exception as e:
        logger.error("知乎热榜抓取失败", e)
        print(f"  知乎热榜失败: {e}")

    try:
        items = fetch_search_hot()
        all_results.extend(items)
        logger.action("zhihu", "抓取大家都在搜", f"成功{len(items)}条")
    except Exception as e:
        logger.error("知乎大家都在搜抓取失败", e)
        print(f"  知乎大家都在搜失败: {e}")

    return all_results


if __name__ == "__main__":
    items = fetch_zhihu_all()
    print(f"知乎共抓到 {len(items)} 条")
    from collections import Counter
    for cate, n in Counter(it["category"] for it in items).items():
        print(f"  {cate}: {n}条")
