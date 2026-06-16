# MiMo Code for fnOS

把官方 [Xiaomi MiMo Code](https://github.com/XiaomiMiMo/MiMo-Code) 打包成飞牛 fnOS 应用，并提供一个面向 NAS 用户的浏览器工作台。

> 本仓库是 fnOS 应用封装层源码，不包含官方 `mimo` 二进制。二进制来自官方发布渠道，打包时放入 `app/server/mimo`，该文件被 `.gitignore` 忽略。

## 项目定位

MiMo Code 是小米推出的 AI 编程代理，官方能力包括：

- 终端内运行 AI 编程助手；
- 读取/修改项目代码；
- 执行命令、查看 Git 状态；
- 通过官方 Web UI 进行会话交互；
- 管理 Provider、模型、Agent、MCP/ACP 等能力。

本项目的目标不是重写 MiMo Code，而是把官方能力稳定接入 fnOS：

- 一键安装成飞牛应用；
- 应用中心/桌面入口可直接打开；
- 自动管理 wrapper 服务和官方 `mimo web`；
- 提供中文化的配置、状态、日志和诊断入口；
- 保留官方 Web 会话作为主聊天界面。

## 当前版本

- 应用版本：`v0.11.9`
- wrapper 端口：`5670`
- 官方 MiMo Web 端口：`5669`
- fnOS 应用名：`mimocode`
- fpk 包名示例：`mimocode.v0.11.9.fpk`

## 功能概览

`v0.11.9` 将官方会话恢复为直连官方 `mimo web`，减少 wrapper 代理兼容问题。

### 1. 工作台

工作台用于查看和管理应用状态，不承载聊天主界面：

- MiMo 服务状态；
- 官方 Web 入口；
- 当前 Provider/模型；
- CLI 状态；
- 快速进入官方会话、项目概览、模型配置、健康检查、日志诊断、配置备份和工具箱。

### 2. 官方会话

真实聊天和上下文交互交给官方 `mimo web`。

从 `v0.10.4` 开始，「官方会话」按早期 `v0.5.0` 的正确交互方式实现：

- 点击顶部「官方会话」后，主内容区直接被官方 MiMo Web 接管；
- 只放一个 100% 宽高、无边框 iframe；
- 不再额外包卡片；
- 不显示 wrapper 标题栏说明；
- 不显示右下角 fallback 弹窗；
- 最大限度保留官方 Web 的原生布局、快捷键和文件区体验。

如果应用内 iframe 在未来被官方 Web 限制，可从工作台使用「新窗口打开」进入官方 Web。

### 3. 模型与服务商

提供中文化 Provider 配置：

- MiMo 官方模型；
- OpenAI 兼容接口；
- DeepSeek 等第三方 Provider；
- 默认模型设置；
- API Key 本地保存；
- 导出配置默认脱敏。

内置官方模型列表包括：

```text
mimo/mimo-auto
xiaomi/mimo-v2-flash
xiaomi/mimo-v2-omni
xiaomi/mimo-v2-pro
xiaomi/mimo-v2.5
xiaomi/mimo-v2.5-pro
xiaomi/mimo-v2.5-pro-ultraspeed
```

推荐首次使用选择 `mimo/mimo-auto`。

### 4. 会话历史

wrapper 提供轻量会话历史入口，用于查看和管理通过 wrapper 触发的 CLI 快速测试记录。完整聊天历史仍以官方 MiMo Web 为准。

### 5. 项目概览 / 健康检查 / 安全说明

`v0.11.9` 延续工作台辅助页面，并将官方会话交回官方 Web 直连处理：

- 项目概览：扫描当前项目目录、识别常见项目标记和文件类型分布；
- 免费模型库：内置常见免费/限免/试用模型入口，可一键填入 Provider 表单；
- 免费模型库来源说明：该功能整理常见 OpenAI 兼容平台的公开入口和模型名预设，参考 QwenPaw provider 配置结构补齐免费模型分组，没有复制 QwenPaw 或其他第三方项目运行时代码；免费/限免状态以各平台实时政策为准；
- 健康检查：检查 Wrapper、官方 Web、MiMo CLI、模型配置、项目目录和错误日志；
- 安全说明：明确官方二进制、凭据保存、命令白名单、只读文件浏览和高级功能边界。

### 6. 日志诊断

日志页将常见错误整理成中文建议，包括：

- MiMo Web 未启动；
- Provider 未配置；
- 模型无响应；
- API Key 缺失；
- CLI 调用失败；
- 端口占用或进程异常。

### 7. 高级设置 / 配置备份

高级设置用于管理 wrapper 行为：

- 默认项目目录；
- 默认模型；
- 配置导入/导出；
- 诊断包导出；
- 手动配置备份；
- 配置导入前自动创建脱敏备份；
- 开发者工具箱开关。

诊断包会自动脱敏，避免直接导出明文 Key。

### 8. 工具箱

工具箱默认隐藏，适合排查和高级用户使用：

- 项目文件浏览：只读、限制在当前项目目录；
- 性能监控：wrapper uptime、MiMo pid、端口状态；
- ACP 服务信息：只读查看；
- Agent 配置信息：默认只读；
- MiMo 命令助手：只允许白名单命令，不提供任意 shell。

## 安装

### 方法一：安装 fpk

在 fnOS 应用中心安装打包产物，例如：

```text
mimocode.v0.11.9.fpk
```

安装后从应用中心或桌面打开 `MiMo Code`。

### 方法二：本地打包

准备好官方 `mimo` 二进制，并放到：

```text
app/server/mimo
```

然后在源码根目录执行：

```bash
fnpack build
```

生成的 fpk 位于当前工作目录。

> 注意：不要在 `/tmp` 下构建。某些 fnOS 环境的 `/tmp` ACL 会导致 fnpack 打包异常。建议使用 NAS 数据盘路径作为 build 目录。

## 使用流程

1. 安装并打开应用；
2. 首次进入时设置管理密码；
3. 在「模型与服务商」中选择 MiMo 官方模型或配置第三方 Provider；
4. 回到「工作台」确认服务状态；
5. 点击顶部「官方会话」开始使用官方 MiMo Web；
6. 如需排查问题，进入「健康检查」「日志诊断」或开启「工具箱」。

## 端口说明

| 端口 | 服务 | 说明 |
|---:|---|---|
| `5670` | wrapper | fnOS 应用入口、工作台、配置、日志、API |
| `5669` | mimo web | 官方 MiMo Web 会话界面 |

`5670` 是应用中心打开的入口。wrapper 会负责拉起和监控 `5669` 上的官方 Web 服务。

## 目录结构

```text
.
├── app/
│   └── server/
│       ├── public/          # wrapper 前端
│       ├── uwrapper.py      # wrapper HTTP 服务
│       └── mimo             # 官方二进制，打包时放入，不提交仓库
├── cmd/                     # fnOS 生命周期脚本
├── config/                  # fnOS 权限/资源配置
├── ui/                      # fnOS 桌面入口配置与图标
├── manifest                 # fnOS 应用 manifest
└── README.md
```

## 安全边界

本应用遵循以下安全边界：

- 不反编译、不修改官方 `mimo` 二进制；
- 不在 UI 中提供在线替换官方二进制能力；
- 不提供任意 shell 执行入口；
- 工具箱文件浏览只读；
- Agent/ACP 默认只读或强确认；
- Provider Key 本地保存，导出默认脱敏；
- 诊断包自动脱敏。

## fnOS 状态机注意事项

fnOS 应用中心使用 appcenter 数据库维护应用状态，不是单纯依赖 systemd。

本应用在 `cmd/main start` 中同步 appcenter 状态，确保：

```text
status = running
is_stop = true
```

实测如果 `status=running` 但 `is_stop=false`，可能出现服务端口正常、应用中心记录正常，但桌面无图标或应用中心点击打开无反应。

## 常见问题

### 1. 应用中心打开无反应 / 桌面没有图标

检查 appcenter 状态，正常应为：

```text
status=running
is_stop=true
```

如果服务正常但入口异常，优先检查 appcenter DB 状态。

### 2. 首页 404

确认安装后存在：

```text
/var/apps/mimocode/target/server/public/index.html
/var/apps/mimocode/target/server/public/js/app.js
/var/apps/mimocode/target/server/public/css/style.css
```

旧版本曾因安装脚本误删 `target/server/public` 导致首页 404，已在 v0.8.2 修复。

### 3. 安装日志出现复制自身错误

旧版本曾出现：

```text
cp: .../uwrapper.py and .../uwrapper.py are the same file
```

原因是 `install_callback` 在 `SRC == DST` 时仍复制自身。已在 v0.8.3 修复。

### 4. 官方会话显示异常

优先确认官方 Web 端口：

```text
默认直连路径 http://当前主机:5669/（/mimo-web/ 仅作为备用代理入口）
```

如果 iframe 受浏览器或官方 Web 限制，可在工作台点击「新窗口打开」。

### 5. `mimo run` 没有输出

`mimo run` 更适合作为 CLI 快速测试，不适合作为完整 Web 主会话。真实聊天请使用顶部「官方会话」。

## 版本历史

### v0.10.4

- 按 v0.5.0 风格修复官方会话页面；
- 官方会话进入后内容区裸 iframe，100% 宽高、无边框；
- 移除卡片、标题说明和右下角 fallback 弹窗遮挡；
- 包内验证清理 `__pycache__`。

### v0.10.3

- 顶部导航新增「官方会话」；
- 将官方会话从工作台中拆出为独立选项；
- 工作台改为状态和入口页。

### v0.10.2

- 将真实聊天主路径转交官方 `mimo web`；
- 自研 CLI 聊天降级为工具箱里的快速测试。

### v0.10.1

- 改善自研 CLI 聊天显示；
- 增加气泡、思考中状态、空输出提示。

### v0.10.0

- 补全 MiMo 官方模型列表；
- 默认模型改为 `mimo/mimo-auto`；
- 增加默认隐藏的 P3 开发者工具箱。

### v0.9.0

- 增加 Provider 首次配置向导；
- 增加会话历史、项目目录校验、模型切换、配置导入导出、诊断包；
- MCP 管理移入高级设置。

### v0.8.x

- v0.8.1：补齐 `/var/apps/mimocode/ui/config`；
- v0.8.2：修复 `target/server/public` 被误删导致首页 404；
- v0.8.3：修复安装脚本 `SRC == DST` 时复制自身报错。

## 许可证与上游

- 官方 MiMo Code：<https://github.com/XiaomiMiMo/MiMo-Code>
- 本仓库仅提供 fnOS 应用封装层、生命周期脚本和管理 UI。

请遵守官方 MiMo Code 的使用条款和模型服务条款。


### v0.11.7

- 修复官方会话 `/global/event` SSE 长连接代理，模型回复可实时显示。
- 补齐官方 Web 动态 `/assets/...` 资源代理，减少前端组件资源 404。
- 点击左侧「官方会话」时保留已有 iframe，离开/返回时尽量恢复上次会话页面。


### v0.11.8

- 补齐官方 MiMo `/file` 接口代理，修复启动时“列出文件失败”。
- 恢复官方会话路径时统一补 `/mimo-web` 前缀，修复返回官方会话后的 wrapper 404。
- 增加官方 SPA 路由兜底代理，兼容 `/<base64目录>/session/<session_id>`。


### v0.11.9

- 官方会话默认恢复为浏览器直连 `http://当前主机:5669/`，回到 v0.5.0 风格，避免 `/mimo-web/` 代理兼容 SSE、停止按钮、SPA 路由等问题。
- 保留 `/mimo-web/` 代理作为备用入口，不再作为主会话默认路径。
- wrapper 继续负责工作台、模型配置、免费模型库、健康检查、日志诊断和配置备份。
