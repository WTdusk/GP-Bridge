# 项目检查记录

检查日期：2026-11-05。开发者：**WTdusk**。

## 已修复

- 预设的根节点、容器类型、MIDI 通道、非有限数值、事件时长和组合条件校验不完整：现在返回明确错误；CLI 在生成 MIDI 前校验预设。
- 组合技法命中后，其他未命中组合中的独立技法可能被跳过：现在只抑制已经由命中组合处理的技法。
- `score-timewise` MusicXML 被交给 `score-partwise` 解析器，可能导出错误时序：现在明确拒绝，并提示转换格式。
- MCP 的中文管道编码依赖 Windows 默认代码页：现在明确采用 UTF-8。补充 ping、通知不回复、无效请求处理和工具执行错误结果。错误处理依据 [MCP 2024-11-05 schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2024-11-05/schema.json)。
- 缺少源码仓库忽略规则：已排除 Python 环境、缓存、临时下载、JUCE、构建产物和个人设置，保留指定内置预设和验证说明。
- 构建脚本依赖本机专用 Python 路径：增加 `-Python` 参数、优先使用 `.venv`，并检查 Windows Python 和构建依赖。脚本结束时恢复工作目录和 PYTHONPATH。
- 打包会复制个人预设目录里的所有文件：现在发布包只取指定的 Shreddage 预设及验证记录。
- 补充 WTdusk 的 README、AUTHORS、帮助文本、Windows EXE 和安装器元数据；拆分运行与开发依赖，并添加 Windows/Python 3.12–3.14 CI 配置。

## 验证结果

- Windows Python 3.12.14：`pytest` **48 项通过**（原有 29 项，新增 19 项）。
- 隐藏窗口下的 Tk/TkinterDnD GUI 初始化、预设加载与帮助署名检查通过。
- 示例乐谱通过 CLI 转换，输出 MIDI 和 JSON 报告。
- 内置 Shreddage 预设校验通过，Windows 版本信息文件解析通过，PowerShell 构建脚本语法检查通过。
- 完整 Windows 构建通过：已重新生成 `dist/GPBridge.exe`、`dist/GPBridgeMCP.exe`、`dist/GPBridge-portable.zip` 和 `dist/GPBridge-Setup.exe`。三个 EXE 的开发者元数据均为 WTdusk。
- 打包后的 MCP EXE 已通过 ping、默认预设发现和实际 MIDI 转换检查；便携 ZIP 与安装器 payload 的 ZIP 完整性、内置预设白名单和 AUTHORS 文件检查通过。
- 使用临时 Git 元数据核对待提交清单，忽略规则生效。项目根目录尚未初始化 Git，也没有创建远程仓库或推送。
- 对候选源码进行了常见 API Key、GitHub Token、AWS Key 和私钥标记扫描，未发现匹配；未进行完整历史或第三方安全审计。

## 发布前仍需关注

1. **播放准确性**：目前 MIDI 使用单一速度，不能保留完整变速图和拍号图；反复记号按书写顺序播放一次。此类乐谱需要人工检查导出结果。
2. **Kontakt 实机验证**：现有 Shreddage 预设状态为手册有据，尚未在实际 Kontakt 音源中验证。仍需核对键位、CC1、弯音范围、连奏及多乐器路由。
3. **GUI 提取窗口生命周期**：静态检查发现 PDF 提取线程读取 Tk 变量并调用窗口回调；请求期间关闭对话框后，线程仍可能写入预设并访问已销毁的窗口。建议后续通过主线程消息队列处理结果，并定义取消行为；本轮未修改这部分流程。
4. **干净系统验证**：需在无开发环境的 Windows 上人工验证拖放、安装、文件权限和完整使用流程。隐藏窗口初始化检查未覆盖这些交互。
5. **许可证与发布材料**：项目尚未选择许可证。如果计划以开源方式发布，需要确定许可证；二进制分发还需要整理所带第三方组件的声明。临时下载的手册、参考源码和 JUCE 没有纳入待提交清单。
6. **CI**：已添加工作流；GitHub 上的三个 Python 版本任务尚未实际运行。

后续新增预设时，需同步维护 `.gitignore` 的内置预设白名单与 `build.ps1` 的打包清单。
