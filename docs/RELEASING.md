# 发布流程（RELEASING）

给维护者看的清单：第一次把项目推上 GitHub、以及以后每次发新版，照着走一遍就行。

---

## 一、版本号规则

遵循[语义化版本](https://semver.org/lang/zh-CN/)：`主版本.次版本.修订号`

- **修订号 +1**：修 Bug、改文档、换配色这类不影响用法的改动；
- **次版本 +1**：新增功能（比如多一种声音来源）；
- **主版本 +1**：有不兼容的改动（比如设置文件格式变了、旧配置读不出来）。

版本号**只在 `main.py` 顶部的 `__version__` 改一处**，然后同步更新
`README.md` 顶部的 version 徽章和 `CHANGELOG.md`。
发布时打的 git 标签统一用 `v` 开头，例如 `v1.0.0`。

---

## 二、第一次上 GitHub（本仓库已完成，留作记录）

> 本项目已经初始化好仓库并推送到 **https://github.com/hcb9291/KeyPress**，
> 下面这些步骤换台机器、或者要重建仓库时照着做就行。

### 1. 仓库地址出现在哪些地方

以后如果改了用户名或仓库名（比如把仓库改名成 `KeyPresser`），下面几处要一起改，
否则徽章和下载链接会失效：

- `README.md` / `README.en.md`：CI 徽章、Releases 下载链接（各一处，英文版还有底部的链接）；
- `CHANGELOG.md`：底部的两个链接；
- `.github/ISSUE_TEMPLATE/config.yml`：常见问题链接。

### 2. 确认提交身份

提交记录里的作者名和邮箱是**公开**的，先确认它是你愿意公开的那一个：

```bat
git config --global user.name  "你的名字"
git config --global user.email "你的名字@users.noreply.github.com"
```

不想暴露真实邮箱的话，用 GitHub 提供的 `xxx@users.noreply.github.com` 即可
（在 GitHub 的 Settings → Emails 里能看到属于你自己的那个地址）。

### 3. 初始化仓库并推送

```bat
cd KeyPresser
git init -b main
git add .
git status
```

**重点看 `git status` 的输出**：里面应该只有程序本体、素材和文档，
不应该出现 `.private\`、`settings.json`、`__pycache__\`、`dist\` 之类的条目。

```bat
git commit -m "chore: 初始提交，KeyPresser 1.0.0"
git remote add origin https://github.com/hcb9291/KeyPress.git
git push -u origin main
```

### 4. 仓库设置建议

- **Description**：
  `Windows 上按间隔自动重复按键的小工具，纯 Python 标准库，带全局热键 / 声音提示 / 主题`
- **Topics**：`windows`、`python`、`tkinter`、`automation`、`hotkey`、
  `keyboard`、`autoclicker`、`utility`
- Settings → **Security** → 打开 **Private vulnerability reporting**
  （配合 `SECURITY.md`）；
- Settings → Actions → General：保持默认（允许运行工作流）即可。

---

## 三、每次发新版

### 1. 发布前检查清单

- [ ] `main.py` 里的 `__version__` 已改成新版本号；
- [ ] `CHANGELOG.md` 已把 `[未发布]` 的内容整理到新版本标题下，并补上日期；
- [ ] `README.md` 顶部的 version 徽章已同步；
- [ ] `python tools\selfcheck.py` 全部通过；
- [ ] `git status` 里没有任何不想公开的文件（尤其看一眼 `.private\`）；
- [ ] 主要功能手动过一遍：加按键、`F8` / `F9`、试听声音、换主题，
      再选一个指定程序试试范围限制；
- [ ] 如果改了图标或提示音，重新跑一遍 `python tools\make_assets.py` 确认能正常生成。

### 2. 打标签并推送（推荐：CI 自动打包并建 Release）

```bat
git add -A
git commit -m "chore: 发布 v1.0.0"
git push
git tag -a v1.0.0 -m "KeyPresser v1.0.0"
git push origin v1.0.0
```

推上标签之后，`.github/workflows/release.yml` 会自动：

1. 在 Windows 环境里跑一遍自检；
2. 用 PyInstaller 打包出单文件 `KeyPresser.exe`（做法与 `build.bat` 一致，
   包括把 Tcl/Tk 一起打进去，避免 exe 起来后界面出不来）；
3. 把 exe 传到 GitHub 的 Release 上，并按提交记录自动生成发布说明。

到仓库的 **Actions** 页面能看到进度，**Releases** 页面能看到结果。

### 3. 备用方案：本地打包后手动上传

CI 暂时用不了时，可以本地打包：

```bat
build.bat
```

产物是 `dist\KeyPresser.exe`。然后到 GitHub 的 Releases 页面
「Draft a new release」→ 选择已有标签 `v1.0.0` → 填标题和说明 →
把 `KeyPresser.exe` 拖进附件区 → Publish。

### 4. 发布后

- [ ] 从 Release 页面**实际下载一次 exe**，换个目录双击跑起来，
      确认界面、热键、声音都正常，窗口标题上的版本号也对；
- [ ] 看一下自动生成的发布说明，太啰嗦就精简一下；
- [ ] 如果这次修了安全问题，确认 CHANGELOG 里有对应条目。

---

## 四、提交信息怎么写

不强制，但推荐用 [约定式提交](https://www.conventionalcommits.org/zh-hans/)：

| 前缀 | 用在什么时候 |
| --- | --- |
| `feat:` | 新增功能 |
| `fix:` | 修 Bug |
| `docs:` | 只改文档 |
| `refactor:` | 重构，行为不变 |
| `chore:` | 杂项，比如发版、改配置 |

例子：`fix: 热键被其它程序占用时给出提示`。

---

## 五、常见问题

**标签打错了、推送了还没发布，怎么改？**

```bat
git tag -d v1.0.0                 :: 删本地标签
git push origin :refs/tags/v1.0.0 :: 删远端标签
```

然后重新打标签、重新推送即可。如果 Release 已经建好了，
先在 Releases 页面删掉那个 Release，再删标签。

**CI 打包出来的 exe 打不开 / 界面不显示？**

先看 `build.bat` 里的 Tcl/Tk 处理：打包时必须把 Python 安装目录下的 `tcl`
整个塞进包里（`--add-data "<Python目录>\tcl;tcl"`），而 `main.py` 启动时也要
清掉 `TCL_LIBRARY` / `TK_LIBRARY` 这两个环境变量。这两处缺一不可。

**Release 附件多大合适？**

单文件 exe 大概 15 MB 上下，正常。**不要把 exe 提交进仓库**
（仓库只放源码，exe 走 Release 附件），`.gitignore` 里已经挡掉了 `dist/`。
