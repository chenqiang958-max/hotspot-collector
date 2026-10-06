# -*- coding: utf-8 -*-
"""数据库模块：建表、存数据、查询、cookie管理、趋势历史"""
import sqlite3
import os
import hashlib
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "trends.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT,
            platform TEXT NOT NULL,
            category TEXT,
            title TEXT NOT NULL,
            url TEXT,
            extra TEXT,
            search_keyword TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            seen_count INTEGER DEFAULT 1,
            tags TEXT,
            platforms_seen TEXT,
            heat INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            pub_time TEXT,
            rank_no INTEGER DEFAULT 0
        )
    """)
    # 老库升级：如果没有这些新列就加上
    for col, coltype in [("heat","INTEGER DEFAULT 0"),("likes","INTEGER DEFAULT 0"),("pub_time","TEXT"),("rank_no","INTEGER DEFAULT 0"),
                         ("batch_id","INTEGER DEFAULT 0"),("collected_at","TEXT"),("is_duplicate","INTEGER DEFAULT 0")]:
        try:
            cur.execute(f"ALTER TABLE items ADD COLUMN {col} {coltype}")
        except Exception:
            pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_batch ON items(batch_id)")
    # 老库迁移：早期版本 content_hash 带 UNIQUE 约束，会导致同一标题跨批次存不进第二行。
    # 检测到就重建表去掉该约束（数据完整保留）。
    try:
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='items'")
        tbl_sql = (cur.fetchone() or [""])[0] or ""
        if "content_hash TEXT UNIQUE" in tbl_sql.replace("\n", " ").replace("  ", " ") or "content_hash TEXT UNIQUE" in tbl_sql:
            cur.execute("PRAGMA table_info(items)")
            cols = [r[1] for r in cur.fetchall()]
            col_list = ",".join(cols)
            cur.execute("ALTER TABLE items RENAME TO items_old_unique")
            cur.execute("""
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_hash TEXT, platform TEXT NOT NULL, category TEXT,
                    title TEXT NOT NULL, url TEXT, extra TEXT, search_keyword TEXT,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                    seen_count INTEGER DEFAULT 1, tags TEXT, platforms_seen TEXT,
                    heat INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, pub_time TEXT,
                    rank_no INTEGER DEFAULT 0, batch_id INTEGER DEFAULT 0,
                    collected_at TEXT, is_duplicate INTEGER DEFAULT 0
                )
            """)
            cur.execute(f"INSERT INTO items ({col_list}) SELECT {col_list} FROM items_old_unique")
            cur.execute("DROP TABLE items_old_unique")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_batch ON items(batch_id)")
    except Exception:
        pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_platform ON items(platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_last_seen ON items(last_seen)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tags ON items(tags)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            run_time TEXT NOT NULL,
            status TEXT NOT NULL,
            item_count INTEGER DEFAULT 0,
            error_msg TEXT
        )
    """)

    # cookie存储表：每个平台一行
    cur.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            platform TEXT PRIMARY KEY,
            cookie TEXT,
            updated_at TEXT,
            status TEXT
        )
    """)

    # 趋势历史表：记录每个词每天的出现次数快照，用于算涨跌
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trend_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL,
            title TEXT,
            snapshot_date TEXT NOT NULL,
            seen_count INTEGER,
            UNIQUE(content_hash, snapshot_date)
        )
    """)
    # 保存的常用网址清单
    cur.execute("""
        CREATE TABLE IF NOT EXISTS saved_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            note TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_name TEXT NOT NULL,
            keywords TEXT NOT NULL,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS filter_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE,
            match_type TEXT NOT NULL DEFAULT 'exact',
            created_at TEXT
        )
    """)
    # 收集批次表：每次收集（可能5个账号一起）算一批，标注收集时间。
    # 间隔1小时以上才开新批次，1小时内的收集都归到同一批。
    cur.execute("""
        CREATE TABLE IF NOT EXISTS collect_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            last_at TEXT NOT NULL,
            label TEXT,
            platform TEXT,
            category TEXT
        )
    """)
    # 老库升级：给批次表补platform/category列
    for col in ["platform", "category"]:
        try:
            cur.execute(f"ALTER TABLE collect_batches ADD COLUMN {col} TEXT")
        except Exception:
            pass
    # 软件设置表（存开机密码的哈希等）。key-value形式。
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


BATCH_GAP_MINUTES = 60  # 旧逻辑兜底用
SAME_BOARD_MERGE_MINUTES = 30  # 同一个平台+榜单，间隔在这个分钟数内算同一批（防手抖多点）

# 记录“本次抓取动作”正在写入的批次id。
_CURRENT_BATCH = {"id": None}


def start_new_batch(label_note="", platform="", category=""):
    """
    开始一次抓取，决定这次数据写入哪个批次。
    规则：
    - 小红书（platform=xiaohongshu）：每次都开新批次（因为你每次抓的页面/内容不同）。
    - 其他平台：如果“同一个平台+同一个榜单”在最近 SAME_BOARD_MERGE_MINUTES 分钟内
      已经有批次，就复用它（防止手抖多点几次生成一堆重复批次）；否则开新批次。
    - platform/category 传不进来时（比如通用抓网页），退化为“每次开新批”。
    返回批次id。
    """
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now()
    now_str = now.isoformat(timespec="seconds")

    reuse_id = None
    # 小红书永远新开；其他平台在30分钟内尝试合并
    if platform and platform != "xiaohongshu":
        cutoff = (now - timedelta(minutes=SAME_BOARD_MERGE_MINUTES)).isoformat(timespec="seconds")
        if category:
            # 有榜单信息：按“平台+榜单”找30分钟内的批次
            cur.execute("""SELECT id FROM collect_batches
                           WHERE platform=? AND category=? AND last_at>=?
                           ORDER BY id DESC LIMIT 1""", (platform, category, cutoff))
        else:
            # 无榜单信息（整轮抓取）：按“平台”找30分钟内、且同样没细分榜单的批次
            cur.execute("""SELECT id FROM collect_batches
                           WHERE platform=? AND (category IS NULL OR category='') AND last_at>=?
                           ORDER BY id DESC LIMIT 1""", (platform, cutoff))
        row = cur.fetchone()
        if row:
            reuse_id = row["id"]

    if reuse_id is not None:
        cur.execute("UPDATE collect_batches SET last_at=? WHERE id=?", (now_str, reuse_id))
        batch_id = reuse_id
    else:
        label = now.strftime("%m月%d日 %H:%M")
        if label_note:
            label = f"{label} {label_note}"
        cur.execute("""INSERT INTO collect_batches (started_at, last_at, label, platform, category)
                       VALUES (?, ?, ?, ?, ?)""", (now_str, now_str, label, platform, category))
        batch_id = cur.lastrowid
    conn.commit()
    conn.close()
    _CURRENT_BATCH["id"] = batch_id
    return batch_id


def get_or_create_batch():
    """
    返回当前应该写入的批次id。
    新逻辑：优先用 start_new_batch() 开好的“本次抓取批次”。
    如果没开过（比如直接调用、或老的定时任务），才退回到“1小时合并”的旧规则兜底。
    """
    # 如果本次抓取已经用 start_new_batch 开了批，直接用它（这一轮所有内容进同一批）
    if _CURRENT_BATCH["id"] is not None:
        return _CURRENT_BATCH["id"]

    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now()
    now_str = now.isoformat(timespec="seconds")
    cur.execute("SELECT id, last_at FROM collect_batches ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    batch_id = None
    if row:
        try:
            last = datetime.fromisoformat(row["last_at"])
            gap = (now - last).total_seconds() / 60.0
        except Exception:
            gap = BATCH_GAP_MINUTES + 1
        if gap < BATCH_GAP_MINUTES:
            batch_id = row["id"]
            cur.execute("UPDATE collect_batches SET last_at=? WHERE id=?", (now_str, batch_id))
    if batch_id is None:
        label = now.strftime("%m月%d日 %H:%M")
        cur.execute("INSERT INTO collect_batches (started_at, last_at, label) VALUES (?, ?, ?)",
                    (now_str, now_str, label))
        batch_id = cur.lastrowid
    conn.commit()
    conn.close()
    return batch_id


def end_batch():
    """一次抓取结束，清掉当前批次记忆，下次抓取会开新的一批。"""
    _CURRENT_BATCH["id"] = None


def get_all_categories(platform=None):
    """
    返回库里出现过的所有榜单名（去重、排序）。
    用于筛选下拉框，必须查全库、不受数量限制，否则某些榜单（如微博-文娱）会漏掉。
    platform: 传了就只返回该平台的榜单。
    """
    conn = get_conn()
    cur = conn.cursor()
    if platform:
        cur.execute("SELECT DISTINCT category FROM items WHERE category != '' AND platform=? ORDER BY category", (platform,))
    else:
        cur.execute("SELECT DISTINCT category FROM items WHERE category != '' ORDER BY category")
    cats = [r["category"] for r in cur.fetchall()]
    conn.close()
    return cats


def get_batches(limit=200):
    """返回所有收集批次（最新在前），带每批实际条数。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.id, b.started_at, b.last_at, b.label, b.platform, b.category,
               (SELECT COUNT(*) FROM items WHERE batch_id=b.id) AS item_count
        FROM collect_batches b
        ORDER BY b.id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def make_hash(platform, title):
    normalized = "".join(title.lower().split())
    return hashlib.md5(f"{platform}:{normalized}".encode("utf-8")).hexdigest()


def make_cross_hash(title):
    """跨平台去重用的hash：不含平台名，只看标题"""
    normalized = "".join(title.lower().split())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def upsert_item(platform, title, url="", category="", extra="", search_keyword="", tags="",
                heat=0, likes=0, pub_time="", rank_no=0, batch_id=None):
    """
    按批次存储：每次收集（batch）的数据各自成行、互相分开。
    - 同一批次内、同平台同标题只留一行（合并标签，避免同一次抓重复）。
    - 跨批次保留各自独立记录（这样每次收集的结果不会混在一起）。
    - 如果之前的批次里出现过相同（平台+标题）内容，本条标记 is_duplicate=1（“和上次一样的热搜”）。
    """
    # 命中过滤词库的内容直接丢弃，不入库（默认精确匹配，用户可在过滤词库管理里增删）
    try:
        if is_filtered(title):
            return
    except Exception:
        pass  # 过滤词库出问题时不影响正常入库

    if batch_id is None:
        batch_id = get_or_create_batch()

    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    h = make_hash(platform, title)

    # 1) 同批内是否已存在同一条（同平台+同标题）→ 合并标签，不新增
    cur.execute("SELECT id, tags FROM items WHERE content_hash=? AND batch_id=?", (h, batch_id))
    same = cur.fetchone()
    if same:
        old_tags = set(t for t in (same["tags"] or "").split(",") if t)
        new_tags = set(t for t in (tags or "").split(",") if t)
        merged_tags = ",".join(sorted(old_tags | new_tags))
        cur.execute("""
            UPDATE items SET last_seen=?, seen_count=seen_count+1, tags=?,
                url=COALESCE(NULLIF(?, ''), url), heat=MAX(heat, ?), likes=MAX(likes, ?),
                pub_time=COALESCE(NULLIF(?, ''), pub_time), rank_no=?
            WHERE id=?
        """, (now, merged_tags, url, heat, likes, pub_time, rank_no, same["id"]))
        conn.commit(); conn.close()
        return same["id"]

    # 2) 过去12小时内的更早批次里出现过同样内容吗？出现过→本条标记为“与上次重复”。
    #    只看12小时窗口：超过12小时前出现过的算“重新冒出来的热点”，不算重复。
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(hours=12)).isoformat(timespec="seconds")
    cur.execute(
        "SELECT COUNT(*) AS n FROM items "
        "WHERE content_hash=? AND batch_id<>? AND collected_at>=?",
        (h, batch_id, cutoff),
    )
    is_dup = 1 if cur.fetchone()["n"] > 0 else 0

    cur.execute("""
        INSERT INTO items (content_hash, platform, category, title, url, extra, search_keyword,
            first_seen, last_seen, seen_count, tags, platforms_seen, heat, likes, pub_time, rank_no,
            batch_id, collected_at, is_duplicate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (h, platform, category, title, url, extra, search_keyword, now, now, tags, platform,
          heat, likes, pub_time, rank_no, batch_id, now, is_dup))
    result_id = cur.lastrowid
    conn.commit()
    conn.close()
    return result_id


def log_fetch(platform, status, item_count=0, error_msg=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO fetch_log (platform, run_time, status, item_count, error_msg)
        VALUES (?, ?, ?, ?, ?)
    """, (platform, datetime.now().isoformat(timespec="seconds"), status, item_count, error_msg))
    conn.commit()
    conn.close()


def query_items_deduped(limit=2000):
    """
    给数据分析用：同一条内容（content_hash）只返回一行（保留最新批次那条），
    并把该内容在所有批次里的出现总次数汇总到 seen_count、最高热度汇总到 heat。
    这样跨平台聚合、今日摘要不会因为“每批存一行”而把同一条重复计入。
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM items
        WHERE id IN (
            SELECT id FROM items GROUP BY content_hash HAVING id=MAX(id)
        )
        ORDER BY batch_id DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    # 汇总每个内容的总出现次数和最高热度
    cur.execute("""SELECT content_hash, SUM(seen_count) as tot, MAX(heat) as mh,
                          MIN(first_seen) as ff
                   FROM items GROUP BY content_hash""")
    agg = {r["content_hash"]: r for r in cur.fetchall()}
    conn.close()
    for it in rows:
        a = agg.get(it["content_hash"])
        if a:
            it["seen_count"] = a["tot"]
            it["heat"] = max(it.get("heat", 0) or 0, a["mh"] or 0)
            it["first_seen"] = a["ff"] or it.get("first_seen")
    return rows


def query_items(platform=None, tag=None, keyword=None, days=None, limit=300, sort="default", category=None,
                batch_id=None, hide_duplicate=False, date_range=None):
    conn = get_conn()
    cur = conn.cursor()
    sql = """SELECT items.*, b.label AS batch_label
             FROM items LEFT JOIN collect_batches b ON items.batch_id=b.id WHERE 1=1"""
    params = []
    if platform:
        sql += " AND items.platform=?"
        params.append(platform)
    if category:
        sql += " AND items.category=?"
        params.append(category)
    if batch_id:
        sql += " AND items.batch_id=?"
        params.append(batch_id)
    if hide_duplicate:
        sql += " AND items.is_duplicate=0"
    if tag:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    if keyword:
        sql += " AND title LIKE ?"
        params.append(f"%{keyword}%")
    if days:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        sql += " AND last_seen >= ?"
        params.append(cutoff)
    if date_range:
        # 用“收集时间”判断（老数据没有就用last_seen兜底）
        col = "COALESCE(NULLIF(collected_at,''), last_seen)"
        now = datetime.now()
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if date_range == "today":
            sql += f" AND {col} >= ?"
            params.append(today0.isoformat(timespec="seconds"))
        elif date_range == "yesterday":
            y0 = today0 - timedelta(days=1)
            sql += f" AND {col} >= ? AND {col} < ?"
            params.append(y0.isoformat(timespec="seconds"))
            params.append(today0.isoformat(timespec="seconds"))
        elif date_range in ("3days", "5days", "7days"):
            n = {"3days": 3, "5days": 5, "7days": 7}[date_range]
            start = today0 - timedelta(days=n - 1)  # 含今天在内的最近n天
            sql += f" AND {col} >= ?"
            params.append(start.isoformat(timespec="seconds"))
    # 排序方式
    order_map = {
        "default": "batch_id DESC, seen_count DESC, last_seen DESC",  # 按收集批次分开，最新一次在前
        "heat": "heat DESC",              # 热度/播放量高到低
        "likes": "likes DESC",            # 点赞高到低
        "pub_new": "pub_time DESC",       # 最新发布
        "pub_old": "pub_time ASC",        # 最早发布
        "rank": "rank_no ASC",            # 榜单排名
        "cross": "seen_count DESC",       # 多平台上榜（seen_count高）
    }
    order = order_map.get(sort, order_map["default"])
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_recent_fetch_logs(limit=50):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM fetch_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def item_stats():
    """统计数字全部按“不同的内容”去重计算（同一条热搜被多批抓到只算一次），
    否则每抓一轮所有数字就翻倍膨胀。明细列表另外按批次分开展示，互不影响。"""
    conn = get_conn()
    cur = conn.cursor()
    # 各平台（去重：同一条只算一次）
    cur.execute("""SELECT platform, COUNT(DISTINCT content_hash) as cnt FROM items
                   GROUP BY platform ORDER BY cnt DESC""")
    by_platform = {r["platform"]: r["cnt"] for r in cur.fetchall()}
    # 总数（去重）
    cur.execute("SELECT COUNT(DISTINCT content_hash) as total FROM items")
    total = cur.fetchone()["total"]
    # 各榜单（去重）
    cur.execute("""SELECT category, COUNT(DISTINCT content_hash) as cnt FROM items
                   WHERE category != '' GROUP BY category ORDER BY cnt DESC""")
    by_category = {r["category"]: r["cnt"] for r in cur.fetchall()}
    # 今日新增：今天“第一次”出现的不同内容数（按最早first_seen在今天算）
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("""SELECT COUNT(*) as cnt FROM (
                       SELECT content_hash, MIN(first_seen) as ff FROM items GROUP BY content_hash
                   ) WHERE ff LIKE ?""", (today + "%",))
    today_new = cur.fetchone()["cnt"]

    # 各标签：同一条内容只算一次（按content_hash去重后再拆标签）
    cur.execute("""SELECT tags FROM items GROUP BY content_hash""")
    by_tag = {}
    for r in cur.fetchall():
        for t in (r["tags"] or "").split(","):
            t = t.strip()
            if t:
                by_tag[t] = by_tag.get(t, 0) + 1
    by_tag = dict(sorted(by_tag.items(), key=lambda x: -x[1]))
    conn.close()

    return {
        "total": total, "by_platform": by_platform,
        "by_category": by_category, "by_tag": by_tag,
        "today_new": today_new,
    }


# ============ cookie管理 ============
def save_credential(platform, cookie, status="有效"):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")
    cur.execute("""
        INSERT INTO credentials (platform, cookie, updated_at, status)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(platform) DO UPDATE SET cookie=?, updated_at=?, status=?
    """, (platform, cookie, now, status, cookie, now, status))
    conn.commit()
    conn.close()


def get_credential(platform):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM credentials WHERE platform=?", (platform,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_credentials():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM credentials")
    rows = {r["platform"]: dict(r) for r in cur.fetchall()}
    conn.close()
    return rows


def clear_credential(platform):
    """退出登录：删掉该平台存的cookie记录。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM credentials WHERE platform=?", (platform,))
    conn.commit()
    conn.close()


def set_credential_status(platform, status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE credentials SET status=? WHERE platform=?", (status, platform))
    conn.commit()
    conn.close()


# ============ 趋势历史 ============
def snapshot_trends():
    """把当前所有item的seen_count按今天日期存一份快照，用于算涨跌"""
    conn = get_conn()
    cur = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT content_hash, title, seen_count FROM items")
    for row in cur.fetchall():
        cur.execute("""
            INSERT INTO trend_history (content_hash, title, snapshot_date, seen_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(content_hash, snapshot_date) DO UPDATE SET seen_count=?
        """, (row["content_hash"], row["title"], today, row["seen_count"], row["seen_count"]))
    conn.commit()
    conn.close()


def get_trend_direction(content_hash):
    """
    返回这个词相比昨天的趋势: 'up' / 'down' / 'flat' / 'new'
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT snapshot_date, seen_count FROM trend_history
        WHERE content_hash=? ORDER BY snapshot_date DESC LIMIT 2
    """, (content_hash,))
    rows = cur.fetchall()
    conn.close()
    if len(rows) < 2:
        return "new"
    today_count, prev_count = rows[0]["seen_count"], rows[1]["seen_count"]
    if today_count > prev_count:
        return "up"
    elif today_count < prev_count:
        return "down"
    return "flat"


if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化: {DB_PATH}")


# ============ 常用网址清单 ============
def add_saved_url(url, note=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO saved_urls (url, note, created_at) VALUES (?, ?, ?)",
                (url, note, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def get_saved_urls():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM saved_urls ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_saved_url(url_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM saved_urls WHERE id=?", (url_id,))
    conn.commit()
    conn.close()


def add_custom_tag(tag_name, keywords):
    """新增一个自定义标签规则。keywords是逗号分隔的关键词字符串。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO custom_tags (tag_name, keywords, created_at) VALUES (?, ?, ?)",
                (tag_name.strip(), keywords.strip(), datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def get_custom_tags():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM custom_tags ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_custom_tag(tag_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM custom_tags WHERE id=?", (tag_id,))
    conn.commit()
    conn.close()


# ---------- 过滤词库 ----------
# 内置的知乎/通用页面固定菜单词（首次建库时预置，之后用户可自行增删）
_DEFAULT_FILTER_WORDS = [
    "综合", "用户", "论文", "专栏", "盐选内容", "电子书", "圈子", "话题", "视频", "想法",
    "关注", "推荐", "热榜", "会员", "首页", "发现", "等你来答", "创作中心",
]


def add_filter_word(word, match_type="exact"):
    """加一个过滤词。match_type: exact=整条标题相等才拦, contains=含该词即拦"""
    word = (word or "").strip()
    if not word:
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT OR IGNORE INTO filter_words (word, match_type, created_at) VALUES (?, ?, ?)",
                    (word, match_type if match_type in ("exact", "contains") else "exact",
                     datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        ok = cur.rowcount > 0
    finally:
        conn.close()
    return ok


def get_filter_words():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM filter_words ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_filter_word(word_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM filter_words WHERE id=?", (word_id,))
    conn.commit()
    conn.close()


def seed_default_filter_words():
    """首次建库时把内置菜单词写进去（已存在则跳过）。只在词库为空时执行，避免用户删掉的词又被塞回来。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM filter_words")
    n = cur.fetchone()["n"]
    conn.close()
    if n == 0:
        for w in _DEFAULT_FILTER_WORDS:
            add_filter_word(w, "exact")


def is_filtered(title, words_cache=None):
    """判断一条标题是否命中过滤词库。words_cache可传入get_filter_words()结果避免重复查库。"""
    t = (title or "").strip()
    if not t:
        return False
    words = words_cache if words_cache is not None else get_filter_words()
    for w in words:
        word = w["word"]
        if w["match_type"] == "contains":
            if word in t:
                return True
        else:  # exact
            if t == word:
                return True
    return False


def clear_all_items():
    """清空所有收集到的热点数据（items和批次记录、抓取日志、趋势历史）。
    不动登录cookie、过滤词库、自定义标签、常用网址这些配置。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM items")
    cur.execute("DELETE FROM collect_batches")
    cur.execute("DELETE FROM fetch_log")
    cur.execute("DELETE FROM trend_history")
    conn.commit()
    conn.close()


def delete_batch(batch_id):
    """删除某一次收集（该批次的所有数据 + 批次记录）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE batch_id=?", (batch_id,))
    cur.execute("DELETE FROM collect_batches WHERE id=?", (batch_id,))
    conn.commit()
    conn.close()


def get_keep_days():
    """读取用户设置的“数据保留天数”，没设过默认3天。范围1~365。"""
    v = get_setting("keep_days")
    try:
        d = int(v)
        if d < 1:
            d = 1
        if d > 365:
            d = 365
        return d
    except Exception:
        return 3


def set_keep_days(days):
    """设置数据保留天数。"""
    try:
        d = int(days)
    except Exception:
        return False
    if d < 1:
        d = 1
    if d > 365:
        d = 365
    set_setting("keep_days", str(d))
    return d


def prune_old_data(keep_days=None):
    """
    只保留最近 keep_days 天的数据，更早的自动删掉（含对应的批次、趋势快照）。
    keep_days 不传就用用户设置的值（默认3天）。
    按“收集时间 collected_at”判断；老数据没有这个字段的用 last_seen 兜底。
    返回删掉的条数。
    """
    if keep_days is None:
        keep_days = get_keep_days()
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec="seconds")
    conn = get_conn()
    cur = conn.cursor()
    # 先算要删多少条（用collected_at，没有就用last_seen）
    cur.execute("""SELECT COUNT(*) AS n FROM items
                   WHERE COALESCE(NULLIF(collected_at,''), last_seen) < ?""", (cutoff,))
    n = cur.fetchone()["n"]
    cur.execute("""DELETE FROM items
                   WHERE COALESCE(NULLIF(collected_at,''), last_seen) < ?""", (cutoff,))
    # 清掉已经没有任何数据的空批次
    cur.execute("""DELETE FROM collect_batches
                   WHERE id NOT IN (SELECT DISTINCT batch_id FROM items WHERE batch_id IS NOT NULL)""")
    # 清掉过期的趋势快照
    cur.execute("DELETE FROM trend_history WHERE snapshot_date < ?",
                ((datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d"),))
    conn.commit()
    conn.close()
    return n


def delete_items_by_ids(ids):
    """批量删除内容，返回被删条目的标题列表（供调用方决定是否加入过滤库）"""
    if not ids:
        return []
    conn = get_conn()
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in ids)
    cur.execute(f"SELECT title FROM items WHERE id IN ({placeholders})", tuple(ids))
    titles = [r["title"] for r in cur.fetchall()]
    cur.execute(f"DELETE FROM items WHERE id IN ({placeholders})", tuple(ids))
    conn.commit()
    conn.close()
    return titles


# ============ 开机密码 ============
import secrets as _secrets


def _hash_password(password, salt):
    """用 salt + sha256 多轮哈希，避免存明文密码。"""
    h = (salt + password).encode("utf-8")
    for _ in range(100000):
        h = hashlib.sha256(h).digest()
    return h.hex()


def set_app_password(password):
    """设置/修改开机密码。存的是加盐哈希，不是明文。"""
    password = (password or "").strip()
    if not password:
        return False
    salt = _secrets.token_hex(16)
    pwd_hash = _hash_password(password, salt)
    conn = get_conn()
    cur = conn.cursor()
    for k, v in [("pwd_salt", salt), ("pwd_hash", pwd_hash)]:
        cur.execute("""INSERT INTO app_settings (key, value) VALUES (?, ?)
                       ON CONFLICT(key) DO UPDATE SET value=?""", (k, v, v))
    conn.commit()
    conn.close()
    return True


def has_app_password():
    """是否已经设置过开机密码。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key='pwd_hash'")
    row = cur.fetchone()
    conn.close()
    return bool(row and row["value"])


def check_app_password(password):
    """校验输入的密码对不对。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM app_settings WHERE key IN ('pwd_salt','pwd_hash')")
    kv = {r["key"]: r["value"] for r in cur.fetchall()}
    conn.close()
    salt = kv.get("pwd_salt"); real = kv.get("pwd_hash")
    if not salt or not real:
        return False
    return _hash_password((password or "").strip(), salt) == real


def clear_app_password():
    """清除开机密码（忘记密码时的后门：删掉密码记录，重新走首次设置）。"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM app_settings WHERE key IN ('pwd_salt','pwd_hash')")
    conn.commit()
    conn.close()


# ============ 通用设置 & 激活码记录 ============
def get_setting(key, default=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO app_settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value=?""", (key, value, value))
    conn.commit()
    conn.close()


def _ensure_code_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS used_codes (
            code TEXT PRIMARY KEY,
            machine_fp TEXT,
            activated_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_code_bound_machine(code):
    """这个激活码已经绑定到哪台机器了？没绑过返回None。"""
    _ensure_code_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT machine_fp FROM used_codes WHERE code=?", (code,))
    row = cur.fetchone()
    conn.close()
    return row["machine_fp"] if row else None


def bind_code_to_machine(code, machine_fp):
    """把激活码绑定到本机（记下来，防止同码激活第二台）。"""
    _ensure_code_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""INSERT OR IGNORE INTO used_codes (code, machine_fp, activated_at)
                   VALUES (?, ?, ?)""",
                (code, machine_fp, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def rebind_code_to_machine(code, machine_fp):
    """把已存在的激活码更新绑定到新的机器指纹。
    仅用于“本机因老版本指纹不稳定而指纹变化”的恢复场景。"""
    _ensure_code_table()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE used_codes SET machine_fp=? WHERE code=?", (machine_fp, code))
    conn.commit()
    conn.close()
