# -*- coding: utf-8 -*-
"""
激活码模块（软件端）：
- 生成本机硬件指纹（用于把激活码绑到一台电脑）
- 验证用户输入的激活码是否有效
- 记录激活状态到数据库

重要：这里只有【验证】逻辑，没有【造码】逻辑。
造码用的密钥只放在你自己的“发码工具.py”里，绝不放进分享出去的软件。
别人拿到这个软件也造不出新激活码。

激活码格式： XXXX-XXXX-XXXX-XXXX （4段，去掉了容易看错的字符）
最后一段是校验签名，前面几段是编号+随机。
"""
import hashlib
import hmac
import uuid
import re

# ===== 对暗号用的“钥匙” =====
# 这个值必须和你的“发码工具.py”里的 SECRET 完全一样，否则你发的码软件认不出来。
# 你可以（也建议）把它改成只有你知道的一长串字符，改了之后发码工具里也要改成一样的。
# 改这里 → 老激活码会全部失效，需要用新密钥重新发码。
SECRET = "CHANGE-ME-hotspot-2026-请改成你自己的一长串随机字符-abcdEFGH1234"

# 激活码里允许的字符（去掉了 0/O、1/I/L 这种容易看错的）
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _mac_is_reliable(node):
    """
    判断 uuid.getnode() 拿到的是不是真实网卡MAC。
    Python官方说明：读不到真MAC时会返回一个“设了多播位”的随机数，
    这种值每次可能都不同，绝不能拿来当稳定指纹。多播位=最低字节的最低位为1。
    """
    if not node:
        return False
    # 48位MAC的最高字节里，bit0(多播位)为1 → 是随机/多播地址，不可靠
    # node 的最高字节 = (node >> 40) & 0xFF，其 bit0 即多播位
    if (node >> 40) & 0x01:
        return False
    return True


def _compute_fp_from_seed(seed_str):
    """把一段种子串算成 XXXX-XXXX-XXXX 格式的指纹。"""
    h = hashlib.sha256(f"hotspot-machine-{seed_str}".encode("utf-8")).hexdigest().upper()
    short = h[:12]
    return f"{short[:4]}-{short[4:8]}-{short[8:12]}"


def get_machine_fingerprint():
    """
    本机指纹（稳定版）。
    关键改动：指纹在【首次生成后固化到数据库】，之后永久读库里那一份，
    不再每次实时读网卡MAC——因为 uuid.getnode() 在读不到真MAC时会返回随机值，
    导致过一段时间指纹变化、激活“无故失效”。

    首次生成逻辑：
    - 能读到可靠的真实MAC → 用MAC派生指纹（保留硬件关联，便于防复制）。
    - 读不到可靠MAC → 用一次性随机数派生（保证唯一），并同样固化存库。
    无论哪种，都会把结果写进数据库 machine_fp，以后不再变。
    """
    try:
        import db
        saved = db.get_setting("machine_fp")
        if saved:
            return saved  # 已固化，直接用，永不再变
    except Exception:
        # 数据库还没就绪（极早期调用）时，退回临时计算，不落库
        node = uuid.getnode()
        if _mac_is_reliable(node):
            return _compute_fp_from_seed(str(node))
        return _compute_fp_from_seed(uuid.uuid4().hex)

    # 库里还没有 → 首次生成并固化
    node = uuid.getnode()
    if _mac_is_reliable(node):
        seed = str(node)
    else:
        # 读不到可靠MAC：用随机种子，保证这台机器有个稳定唯一指纹
        seed = uuid.uuid4().hex
    fp = _compute_fp_from_seed(seed)
    try:
        db.set_setting("machine_fp", fp)
    except Exception:
        pass
    return fp


def _sign(payload):
    """用密钥给一段内容算签名，取前若干位转成字母数字。"""
    mac = hmac.new(SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    # 把签名字节映射到 _ALPHABET 上，取8位
    out = []
    for b in mac[:8]:
        out.append(_ALPHABET[b % len(_ALPHABET)])
    return "".join(out)


def _normalize(code):
    """把用户输入的码规整：去空格、转大写、去连字符外的杂字符。"""
    c = (code or "").strip().upper().replace(" ", "")
    # 只保留字母数字和连字符
    c = re.sub(r"[^0-9A-Z-]", "", c)
    return c


def verify_code(code):
    """
    验证一个激活码本身是否是“你发出来的真码”（签名对不对）。
    返回 (是否有效, 提示信息)。
    这一步不检查是不是本机、是否已用过——那是数据库层的事。
    """
    c = _normalize(code)
    parts = c.split("-")
    # 期望格式：3段随机/编号 + 1段签名 = 4段，每段4位
    if len(parts) != 4 or any(len(p) != 4 for p in parts):
        return False, "激活码格式不对（应该是四段，像 A2B3-C4D5-E6F7-G8H9）"
    body = "-".join(parts[:3])
    sig_given = parts[3]
    sig_calc = _sign(body)[:4]
    if sig_given != sig_calc:
        return False, "激活码无效（不是有效的激活码，请找发放者确认）"
    return True, "激活码有效"


def is_activated():
    """
    本机是否已激活。不只看标记，还要核对激活时记录的机器指纹==当前机器指纹。
    这样即使有人把已激活的整个文件夹复制到别的电脑，指纹对不上，也会要求重新激活。
    """
    import db
    if db.get_setting("activated") != "yes":
        return False
    bound_fp = db.get_setting("activated_machine")
    if not bound_fp:
        return False
    return bound_fp == get_machine_fingerprint()


def activate_this_machine(code):
    """
    用激活码激活本机。做三重检查：
    1. 码本身有效（签名对）
    2. 这个码没被别的电脑用过（防转发：一个码只能激活一台电脑）
    3. 激活成功后把 码+本机指纹 记下来
    返回 (是否成功, 提示信息)。
    """
    import db
    ok, msg = verify_code(code)
    if not ok:
        return False, msg

    c = _normalize(code)
    fp = get_machine_fingerprint()

    # 这个码之前激活过吗？
    used_fp = db.get_code_bound_machine(c)
    if used_fp:
        if used_fp == fp:
            # 就是本机，重复激活，直接放行
            db.set_setting("activated", "yes")
            db.set_setting("activated_machine", fp)
            return True, "本机已激活"
        # 指纹对不上，但可能是“本机因为老版本指纹不稳定而变了指纹”的情况。
        # 判断依据：这个码正是本机当初激活记录里存的那个码 → 认定为本机，更新绑定到新指纹。
        prev_code_here = db.get_setting("activation_code")
        if prev_code_here and _normalize(prev_code_here) == c:
            db.rebind_code_to_machine(c, fp)
            db.set_setting("activated", "yes")
            db.set_setting("activated_machine", fp)
            return True, "本机激活已恢复（指纹已固定，以后不会再掉激活）"
        return False, "这个激活码已经在另一台电脑上用过了（一个码只能激活一台电脑）"

    # 没用过 → 绑定到本机
    db.bind_code_to_machine(c, fp)
    db.set_setting("activated", "yes")
    db.set_setting("activated_machine", fp)
    db.set_setting("activation_code", c)
    return True, "激活成功"


def verify_reset_code(code):
    """
    忘记密码时，校验用户输入的激活码能不能用来重置这台电脑的密码。
    要求：
    1. 码本身有效（签名对）
    2. 而且必须是【当初激活这台电脑用的那个码】（不是随便一个有效码都行）
    返回 (是否通过, 提示)。
    """
    ok, msg = verify_code(code)
    if not ok:
        return False, msg
    import db
    c = _normalize(code)
    used_for_this = db.get_setting("activation_code")
    if used_for_this and _normalize(used_for_this) == c:
        return True, "验证通过"
    # 兜底：如果没存激活码记录，但这个码绑定的机器就是本机，也允许
    bound = db.get_code_bound_machine(c)
    if bound and bound == get_machine_fingerprint():
        return True, "验证通过"
    return False, "这个激活码不是本机激活用的那个，无法重置密码"
