# AccountTools —— 多平台 AI 软件账号工具集

统一管理各 AI 编程软件（WorkBuddy / Trae CN / Qoder / Cursor / 更多…）的
**账号快照切换、每日签到领取、成长任务与设备重置**，提供 **Web 端** 与
**桌面端（macOS DMG / Windows 安装包）** 两种形态，同一后端、同一页面。

```
┌────────────────────────── AccountTools ──────────────────────────┐
│  形态一 Web 端    python3 -m app / ./run.sh      → 浏览器控制台    │
│  形态二 桌面端    Electron 壳 + 打包后的同一后端   → DMG / exe     │
│                              │                                    │
│                    app/  (插件化框架,两种形态共用)                  │
│   ┌──────────────────────────┼──────────────────────────────┐     │
│   │ app/core    配置·日志·后台任务·签到编排·FastAPI 工厂       │     │
│   │ app/agents  适配器插件:workbuddy·trae·qoder·cursor…       │     │
│   │ app/static  前端单页(动态渲染平台卡片与特性按钮)             │     │
│   └──────────────────────────┼──────────────────────────────┘     │
│                    单一逻辑源:各平台目录核心脚本                     │
│   Workbuddy/wb-switch.sh·wb_checkin.py·wb_growth.py·wb_import.py   │
│   Trae/trae_switch.py·trae_reset.py·trae-autocheckin/  等          │
└────────────────────────────────────────────────────────────────────┘
```

## 快速开始（Web 端）

```bash
./run.sh                  # 首次自动创建 .venv 并安装依赖，然后启动
# 或手动：
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app --port 8800
```

启动后访问 <http://127.0.0.1:8800>（仅监听本机回环，不对外暴露）。
数据目录：开发态 `app/data/`（config.json + logs.jsonl），
桌面端 `~/.accounttools/`。旧 SignCenter 的数据在首次启动时自动迁移。

## 桌面端

```bash
# 开发态直接跑 Electron 壳（复用 .venv 里的后端，无需打包）：
cd desktop && npm install && ACCOUNTTOOLS_DEV=1 npm start
```

正式打包走 GitHub Actions（**仅手动触发**）：仓库 → Actions →
「桌面端打包」→ Run workflow（可填版本号，留空用 package.json 里的）。

- **macOS**：`macos-latest`（Apple Silicon）构建 `AccountTools-x.y.z-mac-arm64.dmg`
- **Windows**：`windows-latest` 构建 `AccountTools-x.y.z-win-x64-setup.exe`（NSIS 安装器）
- 流水线：PyInstaller 把 `app/` + 各平台核心脚本打成单文件后端 →
  electron-builder 把后端作为 extraResources 嵌入 → 产物上传为 artifact
- **产物未签名**：macOS 首次打开需右键 →「打开」；Windows SmartScreen 选「仍要运行」

本地打包后端（可选验证）：`pip install pyinstaller && pyinstaller scripts/backend.spec --noconfirm`

## 添加一个新的软件 agent（插件化扩展）

框架目标：**新增一个 agent = 新增一个文件**，Web/桌面、卡片 UI、配置开关、
签到编排、自动调度全部自动出现，无需改 core 或前端结构。

1. 核心脚本/模块放进仓库根的 `<AgentName>/` 目录（保持单一逻辑源）；
2. 复制 `app/agents/_template.py` 为 `app/agents/<agent_id>.py`，实现
   `state / save / switch / delete` 四个账号快照方法（动作统一返回
   `{"ok": bool, "output": str}`），加 `@register` 装饰器即可注册；
3. 可选能力：
   - `claim()` 原生签到领取（WorkBuddy 的 wbipc 代签、Trae 的扩展领取即此）；
   - `direct_checkin(name)` 处理 `token:` 前缀的 API 直连账号；
   - `features()` 声明扩展能力，三种通用 UI 开箱即用：
     - `kind="job"`：后台长任务 + 进度流（成长任务、设备重置）；
     - `kind="action"`：即时动作（重启 Cursor、本机退出登录）；
     - `kind="import"`：凭证 JSON 导入（WorkBuddy token 账号池）；
   - 富交互界面可设 `renderer`（当前内置 `growth-tasks`，可按需在前端增加）。
4. `supported_os` 声明核心脚本支持的系统；不支持的系统上卡片自动置灰并说明原因
   （当前四款适配器的切换脚本均依赖 macOS；Windows 桌面端安装包可正常运行、
   agent 能力按此声明逐步放开）。

适配器约定详见 `app/agents/base.py` 的 docstring。

新增或修改 POST 接口时，Pydantic 请求模型必须定义在**模块级**：本文件启用了
`from __future__ import annotations`，函数内定义的模型注解无法解析，会导致请求全部 422。

## 功能一览

| 功能 | 说明 |
|---|---|
| 平台卡片 | 各 agent 一张卡片：启停开关、当前账号、快照列表、今日签到进度 |
| 添加账号 | 在桌面应用登录后点「+ 添加账号」，保存当前登录态为快照 |
| **导入 JSON** | WorkBuddy：导入外部凭证（access/refresh token），账号直接经官方 API 签到，不切换、不重启桌面应用 |
| 切换账号 | 点账号 chip：WorkBuddy 热加载秒切；Trae/Qoder/Cursor 退出应用→换凭据→重启 |
| 立即签到 | 卡片蓝色按钮：只签当前登录的这个账号（不重启应用，秒级完成） |
| 全部签到 | 快照账号依次切换签到，导入账号 API 直连，完成后自动切回原账号 |
| 全部平台签到 | 底部蓝色按钮：对所有已启用 agent 执行「全部签到」 |
| 自动签到 | 每天到设定时间（默认 05:20）自动执行；「自动补签」支持当天补跑 |
| **成长任务** | WorkBuddy：成长中心任务查看 + 勾选后台自动完成（wbipc 轻量通道 + 桌面端 CDP 通道） |
| **设备重置** | Trae：重置本机设备标识（machineid/storage.json/缓存 + 客户端 16 位设备ID注入） |
| 签到记录 | 持久化于数据目录 logs.jsonl，滚动展示最近记录 |

「签到」的原理（WorkBuddy wbipc 代领、Trae 应用内扩展领取、Qoder 登录态刷新、
自定义 checkin_command 钩子）见各平台目录 README 与 `Trae/DAILY_CHECKIN_ANALYSIS.md`。

## 目录结构

```
AccountTools/
├── app/                     # 插件化应用框架（Web/桌面共用）
│   ├── __main__.py          # 入口：python -m app（含 --exec-script 冻结子命令）
│   ├── core/                # paths·config·logs·jobs·proc·orchestrator·server
│   ├── agents/              # 适配器插件 + _template.py 模板 + registry 自动发现
│   └── static/              # 前端单页（原生 JS）
├── desktop/                 # Electron 壳（main.js·splash·electron-builder 配置·图标）
├── scripts/                 # backend.spec（PyInstaller）·gen_icon.py
├── backend_entry.py         # PyInstaller 打包入口
├── .github/workflows/build-desktop.yml   # 手动触发的桌面打包流水线
├── Workbuddy/ Trae/ Qoder/ Cursor/       # 各平台核心脚本（单一逻辑源，原样保留）
├── run.sh · requirements.txt · .env.example
└── README.md
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/overview` | 全 agent 状态聚合（卡片数据 + 今日进度 + 设置 + features 声明） |
| GET | `/api/logs?limit=100` | 最近签到/切换日志 |
| POST | `/api/agent/{aid}/toggle` | 启用/停用 `{enabled}` |
| POST | `/api/agent/{aid}/save` | 保存当前账号快照 `{name, force?}` |
| POST | `/api/agent/{aid}/switch` | 切换账号 `{name}` |
| POST | `/api/agent/{aid}/delete` | 删除快照 `{name}` |
| POST | `/api/agent/{aid}/checkin` | 平台签到 `{name}`=指定账号；`{}`=全部账号 |
| POST | `/api/checkin/all` | 全部已启用 agent 签到 |
| POST | `/api/settings` | 修改自动签到设置 |
| GET | `/api/agent/{aid}/feature/{fid}/status` | Feature 概览（角标/弹窗首屏） |
| GET | `/api/agent/{aid}/feature/{fid}/job` | job 进度流 |
| POST | `/api/agent/{aid}/feature/{fid}/run` | 启动 job / 执行 action `{payload}` |
| POST | `/api/agent/{aid}/feature/{fid}/import` | 凭证导入 `{data}` |

`aid` 取值：`workbuddy` / `trae` / `qoder` / `cursor`（随插件注册动态增长）。

## 注意事项

- **Trae / Qoder / Cursor 切换会退出并重启应用**（无热加载），签到前请保存好编辑器内容；
  WorkBuddy 支持热加载，秒级完成。
- **不要在 Trae 会话内操作 Trae 签到**：Agent 本身跑在 Trae 里时应用无法退出（签到会安全中止）。
- **WorkBuddy 签到要求应用在运行**（wbipc 通道依赖之）：未运行时会自动启动并等待最多 40 秒。
- **导入的 token 账号只用于 API 直连签到，不能切换桌面登录态**：桌面会话文件中的 token 是应用加密信封，
  无法由明文凭证合成；且同一账号双用会因 refresh_token 轮转互相失效。需在桌面端使用该账号时，
  请先在应用内手动登录一次，再点「+ 添加账号」保存为快照。
- 成长任务 CDP 通道需要 WorkBuddy 带调试端口运行（`python3 Workbuddy/desktop.py ensure`）；
  桌面端安装包未内置 playwright，CDP 类任务请在 Web 端使用（wbipc 轻量任务不受影响）。
- 自动签到调度在服务/应用运行期间生效；如需真正无人值守可用 `launchd`/任务计划定时
  `curl -X POST http://127.0.0.1:8800/api/checkin/all`。
- refresh token 有效期约 30 天，长期不用的账号建议定期签到保活——这正是本工具的用途。
- Trae 默认管理 CN 版（`TRAE_PROFILE=cn`），国际版：`TRAE_PROFILE=intl`。
- 合规提示：签到积分属各平台运营权益，自动化领取是否合规以各平台用户协议为准。
- 各平台目录下仍保留独立的单平台控制台（`Cursor/server.py` 等），可单独使用；
  统一控制台以 `app/` 为准。
