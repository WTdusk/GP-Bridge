# Kontakt 音源 Profile 提取流程

本文档用于指导 Agent 从 Kontakt 音源的官方 Guide PDF 中提取 Guitar Pro → MIDI 所需的技法映射，并生成可被 GP Bridge 使用的 profile。

## 目标

将官方手册中的演奏信息转换为结构化配置：

- Keyswitch 音符
- Keyswitch 的 MIDI 通道
- CC 控制器和取值范围
- 速度、力度或音域触发规则
- 技法组合规则
- 适用的 Kontakt 乐器/预设和版本

不要根据经验猜测没有在手册中明确说明的映射。

## 输入要求

开始前确认以下信息：

1. 官方 PDF 文件路径。
2. Kontakt 音色库名称。
3. 具体乐器名称和预设名称。
4. Kontakt 版本，以及音色库版本（如果手册有版本信息）。
5. 用户希望支持的 Guitar Pro 技法，例如 palm mute、harmonic、bend、slide、hammer-on、pull-off、vibrato。

如果 PDF 是扫描件或文本无法提取，先使用 OCR，再继续后续步骤。OCR 结果必须保留页码，便于回查。

## PDF 提取步骤

### 1. 建立工作记录

在开始提取前，创建临时记录，至少包含：

```text
音源名称：
乐器/预设：
音色库版本：
Kontakt 版本：
PDF 文件：
PDF 页数：
提取日期：
```

### 2. 搜索关键章节

优先搜索以下关键词及其变体：

- Keyswitch
- keyswitches
- articulation
- articulation map
- playing techniques
- MIDI
- controller
- CC
- pitch bend
- performance
- mute / palm mute
- harmonic
- slide
- bend
- vibrato
- hammer-on / pull-off

记录每条映射的 PDF 页码和原文上下文。只记录手册明确表示“触发”或“控制”的内容。

### 3. 统一音符和八度表示

手册可能使用 `C0`、`C1`、`C-1` 或 DAW 专用八度编号。必须记录原始写法，并转换为 MIDI note number。

转换时使用明确的基准，不要凭视觉猜测：

```text
MIDI note 60 = C4（内部统一表示）
MIDI note = 12 * (octave + 1) + semitone
```

如果手册没有说明八度编号规则，不能直接生成最终 profile。将该项标记为 `ambiguous_octave`，并在报告中要求用 Kontakt 键盘显示或 MIDI Monitor 验证。

### 4. 区分事件类型

将手册内容归类为以下事件：

- `keyswitch`：发送一个短音符触发技法。
- `cc`：发送控制器和数值。
- `pitch_bend`：发送 14-bit Pitch Bend。
- `program_change`：切换预设或音色。
- `channel_switch`：改变 MIDI 通道。
- `note_modifier`：改变演奏音符的力度、时值或音域。

如果手册只描述了界面按钮，没有说明 MIDI 触发方式，不要把它写入自动映射。

### 力度触发

如果手册说明某个技法由力度区间触发，而不是 Keyswitch，可以在技法中加入 `velocity` 规则：

```json
{
  "techniques": {
    "hammer_on": {
      "events": [],
      "velocity": {
        "factor": 0.75,
        "offset": 8,
        "min": 1,
        "max": 96
      }
    }
  }
}
```

处理顺序是：原始力度乘以 `factor`，再加上 `offset`，最后限制在 `min` 到 `max`。如果使用固定力度，可指定 `value`。只有 PDF 明确给出力度规则时才填写，不能根据听感猜测。

### 5. 记录上下文和限制

每个技法都要记录：

- 触发事件
- 触发时机（音符前、同时、音符后）
- 事件持续时间
- 是否需要释放事件
- 适用的 MIDI 通道
- 是否只适用于某个预设或模式
- 是否与其他技法互斥

例如，Keyswitch 通常应在演奏音符之前发送，并保留一个很短的持续时间；不要假设所有音源都使用这一行为，除非手册明确说明或验证通过。

## Profile 文件格式

将最终结果保存为：

```text
GPBridgeData/Profiles/kontakt/<library-id>.json
```

推荐结构：

```json
{
  "schema_version": 1,
  "vendor": "厂商名称",
  "library": "音色库名称",
  "instrument": "乐器或预设名称",
  "kontakt_version": "兼容版本或 unknown",
  "library_version": "音色库版本或 unknown",
  "source": {
    "document": "官方 PDF 文件名",
    "pages": [12, 13],
    "octave_convention": "C4=60",
    "confidence": "verified"
  },
  "default_channel": 1,
  "string_channels": {
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6
  },
  "techniques": {
    "palm_mute": {
      "events": [
        {"type": "keyswitch", "note": 24, "velocity": 127, "duration_ticks": 1}
      ],
      "source_pages": [12]
    },
    "vibrato": {
      "events": [
        {"type": "cc", "controller": 1, "value": 80}
      ],
      "source_pages": [13]
    }
  },
  "combinations": [
    {
      "when": ["slide", "vibrato"],
      "events": [
        {"type": "keyswitch", "note": 27, "velocity": 127, "duration_ticks": 1}
      ],
      "source_pages": [14]
    }
  ],
  "unsupported": [],
  "ambiguities": []
}
```

通道编号使用 1 到 16。`source_pages` 必须保留，方便人工复核。`confidence` 只能使用：

- `verified`：手册明确说明，且已通过 MIDI Monitor 或 Kontakt 实测。
- `documented`：手册明确说明，但尚未实测。
- `inferred`：从上下文推断，默认禁止用于生产 profile。

## 验证流程

生成 profile 后必须完成以下检查：

1. JSON 可以被解析。
2. 所有 MIDI note、channel、controller、value 都在合法范围内。
3. 所有 Guitar Pro 技法都有明确映射、明确标记为不支持，或进入 `ambiguities`。
4. Keyswitch 音符不能与实际演奏音域冲突，除非手册明确说明使用同一音域。
5. 生成测试 MIDI，至少包含：
   - 一个普通音符
   - 一个带 Keyswitch 的音符
   - 一个 CC 技法
   - 一个组合技法
   - 两根弦同时发声且使用不同通道
6. 用 MIDI Monitor 或 Kontakt 的 MIDI 指示器确认事件顺序和通道。
7. 把验证结果写入同目录的 `<library-id>.verification.md`。

验证记录至少包含：

```text
测试日期：
Kontakt 版本：
预设名称：
使用的 MIDI 通道：
测试的 Keyswitch：
测试的 CC：
结果：通过 / 失败 / 部分通过
已知问题：
```

## 歧义和失败处理

以下情况禁止静默猜测：

- 八度编号不明确。
- 同一个技法在不同页面有冲突定义。
- PDF 只展示界面，没有 MIDI 说明。
- Keyswitch 依赖未记录的预设状态。
- 手册与实测结果不一致。

处理方式：

1. 把问题写入 `ambiguities`。
2. 在转换报告中显示警告。
3. 不把未经确认的映射标记为 `verified`。
4. 如果该技法会导致错误发声，默认让转换失败，而不是静默输出错误 MIDI。

## 提交前检查清单

- [ ] 本地使用时安装到 `GPBridgeData/Profiles/kontakt/`；社区分享时提交到 `GP-Bridge-Presets/kontakt/`，并按 CONTRIBUTING.md 更新目录及验证记录。
- [ ] JSON 格式正确。
- [ ] PDF 页码已记录。
- [ ] 八度规则已确认。
- [ ] 所有映射有来源或明确标记为不支持。
- [ ] 组合技法已覆盖需要的连用场景。
- [ ] 测试 MIDI 已生成。
- [ ] 测试结果已记录。
- [ ] 未确认项目已写入 `ambiguities`。
- [ ] README 或 profile 索引已说明如何调用该音源 profile。

## Agent 输出要求

完成后，Agent 应报告：

1. 使用的 PDF 文件和页码。
2. 创建或修改的 profile 路径。
3. 已支持的技法。
4. 未支持或有歧义的技法。
5. 八度编号转换规则。
6. 是否完成 Kontakt/MIDI Monitor 实测。
7. 测试 MIDI 和验证报告路径。

如果没有足够信息确认映射，Agent 必须明确说明缺口，不得把猜测写成确定配置。
