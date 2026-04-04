---
name: paddleocr-ui-test
description: This skill should be used when the user asks to "test UI from screenshot", "verify UI matches expected", "check if button text is correct", "validate UI rendering", "compare screenshot content with code", "run visual UI test", "check accessibility from screenshot", "run OCR-based UI test", or "baseline UI regression". Provides dual-path UI validation using PaddleOCR screenshot text extraction cross-referenced with Playwright Accessibility Tree snapshots.
version: 0.2.0
---

# PaddleOCR UI Testing

OCR 截图文字提取 + Playwright Accessibility Tree 交叉验证，6 级 UI 缺陷检测。

## Prerequisites

- Env: `PADDLEOCR_API_KEY` 或 `SILICONFLOW_API_KEY`（必须）
- Python: `openai`, `playwright`, `Pillow`
- 浏览器: `playwright install chromium`

## Control Knobs

### 1. 测试范围 (`--levels`)

| Level | 检测什么 | 何时使用 |
|-------|---------|---------|
| L1 | 文字一致性：可见文字是否符合预期 | 检查文案、按钮文字、标题是否正确 |
| L2 | 布局合理性：溢出、重叠、触控区域 | 检查排版异常、移动端触控可达性 |
| L3 | DOM 交叉验证：OCR 可见文字 vs A11y Tree | 核心功能：检测渲染异常、canvas 文字 |
| L4 | 无障碍：缺失 alt/label、emoji 作图标 | 表单页、图片密集页 |
| L5 | 多语言：检测错误的语言内容 | 国际化页面 |
| L6 | 动态内容：操作前后的文字变化 | 加载状态、分页、异步更新 |

默认: `L1,L3`。用户说"全面检查"时开 `L1,L2,L3,L4,L5`。

### 2. 页面类型 (`--profile`)

| Profile | 适用场景 | 自动设置 |
|---------|---------|---------|
| `saas` | 后台管理系统、数据表格页 | L1,L2,L3,L5 / 1920x1080 / 宽松数量差异 |
| `ecommerce` | 电商网站、商品列表 | L1,L2,L3,L4,L5 / 1440x900 / 模糊匹配+触控检查 |
| `form` | 登录/注册/表单页 | L1,L3,L4 / 1280x720 / 开启 label 检查 |
| `content` | 博客/新闻/文章页 | L1,L2,L3 / 1440x900 / 宽松全页文字阈值 |
| `dashboard` | 数据大屏/分析面板 | L2,L3,L6 / 1920x1080 / 重叠检测+内容持久化 |
| `mobile` | 移动端 H5/响应式页 | L1,L2,L3,L4 / 375x812 / 触控区域+溢出检查 |

Profile 自动设置 levels、viewport、wait_ms 和规则覆盖。

### 3. 规则调优 (`rules/*.json`)

每个 rule 文件控制一个 level 的检测行为。agent 可根据需求修改：

#### L1: `rules/text-consistency.json`
- `default_strategy`: `exact`（严格）/ `substring`（默认）/ `fuzzy`（容错）
- `match_strategies.fuzzy.threshold`: 模糊匹配阈值，默认 0.8
- `ignore_patterns`: 忽略的文字模式（如版本号、哈希值）

#### L2: `rules/layout-anomaly.json`
- `overflow.enabled`: 是否检测溢出
- `element_overlap.enabled` + `iou_threshold`: 重叠检测开关和 IoU 阈值
- `touch_target_size.enabled` + `min_width_px/min_height_px`: 触控区域最小尺寸
- `full_page_text.width_threshold/height_threshold`: 全页文字判定阈值

#### L3: `rules/dom-ocr-crossval.json`
- `fuzzy_match.enabled` + `threshold`: 模糊匹配开关和阈值（0.6 为匹配，0.7 为警告）
- `count_mismatch.delta_threshold`: 数量差异容忍比例，默认 0.3
- `ignore_patterns`: 忽略的文本模式

#### L4: `rules/accessibility.json`
- `missing_alt.enabled`: 图片 alt 检查（默认开）
- `missing_label.enabled`: 交互元素 label 检查（默认关，form profile 开启）
- `canvas_rendered_text.enabled`: 检测 canvas 渲染文字（OCR 可见但 A11y 不可见）
- `emoji_as_icon.enabled`: 检测 emoji 用作图标

#### L5: `rules/i18n.json`
- `languages`: 各语言的正则模式（zh/en/ja/ko）
- `common_false_positives`: 不误判的词（OK, API, URL 等）

#### L6: `rules/dynamic-content.json`
- `state_transitions`: 预定义的状态转换模式（loading→content, content→error）
- `max_tracked_changes`: 最大追踪变化数，默认 5

### 4. 具体期望 (`--config`)

当用户有具体的文字预期时，生成 config JSON：

```json
{
  "expected_texts": {
    "page_title": "Login Page",
    "username_label": "Username",
    "submit_button": "Login"
  },
  "expected_language": "en",
  "ignore_texts": ["Powered by"]
}
```

### 5. 回归对比 (`--baseline` / `--baseline-file`)

- `--baseline`: 保存当前运行结果为基线（首次测试或用户说"保存基准"）
- `--baseline-file baseline.json`: 与历史基线对比，检测文字移除/新增、布局偏移、数量变化
- 基线文件自动保存在输出目录的 `baseline.json`

### 辅助参数

- `--annotate`: 在截图上标注问题区域（失败时推荐开启）
- `--actions`: L6 动态测试的动作序列，如 `"click(#btn);wait(2000);screenshot"`
- `--output`: 输出目录，默认 `./test-results`

## Output Artifacts

| 文件 | 说明 |
|------|------|
| `report.json` | 结构化结果，含 issue 类型、严重级别、建议 |
| `report.md` | 人类可读报告 |
| `screenshot.png` | 捕获的截图 |
| `annotated.png` | 标注了问题区域的截图（`--annotate` 时生成） |
| `baseline.json` | 基线文件（`--baseline` 时生成） |

## Integration

### Input Contract

本 skill 接受的最小输入: `--url` (必须)。
上游 skill 不需要知道本 skill 的 config 格式，agent 负责转换。

### 上游输出适配

| 上游输出 | 转换方式 | 示例 |
|---------|---------|------|
| dogfood 自由文本描述 | 提取关键文字 → expected_texts | "按钮显示 Submit" → `{"submit_button": "Submit"}` |
| dogfood 截图/问题列表 | 问题归类 → 对应 level 的检测规则 | "文字重叠" → 开 L2 |
| ui-ux-pro-max 设计系统 | 提取文案要求 → expected_texts | 设计稿按钮文字 → config |
| ui-ux-pro-max 无障碍建议 | 映射到 L4 规则开关 | "检查 label" → `accessibility.missing_label.enabled=true` |
| ui-ux-pro-max i18n 要求 | 映射到 L5 规则 | "需要中日韩支持" → 开 ja/ko 语言检测 |
| dev-browser 页面状态 | 复用截图 + HTML + A11y Tree | 不重新加载页面，直接消费产物 |
| 用户自然语言描述 | 直接生成 config | "确认标题是 Hello" → `{"title": "Hello"}` |

### 协作模式选择

根据用户意图自动选择协作模式:

| 用户说... | 模式 | 流程 |
|----------|------|------|
| "检查这个页面" | standalone | 只跑本 skill (L1,L3) |
| "全面检查" | standalone+ | 本 skill 全 levels + `--annotate` |
| "先探索再检查" | dogfood → 本 skill | dogfood 发现 → 生成 config → 本 skill 验证 |
| "和之前比有没有变化" | baseline | 检测 baseline.json → `--baseline-file` |
| "设计实现得对不对" | ui-ux-pro-max → 本 skill | 设计意图 → 提取 expected → 验证 |
| "帮我操作然后检查" | dev-browser → 本 skill | dev-browser 导航+操作 → 本 skill 验证最终状态 |

### dev-browser 会话复用

与 dev-browser 协作时，避免重复启动浏览器:

1. dev-browser 完成页面导航/操作后，导出:
   - 截图: `page.screenshot()`
   - HTML: `page.content()`
   - A11y Tree: `page.evaluate(A11Y_TREE_SCRIPT)`
2. 本 skill 直接消费这些产物，不重新加载页面
3. 好处: 保持 session/cookie 一致，节省 API 调用

### Output Contract

本 skill 的产出可被下游 skill 消费:

| 产物 | 格式 | 下游可消费 |
|------|------|-----------|
| `report.json` | 结构化 issue 列表 | dogfood 可读取 results 补充新发现 |
| `annotated.png` | 标注截图 | dev-browser 可定位 `screenshot_region` 坐标确认问题 |
| `baseline.json` | 基线快照 | 后续运行可 `--baseline-file` 对比 |
| `screenshot.png` | 原始截图 | 可喂给其他视觉分析 skill |

### 与其他 Skill 的协作流程

```
ui-ux-pro-max  →  定义设计意图 (颜色/排版/文案/无障碍要求)
     ↓
dogfood        →  探索实际页面 (发现问题/意外行为)
     ↓
paddleocr-ui-test →  验证并守卫 (把发现转为自动化回归检查)
```

- **dev-browser** 是执行引擎: 所有 skill 都可用它做页面导航和交互
- **ui-ux-pro-max** 是理想态: 定义页面"应该"长什么样
- **dogfood** 是发现机制: 找出"实际"有什么问题
- **本 skill** 是验证层: 把发现固化为可持续运行的自动化检查
