# -*- coding: utf-8 -*-
"""
数据分析模块：跨平台同话题汇总、今日洞察摘要。
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from config import PLATFORM_NAMES, WATCH_KEYWORDS


def _extract_keywords(title):
    """从标题提取关键词（去掉标点、常见虚词，保留2字以上的词块）"""
    # 去掉标点和空白
    clean = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9]", "", title)
    return clean


# 常见无意义的词，不作为共同话题依据
_STOPWORDS = {"视频", "现场", "最新", "曝光", "回应", "官方", "网友", "如何", "怎么",
              "为什么", "什么", "怎样", "哪些", "一个", "这个", "那个", "我们", "他们",
              "已经", "正在", "可以", "还是", "就是", "这样", "今天", "目前"}

# 明显不该参与聚合的垃圾标题（备案/页脚/太短/纯数字/时间戳等）
import re as _re
_JUNK_RE = _re.compile(r"备案|ICP|公网安备|人服证字|许可证|营业执照|版权所有|客户端|下载|"
                       r"创作者中心|创作服务|个人中心|会员中心|我的主页|投稿|私信|"
                       r"^\d{1,2}:\d{2}(:\d{2})?$")


def _is_junk_title(title):
    t = (title or "").strip()
    if len(t) < 5:            # 太短的标题（如 "台风"、"00:00"）不参与跨平台聚合
        return True
    if _JUNK_RE.search(t):
        return True
    return False


# 这些榜单是"常驻存档/经典榜"，不是当下热点。
# 比如B站"入站必刷""每周必看"全是历年经典老视频，不该当成"今日新冒出的热点"。
_ARCHIVE_CATEGORIES = {"入站必刷", "每周必看", "排行榜", "音乐榜"}


def _is_archive(item):
    cat = (item.get("category", "") or "")
    for a in _ARCHIVE_CATEGORIES:
        if a in cat:
            return True
    return False


def _similarity(t1, t2):
    """
    判断两个标题是否同话题：看它们共享多少个"实词"（3字以上关键词块）。
    收紧后规则：必须有一个≥4字的共同词块，或≥2个≥3字共同词块，才算同话题。
    （原来"3个2字词块也算"太松，会把不相关内容凑一起，已去掉。）
    """
    a = _extract_keywords(t1)
    b = _extract_keywords(t2)
    if len(a) < 4 or len(b) < 4:
        return 0

    def ngrams(s):
        grams = set()
        for n in (4, 5):  # 只用4/5字块，3字太短容易误配（如"600万"）
            for i in range(len(s) - n + 1):
                g = s[i:i+n]
                if g in _STOPWORDS:
                    continue
                # 关键修复：含数字的字块不作为共同话题依据
                # （否则"600万人""3000万""1700万"会因共享"万"类字块被错误归为同话题）
                if re.search(r"\d", g):
                    continue
                # 纯数字/纯符号也跳过
                grams.add(g)
        return grams

    ga, gb = ngrams(a), ngrams(b)
    common = {c for c in (ga & gb) if c not in _STOPWORDS}
    if not common:
        return 0
    # 收紧：必须有一个≥4字的、不含数字的共同词块才算同话题
    has_long = any(len(c) >= 4 for c in common)
    if has_long:
        return 1.0
    return 0


def cross_platform_topics(min_platforms=2, threshold=1.0, items=None):
    """
    找出跨多个平台出现的相似话题。
    items: 可传入已经过滤好（按时间/排除存档）的数据；不传就用全部去重数据。
    返回：[{topics:[...], platforms:[...], total_heat, count}]
    """
    if items is None:
        items = db.query_items_deduped(limit=2000)
    # 排除常驻存档榜（入站必刷等经典老视频，不是当下跨平台热点）
    items = [it for it in items if not _is_archive(it)]
    used = [False] * len(items)
    groups = []

    for i in range(len(items)):
        if used[i]:
            continue
        if _is_junk_title(items[i]["title"]):
            used[i] = True
            continue
        group = [items[i]]
        used[i] = True
        for j in range(i+1, len(items)):
            if used[j]:
                continue
            if _is_junk_title(items[j]["title"]):
                continue
            # 不同平台 且 标题相似
            if items[j]["platform"] != items[i]["platform"]:
                if _similarity(items[i]["title"], items[j]["title"]) >= threshold:
                    group.append(items[j])
                    used[j] = True
        # 统计这个组涉及的平台
        platforms = set(g["platform"] for g in group)
        if len(platforms) >= min_platforms:
            total_heat = sum(g.get("heat", 0) or 0 for g in group)
            # 收集这个话题涉及的具体榜单（去重），方便用户看它在哪些榜单上火
            cats = []
            for g in group:
                c = g.get("category", "") or ""
                if c and c not in cats:
                    cats.append(c)
            groups.append({
                "title": group[0]["title"],
                "entries": group,
                "platforms": sorted(platforms),
                "platform_names": [PLATFORM_NAMES.get(p, p) for p in sorted(platforms)],
                "categories": cats,
                "count": len(group),
                "platform_count": len(platforms),
                "total_heat": total_heat,
            })

    # 排序改进：
    # 国内榜单（微博热搜、知乎）抓下来热度常常是0，如果一味"平台数优先"，
    # 会让"跨3平台但都不火"的话题排在"跨2平台但超热"前面，误导判断。
    # 新规则：先看有没有真实热度。有热度的按 热度×平台数 的综合分排；
    # 热度都是0的，退回按平台数+条数排。
    def sort_key(x):
        heat = x["total_heat"] or 0
        # 综合分：热度为主，平台数作为加权（跨越平台越多略微加分）
        score = heat * (1 + 0.2 * (x["platform_count"] - 1))
        return (score, x["platform_count"], x["count"])
    groups.sort(key=sort_key, reverse=True)
    return groups


def daily_summary(date_range="3days"):
    """
    今日洞察摘要。
    date_range: 分析的时间范围——today(仅今天)/3days(最近3天)/7days/all(全部)。
    默认最近3天（避免把历史老数据和存档榜混进当下分析）。
    """
    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")

    dr = None if date_range == "all" else date_range
    all_items = db.query_items_deduped(limit=2000)
    if dr:
        now = datetime.now()
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if dr == "today":
            start = today0
        elif dr == "7days":
            start = today0 - timedelta(days=6)
        else:  # 3days 默认
            start = today0 - timedelta(days=2)
        start_str = start.isoformat(timespec="seconds")
        def _in_range(it):
            t = it.get("collected_at") or it.get("last_seen") or it.get("first_seen") or ""
            return t >= start_str
        all_items = [it for it in all_items if _in_range(it)]
    # 排除常驻存档榜（B站入站必刷等经典老视频）
    all_items = [it for it in all_items if not _is_archive(it)]

    today_items = [it for it in all_items if (it.get("first_seen","") or "").startswith(today)]

    # 跨平台话题（用同一批已过滤的数据）
    cross = cross_platform_topics(items=all_items)

    # 监控词命中
    watch_hits = []
    for it in all_items:
        for kw in WATCH_KEYWORDS:
            if kw in it["title"]:
                watch_hits.append({"keyword": kw, "title": it["title"],
                                   "platform": PLATFORM_NAMES.get(it["platform"], it["platform"]),
                                   "url": it.get("url", "")})
                break

    # 需求类
    demand_items = [it for it in all_items if "需求类" in (it.get("tags","") or "")]

    # 选题机会池 1：疑问类（大家在问）——标题里有疑问词
    _QUESTION_PAT = _re.compile(r"怎么|如何|为什么|为何|是什么|有没有|值得吗|值不值|值得买|值得入|"
                                r"哪个好|哪家|区别|靠谱吗|真的吗|会不会|能不能|好用吗|好不好|该怎么|"
                                r"怎么办|多少钱|贵不贵|难不难|要不要")
    question_items = [it for it in all_items if _QUESTION_PAT.search(it.get("title", "") or "")]

    # 选题机会池 2：求推荐/求助（大家在求）——注意避开"求救/求婚"这类情绪词
    _RECO_PAT = _re.compile(r"求推荐|求一个|求个|求分享|求资源|求链接|求教程|求科普|"
                            r"哪里买|哪里下|哪里学|有没有好用|有没有推荐|平替|替代品|"
                            r"怎么选|如何选择|选购|推荐一下|求助各位|求大神")
    reco_items = [it for it in all_items if _RECO_PAT.search(it.get("title", "") or "")]

    # 今日新冒出的热点：今天首次抓到、且不是垃圾标题，按热度排
    today_hot = [it for it in today_items if not _is_junk_title(it.get("title", ""))]
    today_hot.sort(key=lambda it: (it.get("heat", 0) or 0), reverse=True)

    return {
        "total": len(all_items),
        "today_new": len(today_items),
        "cross_count": len(cross),
        "cross_top": cross[:10],
        "cross_all": cross,
        "date_range": date_range,
        "watch_hits": watch_hits[:20],
        "demand_count": len(demand_items),
        "demand_top": demand_items[:15],
        "question_top": question_items[:20],
        "question_count": len(question_items),
        "reco_top": reco_items[:20],
        "reco_count": len(reco_items),
        "today_hot": today_hot[:20],
    }


if __name__ == "__main__":
    print("跨平台话题：")
    for g in cross_platform_topics()[:5]:
        print(f"  [{'/'.join(g['platform_names'])}] {g['title']} (共{g['count']}条)")
