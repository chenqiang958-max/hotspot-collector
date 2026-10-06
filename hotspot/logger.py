# -*- coding: utf-8 -*-
"""
日志模块：把软件运行中的所有关键操作和错误记录到文件。
用GBK编码写（Windows记事本默认GBK，打开不乱码不空白）。
"""
import os
import traceback
from datetime import datetime

# 日志固定写在这个文件旁边
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "软件日志.txt")
MAX_LOG_SIZE = 2 * 1024 * 1024


def _write(level, msg):
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > MAX_LOG_SIZE:
            open(LOG_PATH, "w", encoding="gbk", errors="replace").close()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {msg}\n"
        # 用GBK编码写（Windows记事本默认能读），无法编码的字符替换掉
        with open(LOG_PATH, "a", encoding="gbk", errors="replace") as f:
            f.write(line)
        # 同时打印到命令行，双保险
        try:
            print(f"[日志] {line}", end="")
        except Exception:
            pass
    except Exception as e:
        # 记日志本身绝不能让软件崩，但打印出来让你知道日志出问题了
        try:
            print(f"[日志写入失败] {e}")
        except Exception:
            pass


def info(msg):
    _write("信息", msg)


def warn(msg):
    _write("警告", msg)


def error(msg, exc=None):
    _write("错误", msg)
    if exc is not None:
        try:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            _write("错误详情", "\n" + tb)
        except Exception:
            _write("错误详情", f"{type(exc).__name__}: {exc}")


def action(platform, what, result):
    _write("操作", f"平台={platform} 操作={what} 结果={result}")


def separator(title=""):
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="gbk", errors="replace") as f:
            f.write(f"\n{'='*50}\n[{ts}] === {title} ===\n{'='*50}\n")
    except Exception:
        pass


def read_recent(lines=100):
    """读最近的日志内容（给界面显示用）"""
    try:
        if not os.path.exists(LOG_PATH):
            return "（还没有日志）"
        with open(LOG_PATH, "r", encoding="gbk", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:]) or "（日志为空）"
    except Exception as e:
        return f"（读日志出错: {e}）"


if __name__ == "__main__":
    separator("日志测试")
    info("测试信息")
    action("test", "测试", "成功")
    print("日志位置:", LOG_PATH)
    print(read_recent())
