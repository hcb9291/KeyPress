# 更新日志

本文件记录 KeyPresser 每个版本的变化。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

## [1.0.1] - 2026-10-01

文档与资源更新，程序功能与 1.0.0 相同。

### 新增

- 完整英文版说明 `README.en.md`，中英文两份 README 之间互相加了切换链接；
- `assets/screenshot.png`：界面截图，用在 README 里；
- `assets/social_preview.png`：1280×640 的社交分享预览图（别人分享仓库链接时显示）；
- `tools/selfcheck.py` 支持用 `--patterns` 参数指定额外的私有关键词文件。

### 修复

- 自检脚本在非 UTF-8 控制台（比如 GitHub Actions 的 Windows 运行器）下打印中文会直接崩溃；
  现在脚本内部强制使用 UTF-8 输出，两个工作流也统一设置了 `PYTHONUTF8=1`。

### 变更

- 仓库地址由 `KeyPress` 更名为 `KeyPresser`（GitHub 会保留旧地址跳转）。

## [1.0.0] - 2026-10-01

第一个公开版本。

### 新增

- **按键序列**：列表里放一个键就是重复这一个键，放多个键就按顺序循环执行；
  每一步可以单独设置间隔，支持添加 / 删除 / 上移 / 下移，双击某一行改间隔。
- **全局热键**：默认 `F8` 开始、`F9` 停止，支持 `Ctrl+Alt+K` 这类组合键；
  界面按钮和热键都可以控制。
- **声音提示**，三种来源任选：
  - 内置提示音三套（清脆 / 柔和 / 低沉），开始音上行、停止音下行；
  - 自定义语音：导入 `.wav`，或直接用麦克风录制；
  - 系统语音：调用 Windows 自带中文语音朗读「开始按键 / 停止按键」。
- **作用范围**：全局，或只在指定程序处于前台时生效（切走自动暂停）。
- **主题系统**：4 套内置主题（樱粉·亮 / 樱粉·暗 / 薄荷·亮 / 星夜·暗），
  界面右上角一键切换并记住选择；主题数据放在 `themes.json`，可以自行增改。
- **原创美术资源**：图标、吉祥物（猫耳键帽）、顶部横幅、三套提示音
  全部由 `tools/make_assets.py` 用代码生成，可自由使用。
- 单文件打包脚本 `build.bat`（PyInstaller，目标机器免 Python 环境）。
- 项目自检脚本 `tools/selfcheck.py`，以及 GitHub Actions 持续集成。
- 文档：`README.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、
  `SECURITY.md`、`docs/RELEASING.md`。

### 说明

- 设置与录制的语音存放在 `%APPDATA%\KeyPresser\`，程序目录不产生任何运行期文件。
- 仅支持 Windows 10 / 11。

[未发布]: https://github.com/hcb9291/KeyPresser/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/hcb9291/KeyPresser/releases/tag/v1.0.1
[1.0.0]: https://github.com/hcb9291/KeyPresser/releases/tag/v1.0.0
