# 大肥鱼桌宠（astrbot_plugin_dafeiyu_deskpet）

> **原创** AstrBot 桌宠脑端插件（为大肥鱼定制）  
> **作者 / Author**：[Grok Bot (Ideas Implementation)](https://github.com/JiachengWu-5)  
> **配套壳**：同机 Windows 透明窗 `dafeiyu-deskpet-shell`（另见仓库说明）

本插件由 **Grok Bot（Ideas Implementation）** 编写与维护，不是第三方桌宠套壳。

## 功能（v1）

1. **本地 WebSocket 脑端** — 默认 `ws://127.0.0.1:18765`，驱动桌宠壳。
2. **看屏吐槽（仅文字）** — 定时（随机 5–15 分钟）或点击截屏后，只把**文字**发到主人 QQ；**永不发送截图**。
3. **人格一致** — 看屏 / 壳聊复用 AstrBot 里的「大肥鱼」人格（与 QQ 同一套），再附加场景补充。
4. **会话镜像** — QQ 私聊里大肥鱼的回复可镜像到壳气泡；**壳内本地聊天不同步到 QQ**。
5. **可换立绘** — 壳侧 `assets/default/manifest.json`；Live2D 预留。

## 隐私（必读）

- **截图永不发到 QQ**。截屏只在本机：壳 → 插件 → 视觉 LLM；临时文件用完删除。
- QQ **只**可能收到看屏反馈的**纯文字**（无图片、无截屏附件）。
- **视觉失败 / 看不清**：只在桌宠气泡短提示，**不**发 QQ。
- **壳本地聊天不同步到 QQ**（代码锁定；`enable_shell_chat_to_qq` 即使打开也无效）。
- **QQ 私聊回复可以镜像到桌宠气泡**（`enable_qq_mirror_to_shell` 默认 `true`）。

## 相关端口

| 服务 | 端口 | 说明 |
|------|------|------|
| NapCat / OneBot | `:6199` | 与 QQ 通信 |
| AstrBot 管理面板 | `:6185` | Dashboard |
| 桌宠 WebSocket | `:18765` | 脑端监听；壳连 `ws://127.0.0.1:18765` |

## 安装

1. 将本仓库放入 AstrBot 的 `plugins/astrbot_plugin_dafeiyu_deskpet/`。
2. Dashboard → 插件 → 启用 **大肥鱼桌宠**。
3. 配置主人 QQ UID（默认示例 `407171301`，请改成你自己的）。
4. 启动配套壳（Windows）：`dafeiyu-deskpet-shell/run.bat`（需本机已装依赖并连上 `:18765`）。

需要 **aiocqhttp** + NapCat（或等价 OneBot）已连通。

## 配置

| 键 | 说明 | 默认 |
|----|------|------|
| `enabled` | 总开关 | `true` |
| `ws_host` | WS 监听地址 | `127.0.0.1` |
| `ws_port` | WS 端口 | `18765` |
| `qq_uid` | 主人 QQ | （请填写） |
| `screen_interval_min_sec` | 看屏最小间隔（秒） | `300` |
| `screen_interval_max_sec` | 看屏最大间隔（秒） | `900` |
| `skip_if_nothing_to_say` | 没话可说则跳过发 QQ | `true` |
| `enable_qq_mirror_to_shell` | QQ 回复镜像到壳 | `true` |
| `enable_shell_chat_to_qq` | 壳聊天同步到 QQ（禁止） | `false` |

## 配套壳（简要）

仓库外或同组织下的 `dafeiyu-deskpet-shell`：

- 右键 / 托盘：立刻看屏、桌宠大小、显示/隐藏、退出
- 点击立绘：触发看屏
- 立绘白底已抠透明；大小可调（小/中/大/更大）

## 开发说明

- 协议常量见 `core/protocol.py`（壳侧需复制相同 `MSG_*` 字符串，勿直接 import AstrBot）。
- 单测：在插件目录执行 `pytest tests`。

## 归因

**Author: Grok Bot (Ideas Implementation)**  
为 Jiacheng 的大肥鱼定制。欢迎在 AstrBot 插件市场引用本仓库。

## License

MIT（见 `LICENSE`）