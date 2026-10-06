# -*- coding: utf-8 -*-
"""自检。出问题看软件日志.txt，或把本输出发出来。"""
import sys
RESULTS = []
def check(name, optional=False):
    def deco(fn):
        def wrap():
            try: RESULTS.append((name, True, fn() or "OK", optional))
            except Exception as e: RESULTS.append((name, False, f"{type(e).__name__}: {e}", optional))
        return wrap
    return deco

@check("1. Python依赖库")
def c1():
    import requests, flask, openpyxl, websocket
    return "requests/flask/openpyxl/websocket-client 都就绪"

@check("2. 数据库")
def c3():
    import db
    db.init_db()
    db.save_credential("_t","ck","有效")
    assert db.get_credential("_t")["status"]=="有效"
    db.upsert_item(platform="_t",title="测试",category="x",tags="y")
    db.snapshot_trends()
    conn=db.get_conn();cur=conn.cursor()
    cur.execute("DELETE FROM items WHERE platform='_t'")
    cur.execute("DELETE FROM credentials WHERE platform='_t'")
    conn.commit();conn.close()
    return "读写正常"

@check("3. 打标签")
def c4():
    from tagger import tag_content
    r=tag_content("有没有好用的PDF转Word工具")
    assert "需求类" in r and "效率工具" in r
    return "标签正确"

@check("4. 日志系统")
def c5():
    import logger
    logger.info("自检")
    import os
    assert os.path.exists(logger.LOG_PATH)
    return "日志正常，报错会记入 软件日志.txt"

@check("5. 抓取器可导入")
def c6():
    from scrapers import weibo, bilibili, zhihu, xiaohongshu
    return "微博/B站五榜/知乎/小红书 抓取器就绪"

@check("6. 登录模块+找浏览器")
def c7():
    from login import find_browser, open_browser, read_cookie
    b = find_browser()
    if b:
        return f"登录模块就绪，找到浏览器: {b.split(chr(92))[-1]}"
    else:
        return "登录模块就绪（但没找到Chrome/Edge，登录功能需要装其一）"

@check("7. 界面渲染")
def c8():
    import db; db.init_db()
    from webapp import app
    assert app.test_client().get("/").status_code==200
    return "界面正常"

def main():
    print("="*50); print("热点收集器 - 自检"); print("="*50)
    c1();c3();c4();c5();c6();c7();c8()
    print()
    ok=0
    for n,p,d,o in RESULTS:
        print(f"{'✓ 通过' if p else '✗ 失败'}  {n}"); print(f"        {d}")
        if p: ok+=1
    print(); print(f"总计: {ok}/{len(RESULTS)} 通过")
    if ok==len(RESULTS): print("✓ 全部就绪，双击 启动.bat")
    else: print("✗ 有失败，看 软件日志.txt 或把本输出发出来")
    return 0 if ok==len(RESULTS) else 1

if __name__=="__main__":
    sys.exit(main())
