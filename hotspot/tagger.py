# -*- coding: utf-8 -*-
"""
打标签模块：根据关键词库给内容打标签
"""
from config import DEMAND_KEYWORDS, TOPIC_KEYWORDS, EDUCATION_KEYWORDS, TOOL_KEYWORDS


def _load_custom_rules():
    """从数据库读用户自定义标签规则。读不到（比如建表前）就返回空，不影响内置标签。"""
    try:
        import db
        rules = []
        for row in db.get_custom_tags():
            name = (row.get("tag_name") or "").strip()
            kws = [k.strip() for k in (row.get("keywords") or "").replace("，", ",").split(",") if k.strip()]
            if name and kws:
                rules.append((name, kws))
        return rules
    except Exception:
        return []


def tag_content(title: str) -> str:
    """
    给一段文本打标签，返回逗号分隔的标签字符串
    可能同时命中多个标签，比如"需求类,效率工具"
    内置标签之外，还会套用用户在界面上自定义的关键词规则。
    """
    tags = []
    text = title or ""

    if any(kw in text for kw in DEMAND_KEYWORDS):
        tags.append("需求类")
    if any(kw in text for kw in TOPIC_KEYWORDS):
        tags.append("话题类")
    if any(kw in text for kw in EDUCATION_KEYWORDS):
        tags.append("教育考证")
    if any(kw in text for kw in TOOL_KEYWORDS):
        tags.append("效率工具")

    # 用户自定义标签规则：命中任一关键词就打上该标签
    for name, kws in _load_custom_rules():
        if name in tags:
            continue
        if any(kw in text for kw in kws):
            tags.append(name)

    return ",".join(tags)


def heat_level(seen_count: int, first_seen: str, last_seen: str) -> str:
    """
    根据出现次数和时间跨度算热度分级
    - 爆热: 单次抓取就很显眼（这里简化为 seen_count 用不上时，由调用方结合排名判断）
    - 持续发酵: 出现次数 >= 3 次，说明连续多次抓取都命中
    - 新出现: 第一次抓到
    """
    if seen_count >= 5:
        return "持续发酵"
    elif seen_count >= 2:
        return "开始重复出现"
    else:
        return "新出现"


if __name__ == "__main__":
    # 简单自测
    tests = [
        "有没有好用的PDF转Word工具",
        "初级会计考试真题求分享",
        "某明星塌房上热搜第一",
        "今天天气怎么样",
    ]
    for t in tests:
        print(t, "->", tag_content(t))
