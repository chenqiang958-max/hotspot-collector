# -*- coding: utf-8 -*-
"""
======================================================================
        制作干净分享版（你要把软件发给别人时用这个）
======================================================================

双击“制作分享版.bat”后，它会在旁边生成一个
“hotspot_分享版”文件夹，里面是【不含你任何数据、账号、日志、激活状态】
的干净软件。你把这个“hotspot_分享版”文件夹压缩后发给别人即可。

它会自动排除：
· data 文件夹（你的全部热点数据、登录cookie、开机密码、激活状态都在这里）
· 软件日志.txt（你的操作痕迹）
· 各种缓存文件

对方拿到后第一次打开，会从“输入激活码”开始，全新起步，跟你的数据毫无关系。
"""
import os
import shutil
import sys

# 要复制的软件文件夹（本脚本假设放在软件hotspot文件夹旁边或里面）
def find_software_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    # 情况1：本脚本就在hotspot文件夹里
    if os.path.exists(os.path.join(here, "webapp.py")):
        return here
    # 情况2：本脚本在hotspot旁边，hotspot是子文件夹
    sub = os.path.join(here, "hotspot")
    if os.path.exists(os.path.join(sub, "webapp.py")):
        return sub
    return None


# 绝不复制进分享版的东西（你的隐私数据）
EXCLUDE_NAMES = {
    "data",              # 数据库、cookie、密码、激活状态全在这
    "软件日志.txt",
    "__pycache__",
    ".secret_key",
}
EXCLUDE_SUFFIX = (".db", ".pyc", ".log")


def should_skip(name):
    if name in EXCLUDE_NAMES:
        return True
    for suf in EXCLUDE_SUFFIX:
        if name.endswith(suf):
            return True
    return False


def copy_clean(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if should_skip(name):
            print(f"  跳过（不放进分享版）：{name}")
            continue
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            copy_clean(s, d)
        else:
            shutil.copy2(s, d)


def main():
    print("=" * 50)
    print("        制作干净分享版")
    print("=" * 50)
    software = find_software_dir()
    if not software:
        print("没找到软件文件（webapp.py）。请把这个脚本放在 hotspot 文件夹里，或它旁边。")
        input("按回车关闭...")
        return

    out_parent = os.path.dirname(software)
    out_dir = os.path.join(out_parent, "hotspot_分享版")

    if os.path.exists(out_dir):
        print(f"“hotspot_分享版”已存在，将先删除旧的再重建。")
        try:
            shutil.rmtree(out_dir)
        except Exception as e:
            print(f"删除旧文件夹失败：{e}")
            input("按回车关闭...")
            return

    print(f"\n正在从 {software}")
    print(f"制作干净分享版到 {out_dir}\n")
    copy_clean(software, out_dir)

    print("\n" + "=" * 50)
    print("✅ 完成！")
    print(f"干净的分享版在：{out_dir}")
    print("把这个“hotspot_分享版”文件夹压缩成zip，就能发给别人了。")
    print("里面不含你的任何数据、账号、密码、日志、激活状态。")
    print("=" * 50)
    input("\n按回车关闭...")


if __name__ == "__main__":
    main()
