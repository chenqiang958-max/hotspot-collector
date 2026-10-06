# -*- coding: utf-8 -*-
"""
主界面后端（网页形式，浏览器打开127.0.0.1:5000）
登录用Chrome调试端口方案（已验证），不用会崩的内置浏览器。
"""
import io
import os
import threading
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for

import db
import logger
from config import WATCH_KEYWORDS, PLATFORM_NAMES

app = Flask(__name__)
# session密钥：优先从文件读，没有就生成一个存下来（保证重启后已登录状态不会全失效得太怪）
_SECRET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", ".secret_key")
def _load_secret():
    try:
        if os.path.exists(_SECRET_PATH):
            with open(_SECRET_PATH, "r") as f:
                s = f.read().strip()
                if s:
                    return s
        import secrets as _s
        s = _s.token_hex(32)
        os.makedirs(os.path.dirname(_SECRET_PATH), exist_ok=True)
        with open(_SECRET_PATH, "w") as f:
            f.write(s)
        return s
    except Exception:
        import secrets as _s
        return _s.token_hex(32)
app.secret_key = _load_secret()

# 不需要登录就能访问的路由（激活、登录页、设置密码、静态资源）
_PUBLIC_ENDPOINTS = {"activate_page", "do_activate", "login_page", "do_login",
                     "setup_password", "do_setup_password", "forgot_page", "do_reset_password", "static"}


@app.before_request
def _require_login():
    """全局拦截：未激活→激活页；已激活未设密码→设密码；已设密码未登录→登录页。"""
    ep = request.endpoint or ""
    if ep in _PUBLIC_ENDPOINTS:
        return None
    import activation
    # 第一关：本机没激活 → 去激活页
    if not activation.is_activated():
        if ep != "activate_page":
            return redirect(url_for("activate_page"))
        return None
    # 第二关：激活了但还没设密码 → 去设密码页
    if not db.has_app_password():
        if ep != "setup_password":
            return redirect(url_for("setup_password"))
        return None
    # 第三关：设过密码但没登录 → 跳登录页
    if not session.get("logged_in"):
        if request.method == "POST" and ep not in ("do_login",):
            return jsonify({"ok": False, "msg": "登录已失效，请刷新页面重新输入密码"}), 401
        return redirect(url_for("login_page"))
    return None


@app.after_request
def _no_cache(resp):
    """禁止浏览器缓存页面，保证每次都是最新的（改了代码/模板后不用手动清缓存）"""
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# 抓取任务状态（前端轮询显示进度）
TASK_STATUS = {"running": False, "text": "空闲", "done": 0, "total": 0, "results": []}

def _set_task(running=None, text=None, done=None, total=None, add_result=None, reset=False):
    if reset:
        TASK_STATUS["running"] = True
        TASK_STATUS["text"] = ""
        TASK_STATUS["done"] = 0
        TASK_STATUS["total"] = 0
        TASK_STATUS["results"] = []
    if running is not None: TASK_STATUS["running"] = running
    if text is not None: TASK_STATUS["text"] = text
    if done is not None: TASK_STATUS["done"] = done
    if total is not None: TASK_STATUS["total"] = total
    if add_result is not None: TASK_STATUS["results"].append(add_result)

PLATFORM_OPTIONS = [(k, v) for k, v in PLATFORM_NAMES.items()]
TAG_ORDER = ["重点关注", "需求类", "话题类", "教育考证", "效率工具"]


@app.route("/activate", methods=["GET"])
def activate_page():
    """激活页：输入激活码。已激活就跳去下一步。"""
    import activation
    if activation.is_activated():
        return redirect(url_for("setup_password"))
    return render_template("activate.html", machine=activation.get_machine_fingerprint())


@app.route("/activate", methods=["POST"])
def do_activate():
    import activation
    data = request.get_json() or {}
    code = data.get("code", "")
    ok, msg = activation.activate_this_machine(code)
    if ok:
        logger.action("软件", "激活", "成功")
    else:
        logger.action("软件", "激活", f"失败:{msg}")
    return jsonify({"ok": ok, "msg": msg})


@app.route("/setup", methods=["GET"])
def setup_password():
    """首次使用：设置开机密码。如果已经设过密码就直接去登录页。"""
    if db.has_app_password():
        return redirect(url_for("login_page"))
    return render_template("setup.html")


@app.route("/setup", methods=["POST"])
def do_setup_password():
    data = request.get_json() or {}
    pwd = (data.get("password", "") or "").strip()
    pwd2 = (data.get("password2", "") or "").strip()
    if len(pwd) < 4:
        return jsonify({"ok": False, "msg": "密码太短，至少4位"})
    if pwd != pwd2:
        return jsonify({"ok": False, "msg": "两次输入的密码不一样"})
    db.set_app_password(pwd)
    session["logged_in"] = True  # 设完直接进
    logger.action("软件", "设置开机密码", "成功")
    return jsonify({"ok": True, "msg": "密码已设置，进入软件"})


@app.route("/login", methods=["GET"])
def login_page():
    """输密码进软件的页面。"""
    if not db.has_app_password():
        return redirect(url_for("setup_password"))
    if session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def do_login():
    data = request.get_json() or {}
    pwd = data.get("password", "")
    if db.check_app_password(pwd):
        session["logged_in"] = True
        logger.action("软件", "输入密码进入", "成功")
        return jsonify({"ok": True})
    logger.action("软件", "输入密码进入", "密码错误")
    return jsonify({"ok": False, "msg": "密码不对"})


@app.route("/forgot", methods=["GET"])
def forgot_page():
    """忘记密码页：用激活码重设密码。"""
    import activation
    if not activation.is_activated():
        return redirect(url_for("activate_page"))
    return render_template("forgot.html")


@app.route("/forgot", methods=["POST"])
def do_reset_password():
    """用激活码重设开机密码。要求激活码是本机激活用的那个。"""
    import activation
    data = request.get_json() or {}
    code = data.get("code", "")
    new = (data.get("new", "") or "").strip()
    new2 = (data.get("new2", "") or "").strip()
    ok, msg = activation.verify_reset_code(code)
    if not ok:
        logger.action("软件", "用激活码重置密码", f"失败:{msg}")
        return jsonify({"ok": False, "msg": msg})
    if len(new) < 4:
        return jsonify({"ok": False, "msg": "新密码至少4位"})
    if new != new2:
        return jsonify({"ok": False, "msg": "两次输入的新密码不一样"})
    db.set_app_password(new)
    session["logged_in"] = True  # 重设成功直接进
    logger.action("软件", "用激活码重置密码", "成功")
    return jsonify({"ok": True, "msg": "密码已重置，正在进入软件"})


@app.route("/app_logout", methods=["POST"])
def app_logout():
    """退出登录：清掉本次登录状态，回到密码输入页。"""
    session.pop("logged_in", None)
    return jsonify({"ok": True, "msg": "已退出，需要重新输密码才能进"})


@app.route("/change_password", methods=["POST"])
def change_password():
    """修改开机密码：要先验证旧密码。"""
    data = request.get_json() or {}
    old = data.get("old", "")
    new = (data.get("new", "") or "").strip()
    if not db.check_app_password(old):
        return jsonify({"ok": False, "msg": "旧密码不对"})
    if len(new) < 4:
        return jsonify({"ok": False, "msg": "新密码至少4位"})
    db.set_app_password(new)
    logger.action("软件", "修改开机密码", "成功")
    return jsonify({"ok": True, "msg": "密码已修改"})


@app.route("/")
def index():
    platform = request.args.get("platform", "")
    tag = request.args.get("tag", "")
    keyword = request.args.get("keyword", "")
    days = request.args.get("days", "")
    view = request.args.get("view", "list")
    category = request.args.get("category", "")
    sort = request.args.get("sort", "default")
    batch = request.args.get("batch", "")
    hide_dup = request.args.get("hide_dup", "")
    batch_int = int(batch) if batch else None
    # days 现在是时间段关键词：today/yesterday/3days/5days/7days。
    # 兼容旧的数字值（1=今日，7=最近7天）。
    _range_map = {"1": "today", "7": "7days"}
    date_range = _range_map.get(days, days) or None

    items = db.query_items(
        platform=platform or None, tag=tag or None,
        keyword=keyword or None, limit=500, sort=sort,
        batch_id=batch_int, hide_duplicate=(hide_dup == "1"),
        date_range=date_range,
    )

    # 按榜单分类再过滤（B站的综合热门/排行榜等，微博的热搜等）
    if category:
        items = [it for it in items if it.get("category") == category]

    for it in items:
        try:
            it["trend"] = db.get_trend_direction(it["content_hash"])
        except Exception:
            it["trend"] = "flat"

    # 分板块
    grouped = {t: [] for t in TAG_ORDER}
    grouped["其他"] = []
    for item in items:
        item_tags = [t for t in (item.get("tags") or "").split(",") if t]
        if not item_tags:
            grouped["其他"].append(item)
        else:
            placed = False
            for t in item_tags:
                if t in grouped:
                    grouped[t].append(item)
                    placed = True
            if not placed:
                grouped["其他"].append(item)

    stats = db.item_stats()
    logs = db.get_recent_fetch_logs(limit=10)
    creds = db.get_all_credentials()
    saved_urls = db.get_saved_urls()
    custom_tags = db.get_custom_tags()
    batches = db.get_batches(limit=100)

    cred_panel = []
    for pk, pn in PLATFORM_NAMES.items():
        c = creds.get(pk)
        cred_panel.append({
            "platform": pk, "name": pn,
            "status": c["status"] if c else "未登录",
        })

    # 可选的榜单分类（用于二级筛选）
    all_categories = db.get_all_categories(platform=platform or None)

    return render_template(
        "index.html", items=items, grouped=grouped, stats=stats, logs=logs,
        view=view, platform_names=PLATFORM_NAMES, platform_options=PLATFORM_OPTIONS,
        cred_panel=cred_panel, watch_keywords=WATCH_KEYWORDS, categories=all_categories,
        saved_urls=saved_urls, sort=sort, custom_tags=custom_tags, batches=batches,
        keep_days=db.get_keep_days(),
        filters={"platform": platform, "tag": tag, "keyword": keyword, "days": days,
                 "category": category, "sort": sort, "batch": batch, "hide_dup": hide_dup},
    )


@app.route("/login/<platform>", methods=["POST"])
def login_open(platform):
    """第一步：用Chrome调试端口打开平台网页"""
    from login import open_browser
    r = open_browser(platform)
    return jsonify(r)


@app.route("/read_cookie/<platform>", methods=["POST"])
def login_read(platform):
    """第二步：读cookie"""
    from login import read_cookie
    r = read_cookie(platform)
    return jsonify(r)


@app.route("/logout/<platform>", methods=["POST"])
def logout_route(platform):
    """退出登录：清掉该平台的登录，别人用这台电脑不会自动登录你的账号"""
    from login import logout
    r = logout(platform)
    return jsonify(r)


@app.route("/clear_all", methods=["POST"])
def clear_all_route():
    """清空所有收集到的热点数据（保留登录、过滤词库等配置）"""
    db.clear_all_items()
    return jsonify({"ok": True, "msg": "已清空所有热点数据（登录和过滤词库等设置保留）"})


@app.route("/batch/delete/<int:batch_id>", methods=["POST"])
def delete_batch_route(batch_id):
    """删除某一次收集"""
    db.delete_batch(batch_id)
    return jsonify({"ok": True, "msg": "已删除这次收集的数据"})


@app.route("/prune_old", methods=["POST"])
def prune_old_route():
    """立即按当前设置的保留天数清理老数据（软件启动时也会自动清一次）"""
    try:
        days = db.get_keep_days()
        n = db.prune_old_data()
        return jsonify({"ok": True, "msg": f"已清理{n}条{days}天前的老数据，只保留最近{days}天。"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"清理出错：{type(e).__name__}"})


@app.route("/set_keep_days", methods=["POST"])
def set_keep_days_route():
    """设置数据保留天数，并立即按新天数清理一次。"""
    data = request.get_json() or {}
    days = data.get("days")
    d = db.set_keep_days(days)
    if not d:
        return jsonify({"ok": False, "msg": "请输入有效的天数（1~365）"})
    try:
        n = db.prune_old_data()
        return jsonify({"ok": True, "msg": f"已设置为保留最近{d}天，并清理了{n}条更早的数据。"})
    except Exception:
        return jsonify({"ok": True, "msg": f"已设置为保留最近{d}天。"})


@app.route("/fetch/<platform>", methods=["POST"])
def fetch_now(platform):
    def do():
        _set_task(reset=True)
        _set_task(text=f"正在抓取{PLATFORM_NAMES.get(platform, platform)}...", total=1)
        db.start_new_batch(PLATFORM_NAMES.get(platform, platform), platform=platform)
        try:
            from scheduler import run_once
            results = run_once([platform])
            r = results[0] if results else {}
            if r.get("ok"):
                cate_detail = "、".join(f"{k}:{v}" for k, v in r.get("by_category", {}).items())
                msg = f"{PLATFORM_NAMES.get(platform, platform)} 抓到{r.get('count',0)}条"
                if cate_detail:
                    msg += f"（{cate_detail}）"
                _set_task(done=1, add_result=msg)
            else:
                _set_task(done=1, add_result=f"{PLATFORM_NAMES.get(platform, platform)} 失败: {r.get('error','')[:50]}")
        except Exception as e:
            _set_task(done=1, add_result=f"出错: {e}")
            logger.error(f"手动抓取{platform}失败", e)
        finally:
            db.end_batch()
        _set_task(running=False, text="完成")
    threading.Thread(target=do, daemon=True).start()
    return jsonify({"ok": True, "msg": "started"})


@app.route("/preset_weibo", methods=["POST"])
def preset_weibo():
    """一键预置微博各榜单网址到常用清单"""
    weibo_boards = [
        ("https://s.weibo.com/top/summary?cate=realtimehot", "微博-热搜"),
        ("https://s.weibo.com/top/summary?cate=entrank", "微博-文娱"),
        ("https://s.weibo.com/top/summary?cate=socialevent", "微博-生活"),
        ("https://s.weibo.com/top/summary?cate=tech", "微博-科技"),
        ("https://s.weibo.com/top/summary?cate=life", "微博-社会"),
        ("https://s.weibo.com/top/summary?cate=sport", "微博-体育"),
        ("https://s.weibo.com/top/summary?cate=game", "微博-ACG"),
        ("https://s.weibo.com/top/summary", "微博-热门榜单"),
    ]
    existing = set(u["url"] for u in db.get_saved_urls())
    added = 0
    for url, note in weibo_boards:
        if url not in existing:
            db.add_saved_url(url, note)
            added += 1
    return jsonify({"ok": True, "msg": f"已预置{added}个微博榜单网址到常用，点【一键全抓】即可抓取。如某个抓不到，说明该榜单网址变了，可手动删除替换。"})


@app.route("/open_url", methods=["POST"])
def open_url_route():
    """只打开网址，不抓取（让用户在页面里下拉后再抓）"""
    import requests as _rq
    from login import DEBUG_PORT
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "msg": "请输入网址"})
    if not url.startswith("http"):
        url = "https://" + url
    try:
        try:
            _rq.put(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", timeout=5)
        except Exception:
            _rq.get(f"http://127.0.0.1:{DEBUG_PORT}/json/new?{url}", timeout=5)
        return jsonify({"ok": True, "msg": "已在浏览器打开，请在那个页面往下拉到你要的位置，然后回来点绿色的【抓取浏览器当前页面】"})
    except Exception as e:
        logger.error(f"打开网址失败: {url}", e)
        return jsonify({"ok": False, "msg": f"打开失败: {type(e).__name__}，请确认浏览器窗口开着"})


@app.route("/task_status")
def task_status():
    """前端轮询这个接口，显示抓取进度"""
    return jsonify(TASK_STATUS)


@app.route("/fetch_url", methods=["POST"])
def fetch_url_route():
    """输入网址，打开并抓取（后台跑，前端轮询进度）"""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    note = data.get("note", "").strip()
    if not url:
        return jsonify({"ok": False, "msg": "请输入网址"})

    def do():
        from page_reader import fetch_url, detect_platform
        _set_task(reset=True)
        _set_task(text=f"正在打开并抓取网址...", total=1)
        plat = detect_platform(url) or ""
        db.start_new_batch(note, platform=plat, category=note)
        try:
            r = fetch_url(url, note)
            _set_task(done=1, add_result=r.get("msg", ""))
        except Exception as e:
            _set_task(done=1, add_result=f"出错: {e}")
        finally:
            db.end_batch()
        _set_task(running=False, text="完成")

    threading.Thread(target=do, daemon=True).start()
    return jsonify({"ok": True, "msg": "started"})


@app.route("/saved_urls", methods=["GET"])
def get_saved_urls_route():
    return jsonify({"urls": db.get_saved_urls()})


@app.route("/saved_urls/add", methods=["POST"])
def add_saved_url_route():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    note = data.get("note", "").strip()
    if not url:
        return jsonify({"ok": False, "msg": "请输入网址"})
    db.add_saved_url(url, note)
    return jsonify({"ok": True, "msg": "已保存"})


@app.route("/saved_urls/delete/<int:url_id>", methods=["POST"])
def delete_saved_url_route(url_id):
    db.delete_saved_url(url_id)
    return jsonify({"ok": True})


@app.route("/custom_tags", methods=["GET"])
def get_custom_tags_route():
    return jsonify({"tags": db.get_custom_tags()})


@app.route("/custom_tags/add", methods=["POST"])
def add_custom_tag_route():
    data = request.get_json() or {}
    tag_name = data.get("tag_name", "").strip()
    keywords = data.get("keywords", "").strip()
    if not tag_name or not keywords:
        return jsonify({"ok": False, "msg": "标签名和关键词都要填"})
    db.add_custom_tag(tag_name, keywords)
    return jsonify({"ok": True, "msg": "已添加，以后新抓到的内容会自动套用这个标签"})


@app.route("/custom_tags/delete/<int:tag_id>", methods=["POST"])
def delete_custom_tag_route(tag_id):
    db.delete_custom_tag(tag_id)
    return jsonify({"ok": True})


# ---------- 过滤词库 ----------
@app.route("/filter_words")
def filter_words_page():
    """过滤词库管理页面"""
    return render_template("filter_words.html", words=db.get_filter_words())


@app.route("/filter_words/add", methods=["POST"])
def add_filter_word_route():
    data = request.get_json() or {}
    word = (data.get("word", "") or "").strip()
    match_type = data.get("match_type", "exact")
    if not word:
        return jsonify({"ok": False, "msg": "请输入要过滤的词"})
    ok = db.add_filter_word(word, match_type)
    return jsonify({"ok": True, "msg": "已加入过滤库" if ok else "这个词已经在过滤库里了"})


@app.route("/filter_words/delete/<int:word_id>", methods=["POST"])
def delete_filter_word_route(word_id):
    """从过滤库删除一个词=恢复该词能被正常抓取"""
    db.delete_filter_word(word_id)
    return jsonify({"ok": True})


@app.route("/filter_words/export")
def export_filter_words():
    """导出过滤词库为json文件，方便备份/换电脑"""
    words = [{"word": w["word"], "match_type": w["match_type"]} for w in db.get_filter_words()]
    buf = io.BytesIO(json.dumps(words, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="过滤词库.json",
                     mimetype="application/json")


@app.route("/filter_words/import", methods=["POST"])
def import_filter_words():
    """导入过滤词库json（追加，不覆盖已有）"""
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "msg": "没有选择文件"})
    try:
        data = json.loads(f.read().decode("utf-8"))
        added = 0
        for entry in data:
            if isinstance(entry, str):
                if db.add_filter_word(entry, "exact"):
                    added += 1
            elif isinstance(entry, dict) and entry.get("word"):
                if db.add_filter_word(entry["word"], entry.get("match_type", "exact")):
                    added += 1
        return jsonify({"ok": True, "msg": f"成功导入{added}个新词"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"导入失败：{type(e).__name__}"})


@app.route("/items/batch_delete", methods=["POST"])
def batch_delete_items():
    """批量删除内容。block=True时同时把这些标题加入过滤库（精确匹配）"""
    data = request.get_json() or {}
    ids = data.get("ids", [])
    block = data.get("block", False)
    if not ids:
        return jsonify({"ok": False, "msg": "没有选中任何内容"})
    titles = db.delete_items_by_ids(ids)
    blocked = 0
    if block:
        for t in titles:
            if db.add_filter_word(t, "exact"):
                blocked += 1
    msg = f"已删除{len(ids)}条"
    if block:
        msg += f"，其中{blocked}个标题已加入过滤库（以后不再抓取）"
    return jsonify({"ok": True, "msg": msg})


@app.route("/fetch_all_saved", methods=["POST"])
def fetch_all_saved():
    """一键抓取所有保存的网址（后台跑，前端轮询进度）"""
    def do():
        from page_reader import fetch_url, detect_platform
        urls = db.get_saved_urls()
        _set_task(reset=True)
        _set_task(text="开始一键抓取常用网址", total=len(urls))
        for i, u in enumerate(urls):
            note = u.get("note", "") or u["url"][:20]
            _set_task(text=f"正在抓取第{i+1}/{len(urls)}个：{note}")
            plat = detect_platform(u["url"]) or ""
            db.start_new_batch(note, platform=plat, category=u.get("note", ""))
            try:
                r = fetch_url(u["url"], u.get("note", ""))
                _set_task(done=i+1, add_result=f"{note}: {r.get('msg', '')}")
            except Exception as e:
                _set_task(done=i+1, add_result=f"{note}: 出错{e}")
                logger.error(f"抓取保存的网址失败: {u['url']}", e)
            finally:
                db.end_batch()
        _set_task(running=False, text="全部完成")
    threading.Thread(target=do, daemon=True).start()
    return jsonify({"ok": True, "msg": "started"})


@app.route("/read_pages", methods=["POST"])
def read_pages():
    """通用抓取：读浏览器当前打开的页面内容（后台跑）"""
    data = request.get_json(silent=True) or {}
    note = data.get("note", "").strip()
    def do():
        from page_reader import read_current_pages
        _set_task(reset=True)
        _set_task(text="正在抓取你打开的页面...", total=1)
        db.start_new_batch(note)
        try:
            r = read_current_pages(user_note=note)
            _set_task(done=1, add_result=r.get("msg", ""))
        except Exception as e:
            _set_task(done=1, add_result=f"出错: {e}")
        finally:
            db.end_batch()
        _set_task(running=False, text="完成")
    threading.Thread(target=do, daemon=True).start()
    return jsonify({"ok": True, "msg": "started"})


@app.route("/analysis")
def analysis():
    """数据分析页：跨平台汇总 + 今日摘要"""
    from analyzer import daily_summary
    date_range = request.args.get("range", "3days")
    if date_range not in ("today", "3days", "7days", "all"):
        date_range = "3days"
    summary = daily_summary(date_range=date_range)
    cross = summary.get("cross_all", [])
    return render_template("analysis.html", cross=cross, summary=summary,
                           platform_names=PLATFORM_NAMES, date_range=date_range)


@app.route("/analysis/export_cross")
def export_cross():
    """把跨平台热点话题导出成Excel（含每条的网址）"""
    from analyzer import daily_summary
    date_range = request.args.get("range", "3days")
    groups = daily_summary(date_range=date_range).get("cross_all", [])
    try:
        from openpyxl import Workbook
    except ImportError:
        return "需要安装openpyxl", 500
    wb = Workbook(); ws = wb.active; ws.title = "跨平台话题"
    ws.append(["话题", "涉及平台数", "总条数", "总热度", "来源平台", "来源榜单", "标题", "链接"])
    for g in groups:
        for it in g["entries"]:
            ws.append([
                g["title"], g["platform_count"], g["count"], g.get("total_heat", 0),
                PLATFORM_NAMES.get(it["platform"], it["platform"]),
                it.get("category", ""), it["title"], it.get("url", ""),
            ])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="跨平台话题.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/analysis/export_pool")
def export_pool():
    """导出选题池（需求类/疑问类/求推荐类）单个板块"""
    from analyzer import daily_summary
    pool = request.args.get("pool", "demand")
    date_range = request.args.get("range", "3days")
    summary = daily_summary(date_range=date_range)
    mapping = {
        "demand": ("需求类内容", summary.get("demand_top", [])),
        "question": ("疑问类选题", summary.get("question_top", [])),
        "reco": ("求推荐求助", summary.get("reco_top", [])),
        "today": ("今日新冒出热点", summary.get("today_hot", [])),
    }
    name, rows = mapping.get(pool, mapping["demand"])
    try:
        from openpyxl import Workbook
    except ImportError:
        return "需要安装openpyxl", 500
    wb = Workbook(); ws = wb.active; ws.title = name[:20]
    ws.append(["平台", "榜单", "标题", "热度", "链接"])
    for it in rows:
        ws.append([
            PLATFORM_NAMES.get(it["platform"], it["platform"]),
            it.get("category", ""), it["title"],
            it.get("heat", 0) or 0, it.get("url", ""),
        ])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{name}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/view_log")
def view_log():
    """在网页里直接看日志"""
    import logger as lg
    content = lg.read_recent(200)
    return f"<html><head><meta charset='utf-8'><title>软件日志</title></head><body style='font-family:monospace;padding:20px;background:#1e1e1e;color:#ddd;'><h3 style='color:#4caf50;'>软件日志（最近200行）</h3><pre style='white-space:pre-wrap;font-size:12px;'>{content}</pre></body></html>"


@app.route("/export")
def export_excel():
    platform = request.args.get("platform", "")
    category = request.args.get("category", "")
    tag = request.args.get("tag", "")
    keyword = request.args.get("keyword", "")
    days = request.args.get("days", "")
    batch = request.args.get("batch", "")
    hide_dup = request.args.get("hide_dup", "")
    _range_map = {"1": "today", "7": "7days"}
    date_range = _range_map.get(days, days) or None
    batch_int = int(batch) if batch else None
    items = db.query_items(platform=platform or None, category=category or None,
                           tag=tag or None, keyword=keyword or None, limit=2000,
                           batch_id=batch_int, hide_duplicate=(hide_dup == "1"), date_range=date_range)
    try:
        from openpyxl import Workbook
    except ImportError:
        return "需要安装openpyxl", 500
    wb = Workbook(); ws = wb.active; ws.title = "热点数据"
    ws.append(["收集批次", "是否与上次重复", "标题", "平台", "榜单", "标签", "出现次数", "最近出现", "链接"])
    for it in items:
        ws.append([it.get("batch_label", "") or "", "是" if it.get("is_duplicate") else "",
                   it["title"], PLATFORM_NAMES.get(it["platform"], it["platform"]),
                   it.get("category", ""), it.get("tags", ""), it["seen_count"],
                   it["last_seen"], it.get("url", "")])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="热点数据.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    db.init_db()
    db.seed_default_filter_words()
    app.run(host="127.0.0.1", port=5000, debug=False)
