# -*- coding: utf-8 -*-
"""
通用页面抓取：读取调试浏览器里【当前打开页面】的内容。
绕开签名/反爬——因为是你真浏览器正常加载的，软件只读结果。
针对小红书、知乎做了优化提取，其他页面用通用规则。
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import logger
from login import DEBUG_PORT
import re as _re


# ============ 统一垃圾过滤（所有平台、所有提取器抓的内容，入库前都过这一道）============
# 这些是各平台页面上的功能按钮/菜单/播放数/账号操作，不是热点内容。
_JUNK_EXACT = {
    "回复我的", "收到的赞", "系统消息", "我的消息", "我的动态", "我的关注", "我的收藏",
    "添加至稍后再看", "稍后再看", "添加至", "不感兴趣", "撤销", "减少此类内容推荐",
    "不感兴趣将减少此类内容推荐", "不感兴趣将减少此类内容推荐 撤销",
    "播放", "弹幕", "投币", "转发", "一键三连", "我的", "动态", "消息中心", "消息通知",
    "@我的", "评论我的", "通知", "草稿", "私信设置", "黑名单", "我的等级", "创作中心",
    "关注数", "粉丝数", "获赞", "浏览", "编辑资料", "编辑", "管理", "登录后可查看",
    "登录/注册", "去登录", "立即注册", "扫码登录", "手机登录", "正在直播", "直播中",
    "预约", "已预约", "免费", "VIP", "大会员", "首页", "登录", "注册", "更多", "换一换",
    "下一页", "上一页", "关注", "推荐", "展开", "收起", "全部", "搜索", "确定", "取消",
    "分享", "点赞", "评论", "收藏", "热门", "最新", "设置", "反馈", "举报", "客服",
    "意见反馈", "帮助中心", "关于我们", "联系我们", "用户协议", "隐私政策",
    "创作者中心", "进入创作者中心", "个人中心", "私信", "发布", "投稿", "查看更多",
    "加载更多", "会员中心", "历史记录", "夜间模式", "登录/ 注册",
    # —— 知乎/微博 频道菜单 & 后台功能项（图1那一整屏）——
    "综合", "用户", "论文", "专栏", "盐选内容", "盐选", "电子书", "圈子", "话题",
    "视频", "想法", "热榜", "会员", "发现", "等你来答", "头条文章", "V+微博", "V+会员",
    "你可能感兴趣的人", "你可能感兴趣", "数据中心", "内容管理", "收益中心", "私信管理",
    "自助服务中心", "常见问题", "开放平台", "处理大厅", "微博招聘", "新版反馈客服",
    "反馈客服", "无障碍", "无障碍举报", "网站导航", "问题反馈", "帮助反馈",
    "找人", "看点", "游戏", "微博会员", "超话", "红包", "会员购", "专栏文章",
    "我的关注", "赞过", "评论过", "转发过", "提到我的", "关注我的",
    "新版", "旧版", "反馈", "客服", "在线客服", "联系客服",
}

# 播放数/点赞数：如 "94.0万" "2.1万" "1.2亿" "3.5w" "12万播放" "8万点赞" "10万人感兴趣"
_JUNK_NUM = _re.compile(r"^[·•\s]*[0-9]+(\.[0-9]+)?\s*[万亿wW千kK]?\+?\s*(播放|次播放|观看|弹幕|点赞|评论|阅读|热度|在看|人气|粉丝|关注|人感兴趣|人在看|人参与|条评论|次观看|次点赞)?$")
# 相对时间："3分钟前" "2小时前"，可能带·前缀
_JUNK_TIME = _re.compile(r"^[·•\s]*[0-9]+\s*(秒|分钟|分|小时|天|周|月|年)前$")
_JUNK_CLOCK = _re.compile(r"^[·•\s]*[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?$")
# 日期格式："·08-28" "08-28" "·07-10" "2024-08-28" "8月28日"（B站列表里的发布日期）
_JUNK_DATE = _re.compile(r"^[·•\s]*([0-9]{4}[-/])?[0-9]{1,2}[-/月][0-9]{1,2}[日号]?$")
# 电话/热线："4000-980-980" "合作热线 4000-980-980" "400-xxx-xxx"
_JUNK_PHONE = _re.compile(r"(热线|电话|客服).*[0-9]{3,}|^[0-9]{3,4}[-\s][0-9]{3}[-\s][0-9]{3,4}$")
# 账号操作句式
_JUNK_ACCOUNT = _re.compile(r"不感兴趣|减少此类|稍后再看|添加至|不再推荐|反馈问题")
_JUNK_MYPREFIX = _re.compile(r"^(我的|我关注的|收到的|系统|消息|通知|草稿|评论我的|@我的|赞和收藏)")


def _is_junk_content(title):
    """判断抓到的一条内容是不是垃圾（功能按钮/播放数/账号操作等）。"""
    t = (title or "").strip()
    if not t:
        return True
    if t in _JUNK_EXACT:
        return True
    # 备案/版权
    if _re.search(r"备案|ICP|公网安备|人服证字|许可证|营业执照|Copyright|版权所有|©", t, _re.I):
        return True
    # 纯数字/纯符号
    if _re.match(r"^[0-9\s.:：、,，%]+$", t):
        return True
    if _JUNK_NUM.match(t):
        return True
    if _JUNK_TIME.match(t) or _JUNK_CLOCK.match(t):
        return True
    if _JUNK_DATE.match(t):
        return True
    if _JUNK_PHONE.search(t):
        return True
    if t in ("刚刚", "今天", "昨天", "前天"):
        return True
    if _JUNK_ACCOUNT.search(t):
        return True
    if _JUNK_MYPREFIX.match(t) and len(t) <= 10:
        return True
    # 纯英文短词（导航按钮）
    if _re.match(r"^[A-Za-z]{1,15}$", t):
        return True
    return False


def _clean_items(items):
    """把抓到的一批内容过一遍垃圾过滤，返回干净的列表。"""
    cleaned = []
    for it in items:
        title = (it.get("title") or "").strip() if isinstance(it, dict) else ""
        if not title or _is_junk_content(title):
            continue
        cleaned.append(it)
    return cleaned


def _recv_cdp_result(ws, msg_id, max_reads=30):
    """
    从websocket读取指定id的CDP命令响应。
    浏览器可能在响应之前先推送若干事件消息（不带id或id不同），
    这里循环跳过它们，直到读到匹配的那条，避免把事件当成结果解析而报错。
    """
    for _ in range(max_reads):
        raw = ws.recv()
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if msg.get("id") == msg_id:
            return msg
    raise RuntimeError("没等到页面抓取指令的返回（读到的都是浏览器事件）")


# 针对不同网站的提取JS（返回 [{title, url}] 的JSON）
EXTRACT_JS = {
    "xiaohongshu": """
    (function(){
        var out = [];
        // 小红书笔记卡片（探索页、搜索页、频道页通用）
        document.querySelectorAll('a.cover, a[href*="/explore/"], a[href*="/discovery/item/"], a[href*="/search_result/"]').forEach(function(a){
            var titleEl = a.querySelector('.title, .footer .title') || a;
            var text = (titleEl.innerText || a.getAttribute('title') || '').trim();
            if(text.length >= 3 && text.length <= 80){
                out.push({title: text, url: a.href || ''});
            }
        });
        // 兜底1：note-item 卡片结构
        if(out.length < 3){
            document.querySelectorAll('.note-item, section.note-item, [class*="note-item"]').forEach(function(el){
                var a = el.querySelector('a');
                var t = ((el.querySelector('.title') || {}).innerText || '').trim();
                if(t.length>=3 && t.length<=80) out.push({title:t, url:(a&&a.href)||''});
            });
        }
        // 兜底2：任何带笔记链接的卡片，取其可见文字第一行
        if(out.length < 3){
            document.querySelectorAll('a[href*="/explore/"], a[href*="xhslink"]').forEach(function(a){
                var t = (a.innerText||'').trim().split('\\n')[0].trim();
                if(t.length>=3 && t.length<=80) out.push({title:t, url:a.href||''});
            });
        }
        var s={},o=[];out.forEach(function(x){if(!s[x.title]){s[x.title]=1;o.push(x);}});
        return JSON.stringify(o.slice(0,60));
    })();
    """,
    "zhihu": """
    (function(){
        var out = [];
        // 1) 知乎热榜条目
        document.querySelectorAll('.HotItem-title, .HotList-item .HotItem-title').forEach(function(el){
            var text = (el.innerText || '').trim();
            var a = el.closest('a');
            if(text.length >= 4 && text.length <= 100) out.push({title: text, url: (a&&a.href)||'', kind:'hot'});
        });
        // 2) 问题/回答标题（搜索结果页、问题页）
        document.querySelectorAll('.ContentItem-title a, h2.ContentItem-title, .SearchResult-Card h2 a, .Card .ContentItem-title a').forEach(function(el){
            var text = (el.innerText || '').trim();
            if(text.length >= 4 && text.length <= 100) out.push({title: text, url: el.href||'', kind:'content'});
        });
        // 3) 大家都在搜：先精准定位那个区块（标题含"大家都在搜"的容器），只抓它里面的词
        var searchWords = [];
        var allEls = document.querySelectorAll('*');
        for(var i=0;i<allEls.length;i++){
            var el = allEls[i];
            var t = (el.childNodes.length===1 ? (el.innerText||'') : '').trim();
            if(t === '大家都在搜' || t === '大家都在搜：'){
                // 找到标题，往上找容器，再抓容器里的链接词
                var box = el.parentElement;
                for(var j=0;j<3 && box;j++){
                    var links = box.querySelectorAll('a, [class*="item"], [class*="Tag"], button');
                    if(links.length >= 2){
                        links.forEach(function(lk){
                            var w = (lk.innerText||'').trim();
                            if(w.length>=2 && w.length<=40) searchWords.push({title:w, url:lk.href||'', kind:'search'});
                        });
                        break;
                    }
                    box = box.parentElement;
                }
                break;
            }
        }
        // 兜底：如果上面没定位到，再用"链接指向/search"的老办法
        if(searchWords.length === 0){
            document.querySelectorAll('a[href*="/search"]').forEach(function(a){
                var text = (a.innerText || '').trim();
                if(text.length >= 2 && text.length <= 40) searchWords.push({title: text, url: a.href||'', kind:'search'});
            });
        }
        searchWords.forEach(function(w){ out.push(w); });

        var s={},o=[];out.forEach(function(x){if(!s[x.title]){s[x.title]=1;o.push(x);}});
        return JSON.stringify(o.slice(0,80));
    })();
    """,
    "weibo_hot": """
    (function(){
        var out = [];
        // 微博热搜榜 s.weibo.com/top/summary
        document.querySelectorAll('td.td-02 a, .list_a li a, .data tr td a').forEach(function(a){
            var text = (a.innerText || '').trim();
            if(text.length >= 2 && text.length <= 60 && text !== '换一换'){
                out.push({title: text, url: a.href || ''});
            }
        });
        var s={},o=[];out.forEach(function(x){if(!s[x.title]){s[x.title]=1;o.push(x);}});
        return JSON.stringify(o.slice(0,60));
    })();
    """,
    "_generic": """
    (function(){
        // ===== 借鉴 Scrapling 的思路：不盲目抓所有标题/链接，
        //       而是先定位"内容主体区"，跳过导航/侧栏/页脚，再从主体里提取。=====
        var out = [];

        // 扩展的垃圾词表：网站导航/账号操作/播放数/互动按钮等，都不是热点内容
        var skip = {'首页':1,'登录':1,'注册':1,'更多':1,'换一换':1,'下一页':1,'上一页':1,'关注':1,'推荐':1,
            '下载客户端':1,'下载电脑客户端':1,'客户端下载':1,'营业执照':1,'电子营业执照':1,
            '增值电信业务经营许可证':1,'网络文化经营许可证':1,'广播电视节目制作经营许可证':1,
            '意见反馈':1,'帮助中心':1,'关于我们':1,'联系我们':1,'用户协议':1,'隐私政策':1,
            '举报':1,'客服':1,'商务合作':1,'友情链接':1,'返回顶部':1,'扫码下载':1,'App下载':1,
            '开通会员':1,'立即登录':1,'切换账号':1,'退出登录':1,'展开':1,'收起':1,'全部':1,
            '创作者中心':1,'进入创作者中心':1,'我的主页':1,'个人中心':1,'消息':1,'私信':1,
            '发布':1,'投稿':1,'创作服务':1,'创作学院':1,'热门活动':1,'查看更多':1,'加载更多':1,
            '会员中心':1,'我的收藏':1,'历史记录':1,'设置':1,'夜间模式':1,'反馈':1,'合作':1,
            '搜索':1,'确定':1,'取消':1,'分享':1,'点赞':1,'评论':1,'收藏':1,'热门':1,'最新':1,
            // —— 账号/消息/互动类（B站、微博、知乎、小红书通用）——
            '回复我的':1,'收到的赞':1,'系统消息':1,'我的消息':1,'我的动态':1,'我的关注':1,
            '添加至稍后再看':1,'稍后再看':1,'添加至':1,'不感兴趣':1,'撤销':1,
            '不感兴趣将减少此类内容推荐':1,'不感兴趣将减少此类内容推荐 撤销':1,
            '减少此类内容推荐':1,'播放':1,'弹幕':1,'投币':1,'转发':1,'一键三连':1,
            '我的':1,'动态':1,'消息中心':1,'消息通知':1,'@我的':1,'评论我的':1,
            '通知':1,'草稿':1,'私信设置':1,'黑名单':1,'我的等级':1,'创作中心':1,
            '关注数':1,'粉丝数':1,'获赞':1,'浏览':1,'编辑资料':1,'编辑':1,'管理':1,
            '登录后可查看':1,'登录/注册':1,'去登录':1,'立即注册':1,'扫码登录':1,'手机登录':1,
            '正在直播':1,'直播中':1,'预约':1,'已预约':1,'免费':1,'VIP':1,'大会员':1};

        function isJunk(t){
            if(skip[t]) return true;
            // 备案/许可证/版权类
            if(/备案|ICP|公网安备|人服证字|许可证|营业执照|Copyright|版权所有|京公网|沪ICP|粤ICP|©/i.test(t)) return true;
            // 备案号编号格式
            if(/^[\\(（]?[\\u4e00-\\u9fa5]{0,3}[\\)）]?\\s*[\\u3014\\u3015\\[\\]0-9]+号?$/.test(t)) return true;
            // 纯数字/纯符号
            if(/^[0-9\\s.:：、,，%]+$/.test(t)) return true;
            // 播放数/点赞数：如 "94.0万" "2.1万" "1.2亿" "3.5w" "12万播放"
            if(/^[0-9]+(\\.[0-9]+)?\\s*[万亿wW千kK]?\\+?\\s*(播放|次播放|观看|弹幕|点赞|评论|阅读|热度|在看|人气|粉丝|关注)?$/.test(t)) return true;
            // 时间戳/相对时间：如 "3分钟前" "2小时前" "昨天" "01:23"
            if(/^(刚刚|今天|昨天|前天|周[一二三四五六日])$/.test(t)) return true;
            if(/^[0-9]+\\s*(秒|分钟|分|小时|天|周|月|年)前$/.test(t)) return true;
            if(/^[0-9]{1,2}:[0-9]{2}(:[0-9]{2})?$/.test(t)) return true;
            // 账号操作类句式：以"我的/我关注的/收到的/系统"开头的短功能词
            if(/^(我的|我关注的|收到的|系统|消息|通知|草稿|评论我的|回复我的|@我的|赞和收藏)/.test(t) && t.length <= 10) return true;
            // "不感兴趣""减少推荐""稍后再看"这类推荐操作
            if(/不感兴趣|减少此类|稍后再看|添加至|不再推荐|反馈问题/.test(t)) return true;
            // 纯英文导航词（单个单词，常见于按钮）
            if(/^[A-Za-z]{1,15}$/.test(t)) return true;
            return false;
        }

        // 判断一个元素是不是在导航/页脚/侧栏里（这些区域的内容跳过）
        function inChrome(el){
            var p = el;
            for(var i=0;i<6 && p;i++){
                var tag=(p.tagName||'').toLowerCase();
                if(tag==='nav'||tag==='header'||tag==='footer'||tag==='aside') return true;
                var cls=(p.className&&p.className.toString?p.className.toString():'').toLowerCase();
                var id=(p.id||'').toLowerCase();
                if(/(^|[^a-z])(nav|menu|header|footer|sidebar|side-bar|topbar|toolbar|breadcrumb|copyright|tabbar)([^a-z]|$)/.test(cls+' '+id)) return true;
                p=p.parentElement;
            }
            return false;
        }

        function pushEl(el){
            if(inChrome(el)) return;
            var text = (el.innerText || el.textContent || '').trim().split('\\n')[0].trim();
            if(text.length < 4 || text.length > 100) return;
            if(isJunk(text)) return;
            var a = (el.tagName==='A') ? el : (el.querySelector('a') || el.closest('a'));
            out.push({title: text, url: (a && a.href) || ''});
        }

        // 策略1：优先找"列表/榜单"结构（li、榜单类class里的条目）——最像热点榜的地方
        var listSel = 'li, [class*="item"], [class*="Item"], [class*="rank"], [class*="Rank"], [class*="list"] > *, [class*="List"] > *, [class*="card"], [class*="Card"], [class*="cell"]';
        document.querySelectorAll(listSel).forEach(function(el){
            // 只取叶子一点的条目，避免把整个大容器当一条
            if(el.querySelectorAll('li,[class*="item"],[class*="card"]').length > 2) return;
            pushEl(el);
        });

        // 策略2：如果列表法没抓到多少，退回抓标题类元素
        if(out.length < 5){
            document.querySelectorAll('h1,h2,h3,h4,[class*="title"],[class*="Title"],[class*="heading"]').forEach(pushEl);
        }

        // 策略3：还是太少，最后兜底抓正文区里的链接
        if(out.length < 5){
            document.querySelectorAll('main a, article a, [role="main"] a, [class*="content"] a, [class*="Content"] a').forEach(pushEl);
        }
        // 实在没有main区，就抓所有链接（老逻辑兜底）
        if(out.length < 3){
            document.querySelectorAll('a').forEach(pushEl);
        }

        var s={},o=[];
        out.forEach(function(x){ if(!s[x.title]){ s[x.title]=1; o.push(x); } });
        return JSON.stringify(o.slice(0,80));
    })();
    """,
}


def _extract_value(result):
    """从 CDP Runtime.evaluate 的返回里安全取出 value。
    如果页面JS执行报错（exceptionDetails存在）或结构不对，抛出带具体原因的异常，
    而不是让上层直接因为 KeyError 崩掉、看不出真实原因。"""
    r = result.get("result", {})
    exc = r.get("exceptionDetails")
    if exc:
        msg = exc.get("exception", {}).get("description") or exc.get("text") or str(exc)
        raise RuntimeError(f"页面JS执行异常: {msg[:200]}")
    inner = r.get("result", {})
    if "value" not in inner:
        raise RuntimeError(f"返回结构里没有value字段，原始result={json.dumps(inner)[:200]}")
    return inner["value"]


def _pick_js(url):
    if "xiaohongshu" in url:
        return EXTRACT_JS["xiaohongshu"], "xiaohongshu"
    if "zhihu" in url:
        return EXTRACT_JS["zhihu"], "zhihu"
    if "s.weibo.com" in url or "weibo.com/top" in url:
        return EXTRACT_JS["weibo_hot"], "weibo"
    if "weibo" in url:
        return EXTRACT_JS["_generic"], "weibo"
    if "bilibili" in url:
        return EXTRACT_JS["_generic"], "bilibili"
    return EXTRACT_JS["_generic"], "other"


def read_current_pages(user_note=""):
    """
    读取调试浏览器里所有打开的页面（除操作页面外）的内容。
    user_note: 用户填的备注，如果填了就优先用它当分类名。
    返回 {"ok": bool, "msg": str, "items": [...]}
    """
    try:
        import requests
    except ImportError:
        return {"ok": False, "msg": "缺少requests库"}
    try:
        from websocket import create_connection
    except ImportError:
        return {"ok": False, "msg": "缺少websocket-client库"}

    # 确认调试端口
    try:
        requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=5)
    except Exception:
        return {"ok": False, "msg": "读不到浏览器，请确认软件的浏览器窗口开着"}

    tabs = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5).json()
    page_tabs = [t for t in tabs if t.get("type") == "page" and "127.0.0.1" not in t.get("url", "")]

    if not page_tabs:
        return {"ok": False, "msg": "浏览器里没有打开可抓取的页面。请先在浏览器里打开小红书/知乎等页面。"}

    total_saved = 0
    detail = []
    for tab in page_tabs:
        url = tab.get("url", "")
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            continue
        js, platform = _pick_js(url)
        try:
            ws = create_connection(ws_url, timeout=10)
            ws.send(json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": js, "returnByValue": True}
            }))
            result = _recv_cdp_result(ws, 1)
            ws.close()
            value = _extract_value(result)
            items = json.loads(value)
        except Exception as e:
            logger.error(f"读取页面失败: {url[:50]}", e)
            detail.append(f"{platform}页面读取失败")
            continue

        # 存数据库。category：用户填了备注就优先用备注，否则按平台+url智能判断
        saved = 0
        from tagger import tag_content
        from config import WATCH_KEYWORDS
        if user_note and user_note.strip():
            category = user_note.strip()
        elif platform == "zhihu":
            if "/hot" in url:
                category = "知乎-热榜"
            elif "search" in url:
                category = "知乎-搜索结果"
            else:
                category = "知乎-大家都在搜"
        elif platform == "weibo":
            category = "微博热搜" if ("s.weibo" in url or "/top" in url) else "微博页面"
        elif platform == "xiaohongshu":
            category = "小红书"
        elif platform == "bilibili":
            category = "B站页面"
        else:
            category = "浏览器抓取"
        for it in items:
            title = it.get("title", "").strip()
            if not title or _is_junk_content(title):
                continue
            tags = set(t for t in tag_content(title).split(",") if t)
            if any(kw in title for kw in WATCH_KEYWORDS):
                tags.add("重点关注")
            db.upsert_item(
                platform=platform, title=title, url=it.get("url", ""),
                category=category, tags=",".join(sorted(tags)),
            )
            saved += 1
        total_saved += saved
        page_title = tab.get("title", "")[:20]
        detail.append(f"{platform}({page_title}):{saved}条")
        logger.action(platform, "读当前页面", f"{page_title} 抓到{saved}条")

    db.log_fetch("browser", "success", item_count=total_saved)
    return {"ok": True, "msg": f"从{len(page_tabs)}个页面共抓到{total_saved}条：{'; '.join(detail)}", "count": total_saved}


if __name__ == "__main__":
    print(read_current_pages())


def detect_platform(url):
    """自动识别网址属于哪个平台。认识的返回平台名，不认识返回None"""
    if "xiaohongshu" in url:
        return "xiaohongshu"
    if "zhihu" in url:
        return "zhihu"
    if "weibo" in url:
        return "weibo"
    if "bilibili" in url:
        return "bilibili"
    return None  # 不认识，需要用户备注


def fetch_url(url, note=""):
    """
    在调试浏览器里打开指定网址，等加载后抓取内容。
    note: 用户填的备注（其他网站用，作为分类名）
    认识的平台自动归类，不认识的用note。
    """
    import time
    try:
        import requests
    except ImportError:
        return {"ok": False, "msg": "缺少requests库"}
    try:
        from websocket import create_connection
    except ImportError:
        return {"ok": False, "msg": "缺少websocket-client库"}

    # 确认调试端口
    try:
        requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=5)
    except Exception:
        return {"ok": False, "msg": "读不到浏览器，请确认软件的浏览器窗口开着"}

    # 补全网址
    if not url.startswith("http"):
        url = "https://" + url

    platform = detect_platform(url)
    # 分类名规则：
    # - 认识的平台+有备注 → 用备注（这样微博各榜单能分开：微博-热搜、微博-文娱等）
    # - 认识的平台+无备注 → 用"浏览器抓取"
    # - 不认识+有备注 → 用备注
    # - 不认识+无备注 → "其他"
    if platform:
        category = note.strip() if note.strip() else "浏览器抓取"
    else:
        platform = "other"
        category = note.strip() if note.strip() else "其他"

    # 1. 打开新标签
    try:
        r = requests.put(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", timeout=5)
        new_tab = r.json()
    except Exception:
        try:
            r = requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", timeout=5)
            new_tab = r.json()
        except Exception as e:
            logger.error(f"打开网址失败: {url}", e)
            return {"ok": False, "msg": f"打开网址失败: {type(e).__name__}"}

    tab_id = new_tab.get("id")
    ws_url = new_tab.get("webSocketDebuggerUrl")
    if not ws_url:
        return {"ok": False, "msg": "打开网址后拿不到调试连接"}

    # 1.5 把新标签页切到前台。很多网站（包括微博）在后台标签页时不会完整渲染内容，
    # 必须让它处于"可见"状态才会真正加载出数据，所以这里用CDP接口自动切换，
    # 不需要用户手动点一下。
    try:
        requests.get(f"http://127.0.0.1:{DEBUG_PORT}/json/activate/{tab_id}", timeout=5)
    except Exception as e:
        logger.warn(f"切换标签页到前台失败（不影响继续抓取）: {type(e).__name__}")

    # 2. 等页面加载（小红书等需要时间刷内容）
    logger.info(f"打开网址 {url[:50]}，等待加载...")
    time.sleep(6)

    # 3. 抓取
    js, detected = _pick_js(url)
    try:
        ws = create_connection(ws_url, timeout=15)
        ws.send(json.dumps({
            "id": 1, "method": "Runtime.evaluate",
            "params": {"expression": js, "returnByValue": True}
        }))
        result = _recv_cdp_result(ws, 1)
        ws.close()
        value = _extract_value(result)
        items = json.loads(value)
    except Exception as e:
        logger.error(f"抓取网址内容失败: {url[:50]}", e)
        return {"ok": False, "msg": f"抓取失败: {type(e).__name__}"}

    # 4. 存库
    from tagger import tag_content
    from config import WATCH_KEYWORDS
    saved = 0
    for it in items:
        title = it.get("title", "").strip()
        if not title or _is_junk_content(title):
            continue
        tags = set(t for t in tag_content(title).split(",") if t)
        if any(kw in title for kw in WATCH_KEYWORDS):
            tags.add("重点关注")
        db.upsert_item(
            platform=platform, title=title, url=it.get("url", ""),
            category=category, tags=",".join(sorted(tags)),
        )
        saved += 1

    logger.action(platform, "抓取网址", f"{url[:40]} 分类={category} 抓到{saved}条")
    db.log_fetch(platform, "success", item_count=saved)

    # 不自动关标签，留着让用户能看/能继续下拉再抓
    plat_show = {"weibo":"微博","bilibili":"B站","zhihu":"知乎","xiaohongshu":"小红书","other":category}.get(platform, platform)
    return {"ok": True, "msg": f"抓到{saved}条，归类到【{plat_show if platform!='other' else category}】", "count": saved}
