# -*- coding: utf-8 -*-
"""KeyPresser 项目自检。

提交前、CI 里跑一遍，确认三件事：

1. 该有的文件都在（程序、素材、文档、CI 配置）；
2. 主题数据合法，而且 themes.json 与 main.py 里的 BUILTIN_THEMES 一致；
3. 没有把私人内容（开发对话记录、本机路径、个人邮箱等）混进仓库。

用法：

    python tools/selfcheck.py

只依赖标准库。有硬性问题时以非 0 退出码结束；占位符之类的只提醒，不算失败。
"""

import ast
import json
import os
import re
import sys

# 输出里有中文：Windows 的默认控制台编码可能是 cp936 / cp1252，
# 那样 print 会直接抛 UnicodeEncodeError 把脚本打断（CI 上就踩过这个坑）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = os.path.abspath(__file__)

# 开源前需要替换成自己的 GitHub 用户名
PLACEHOLDER = "YOUR_GITHUB_NAME"

REQUIRED_FILES = (
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "main.py",
    "themes.json",
    "tts_synth.ps1",
    "README.md",
    "README.en.md",
    "CHANGELOG.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "build.bat",
    "run.bat",
    "docs/RELEASING.md",
    "tools/make_assets.py",
    "assets/icon.ico",
    "assets/icon.png",
    "assets/icon_512.png",
    "assets/mascot.png",
    "assets/header.png",
    "assets/screenshot.png",
    "assets/social_preview.png",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
)

PNG_FILES = ("assets/icon.png", "assets/icon_512.png",
             "assets/mascot.png", "assets/header.png", "assets/screenshot.png",
             "assets/social_preview.png")
WAV_FILES = tuple("sounds/%s_%s.wav" % (timbre, kind)
                  for timbre in ("chime", "soft", "deep")
                  for kind in ("start", "stop"))

# 扫「隐私」时跳过的目录（这些不是项目内容）
SKIP_DIRS = {".git", ".private", ".venv", "venv", "env", "build", "dist",
             "__pycache__", ".idea", ".vscode", "node_modules", "tcl"}

TEXT_EXTS = {".py", ".md", ".json", ".ps1", ".bat", ".cmd", ".txt",
             ".yml", ".yaml", ".toml", ".ini", ".cfg"}
TEXT_NAMES = {".gitignore", ".gitattributes", ".editorconfig"}

# 不该出现在公开仓库里的通用东西。每项是 (正则, 说明)，大小写不敏感。
# 想加自己的关键词（邮箱、账号、本机目录名等），写到 .private\private-patterns.txt，
# 那个文件不会被提交，见下面的 local_patterns()。
PRIVATE_PATTERNS = (
    (r"对话记录", "开发对话记录（私人内容）"),
    (r"chatgpt", "提到了 AI 对话工具"),
    (r"[a-z]:\\users\\", "本机绝对路径 C:\\Users\\..."),
)

LOCAL_PATTERNS_FILE = os.path.join(".private", "private-patterns.txt")

failures = []
warnings = []


def fail(msg):
    failures.append(msg)


def warn(msg):
    warnings.append(msg)


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def iter_text_files():
    """遍历项目里的文本文件（跳过 .git / .private / 构建产物）。"""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == SELF:  # 本文件自己也带着这些关键词
                continue
            if os.path.splitext(name)[1].lower() in TEXT_EXTS or name in TEXT_NAMES:
                yield path


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def local_patterns():
    """本地私有关键词：`.private/private-patterns.txt`，一行一个正则，# 开头是注释。

    这个文件不进仓库，方便各自加上自己的邮箱、账号、本机目录名等。
    """
    path = os.path.join(ROOT, LOCAL_PATTERNS_FILE)
    if not os.path.exists(path):
        return []
    found = []
    for line in read(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            re.compile(line)
        except re.error as exc:
            warn("%s 里的正则写错了，已跳过：%s（%s）" % (LOCAL_PATTERNS_FILE, line, exc))
            continue
        found.append((line, "本地私有关键词"))
    return found


def check_required_files():
    for name in REQUIRED_FILES:
        if not os.path.exists(os.path.join(ROOT, name)):
            fail("缺少文件：%s" % name)


def check_asset_headers():
    """素材必须是真文件：有内容、文件头正确（防止被当文本转换坏了）。"""
    checks = [(name, b"\x89PNG") for name in PNG_FILES]
    checks.append(("assets/icon.ico", b"\x00\x00\x01\x00"))
    checks += [(name, b"RIFF") for name in WAV_FILES]

    for name, magic in checks:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue  # 上面已经报过「缺少文件」
        if os.path.getsize(path) == 0:
            fail("素材是空文件：%s" % name)
            continue
        with open(path, "rb") as fh:
            head = fh.read(len(magic))
        if head != magic:
            fail("素材文件头不对（可能损坏或换了格式）：%s" % name)


def main_constants():
    """用 AST 读出 main.py 里的常量，不执行 main.py（避免弹出窗口）。"""
    tree = ast.parse(read(os.path.join(ROOT, "main.py")))
    wanted = {"__version__", "THEME_KEYS", "BUILTIN_THEMES", "DEFAULT_THEME_ID"}
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    try:
                        found[target.id] = ast.literal_eval(node.value)
                    except ValueError:
                        pass
    return found


def check_version(constants):
    version = constants.get("__version__")
    if not version:
        fail("main.py 里找不到 __version__")
        return
    if not re.match(r"^\d+\.\d+\.\d+$", str(version)):
        fail("版本号格式不对（应该是 主.次.修订）：%s" % version)
    for name in ("README.md", "README.en.md"):
        if "version-%s-" % version not in read(os.path.join(ROOT, name)):
            fail("%s 顶部的 version 徽章没有同步成 %s" % (name, version))
    if "## [%s]" % version not in read(os.path.join(ROOT, "CHANGELOG.md")):
        fail("CHANGELOG.md 里没有 %s 的条目" % version)


def check_themes(constants):
    theme_keys = constants.get("THEME_KEYS")
    builtin = constants.get("BUILTIN_THEMES")
    default_id = constants.get("DEFAULT_THEME_ID")
    if not theme_keys or not builtin:
        fail("main.py 里读不到 THEME_KEYS / BUILTIN_THEMES")
        return

    with open(os.path.join(ROOT, "themes.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    themes = data["themes"] if isinstance(data, dict) else data
    if not themes:
        fail("themes.json 里一个主题都没有")
        return

    seen = set()
    for theme in themes:
        name = theme.get("name") or theme.get("id") or "?"
        extra_fields = sorted(set(theme) - {"id", "name", "colors"})
        if extra_fields:
            warn("主题「%s」有多余的字段：%s" % (name, extra_fields))
        if not theme.get("id") or not theme.get("name"):
            fail("主题缺少 id 或 name：%r" % theme)
            continue
        if theme["id"] in seen:
            fail("主题 id 重复：%s" % theme["id"])
        seen.add(theme["id"])

        colors = theme.get("colors") or {}
        missing = [k for k in theme_keys if k not in colors]
        extra = [k for k in colors if k not in theme_keys]
        if missing:
            fail("主题「%s」缺少颜色键：%s" % (name, missing))
        if extra:
            fail("主题「%s」有多余的颜色键：%s" % (name, extra))
        for key, value in colors.items():
            if not re.match(r"^#[0-9A-Fa-f]{6}$", str(value)):
                fail("主题「%s」的 %s 不是 #RRGGBB 颜色：%r" % (name, key, value))

    if default_id and default_id not in seen:
        fail("DEFAULT_THEME_ID（%s）在主题列表里找不到" % default_id)

    if len(builtin) != len(themes):
        fail("BUILTIN_THEMES 有 %d 套，themes.json 有 %d 套，两边对不上"
             % (len(builtin), len(themes)))
    for a, b in zip(builtin, themes):
        if a.get("id") != b.get("id") or a.get("colors") != b.get("colors"):
            fail("BUILTIN_THEMES 与 themes.json 不一致：%s / %s"
                 % (a.get("id"), b.get("id")))


def check_privacy():
    rules = tuple(PRIVATE_PATTERNS) + tuple(local_patterns())
    patterns = [(re.compile(p, re.IGNORECASE), why) for p, why in rules]
    for path in iter_text_files():
        text = read(path)
        for pattern, why in patterns:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                fail("发现不该公开的内容（%s）：%s 第 %d 行"
                     % (why, rel(path), line))


def check_placeholders():
    hits = [rel(p) for p in iter_text_files() if PLACEHOLDER in read(p)]
    if hits:
        warn("还有占位符 %s 没替换，出现在：%s"
             % (PLACEHOLDER, "、".join(sorted(hits))))


def main():
    check_required_files()
    check_asset_headers()

    try:
        constants = main_constants()
    except SyntaxError as exc:
        fail("main.py 语法有问题：%s" % exc)
        constants = {}
    if constants:
        check_version(constants)
        check_themes(constants)

    check_privacy()
    check_placeholders()

    print("KeyPresser 自检：必需文件 %d 个、主题 %d 套、提示音 %d 个"
          % (len(REQUIRED_FILES), len(constants.get("BUILTIN_THEMES") or []),
             len(WAV_FILES)))
    for msg in warnings:
        print("  [提醒] %s" % msg)
    for msg in failures:
        print("  [错误] %s" % msg)

    if failures:
        print("\n自检不通过：%d 个问题。" % len(failures))
        return 1
    print("\n自检通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
