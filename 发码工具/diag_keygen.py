# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys, re, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "check_keygen_report.txt")
LINES = []


def say(s=""):
    print(s)
    LINES.append(str(s))


def main():
    say("=" * 56)
    say("热点采集 发码自检")
    say("=" * 56)
    say("目录: " + HERE)
    say("解释器: " + sys.executable)
    say("版本: " + sys.version.replace("\n", " "))
    say("")

    say("一、文件")
    for fn in ("发码工具.py", "已生成的激活码.json"):
        p = os.path.join(HERE, fn)
        if os.path.isfile(p):
            say("[OK]   {}  {} 字节".format(fn, os.path.getsize(p)))
        else:
            say("[FAIL] 缺少 " + fn)

    act = os.path.abspath(os.path.join(HERE, "..", "hotspot", "activation.py"))
    if os.path.isfile(act):
        say("[OK]   找到软件端 activation.py")
    else:
        say("[WARN] 未在上级 hotspot/ 找到 activation.py，无法核对 SECRET")
    say("")

    say("二、Tkinter（发码窗口）")
    try:
        import tkinter
        say("[OK]   tkinter 可用")
    except Exception as e:
        say("[FAIL] tkinter 不可用: {}".format(e))
        say("       重装 Python 时勾选 tcl/tk")
    say("")

    say("三、SECRET 是否与软件一致")
    kg = os.path.join(HERE, "发码工具.py")
    sec_k = sec_a = None
    if os.path.isfile(kg):
        t = open(kg, encoding="utf-8", errors="replace").read()
        m = re.search(r'SECRET\s*=\s*"([^"]*)"', t)
        sec_k = m.group(1) if m else None
        say("[OK]   发码工具 SECRET 已读取" if sec_k else "[FAIL] 发码工具里没有 SECRET")
    if os.path.isfile(act):
        t = open(act, encoding="utf-8", errors="replace").read()
        m = re.search(r'SECRET\s*=\s*"([^"]*)"', t)
        sec_a = m.group(1) if m else None
        say("[OK]   软件 SECRET 已读取" if sec_a else "[FAIL] activation.py 里没有 SECRET")
    if sec_k and sec_a:
        if sec_k == sec_a:
            say("[OK]   两侧 SECRET 一致，发出的码软件能识别")
        else:
            say("[FAIL] SECRET 不一致。发出的码会提示激活码无效。请把两处改成同一字符串。")
    say("")

    say("四、试发一枚并按软件逻辑验签")
    try:
        sys.path.insert(0, HERE)
        import importlib.machinery
        kgmod = importlib.machinery.SourceFileLoader(
            "kg", os.path.join(HERE, "发码工具.py")
        ).load_module()
        code = kgmod.make_code()
        say("[OK]   生成: " + code)
        # local verify copy
        parts = code.split("-")
        body = "-".join(parts[:3])
        sig = kgmod._sign(body)[:4]
        if parts[3] == sig:
            say("[OK]   签名自检通过")
        else:
            say("[FAIL] 签名自检失败")
        if os.path.isfile(act):
            sys.path.insert(0, os.path.dirname(act))
            # do not import db-heavy activation if possible; exec verify only
            text = open(act, encoding="utf-8", errors="replace").read()
            ns = {}
            # activation imports db only in some functions; module import of activation is safe
            try:
                import activation as actmod
                ok, msg = actmod.verify_code(code)
                if ok:
                    say("[OK]   软件端 verify_code 通过: " + msg)
                else:
                    say("[FAIL] 软件端拒绝该码: " + msg)
            except Exception as e:
                say("[WARN] 未能导入 activation.py: " + str(e))
    except Exception:
        say("[FAIL] 试发失败")
        say(traceback.format_exc())
    say("")
    text = "\n".join(LINES)
    say("五、结论")
    say("自检通过。" if "[FAIL]" not in text else "自检未通过，请处理上面的 [FAIL]。")
    say("=" * 56)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        say(traceback.format_exc())
    open(REPORT, "w", encoding="utf-8").write("\n".join(LINES) + "\n")
    say("报告已保存: " + REPORT)
    try:
        input("\n按回车关闭...")
    except Exception:
        pass
