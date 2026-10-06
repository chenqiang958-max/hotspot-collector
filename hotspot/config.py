# -*- coding: utf-8 -*-
"""配置文件：关键词库、监控词、限速"""

DEMAND_KEYWORDS = [
    "求推荐", "求一个", "求个", "有没有", "求", "平替", "替代品",
    "没人做", "谁有", "求资源", "求资料", "求软件", "求工具", "哪里能买",
    "怎么买", "在哪买", "求链接", "求分享", "代做", "接单",
]
TOPIC_KEYWORDS = [
    "争议", "反转", "翻车", "塌房", "槽点", "吐槽", "热议", "刷屏",
    "全网", "爆了", "上热搜", "冲上热搜", "热搜第一",
]
EDUCATION_KEYWORDS = [
    "考证", "考试", "会计", "初级会计", "验光师", "职业资格", "题库",
    "培训", "证书", "报考", "考点", "真题", "押题", "税务师", "网课",
]
TOOL_KEYWORDS = [
    "软件", "工具", "app", "APP", "转换", "PDF", "Word", "效率",
    "插件", "脚本", "自动化", "PPT",
]

# 监控词：命中标"重点关注"
WATCH_KEYWORDS = [
    "验光师", "初级会计", "PDF转Word", "题库",
]

# 小红书频道（除"推荐"外）
XIAOHONGSHU_CHANNELS = [
    "穿搭", "美食", "彩妆", "影视", "职场", "情感", "家居", "游戏", "旅行", "健身", "视频",
]

# 限速保护账号
BATCH_SIZE = 25
BATCH_PAUSE_MINUTES = 10

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 10

PLATFORM_NAMES = {
    "weibo": "微博", "bilibili": "B站", "zhihu": "知乎", "xiaohongshu": "小红书",
    "douyin": "抖音",
}
