# PaddleOCR UI 测试

> 基于 PaddleOCR 截图分析与 DOM/无障碍树交叉验证的 AI 驱动 UI 测试工具。

[English README](README.md)

## 概述

传统 UI 测试工具存在盲区：

| 方案 | 代表工具 | 核心缺陷 |
|------|---------|---------|
| 像素对比 | Playwright `toHaveScreenshot`, Percy | 只能检测"是否不同"，无法理解"哪里错了、为什么错" |
| DOM/A11y Tree | axe-core, Playwright a11y | 只能分析结构，无法验证"用户实际看到了什么" |

PaddleOCR 填补了"像素"和"语义"之间的鸿沟——从截图中提取结构化的 UI 信息（文字内容、位置、布局关系），让 AI Agent 能像人一样"看懂"截图。

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        上游输出 (任意格式)                            │
├─────────────┬──────────────┬──────────────┬─────────────────────────┤
│  dogfood    │ ui-ux-pro-   │ dev-browser  │ 用户自然语言             │
│  自由文本   │ max 设计系统  │ 页面状态      │                         │
└──────┬──────┴──────┬───────┴──────┬───────┴────────────┬────────────┘
       │             │              │                    │
       ▼             ▼              ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     适配层 (Agent 转换)                               │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ 文本提取     │  │ 规则映射      │  │ 产物复用      │               │
│  │ 自由文本     │  │ 设计建议     │  │ 复用已有     │               │
│  │ → expected  │  │ → L4 规则    │  │ 浏览器会话   │               │
│  │   _texts    │  │ 设计文案     │  │ 不重新加载   │               │
│  │             │  │ → expected_  │  │              │               │
│  │             │  │   texts      │  │              │               │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                │                  │                       │
│         └────────────────┼──────────────────┘                       │
│                          ▼                                          │
│              ┌───────────────────────┐                              │
│              │  意图识别 (决策树)      │                              │
│              │  "检查页面" → standalone│                              │
│              │  "全面检查" → 全 levels │                              │
│              │  "探索再检查" → dogfood │                              │
│              │  "和之前比" → baseline  │                              │
│              │  "设计对不对" → 设计验证 │                              │
│              │  "操作后检查" → 会话复用 │                              │
│              └───────────┬───────────┘                              │
└──────────────────────────┼──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    标准输入契约                                       │
│   --url | --input-mode | --artifacts-dir | --input-json | --source   │
│      + --profile | --config | --levels | --annotate | --baseline     │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      本 skill 处理流程                                │
│                                                                     │
│  加载 rules/*.json → 阈值/策略/开关                                  │
│  加载 profile      → levels/viewport/规则覆盖                        │
│  Playwright 截图   → PaddleOCR 文字提取                              │
│  A11y Tree 提取    → L1-L6 检测引擎                                  │
│  BaselineDiff      → 回归对比 (可选)                                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    输出契约                                           │
│       report.json | annotated.png | baseline.json | screenshot.png   │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      下游消费                                         │
│  dev-browser ← 坐标定位 | dogfood ← 补充发现 | CI/CD ← 构建状态      │
└─────────────────────────────────────────────────────────────────────┘
```

## 安装

### 推荐方式（`npx skills`）

从 GitHub 安装（OpenCode 全局）：

```bash
npx skills add aotenjou/paddleOCR-UI-test --skill paddleocr-ui-test -g -a opencode -y
```

从 GitHub 安装（Claude Code 全局）：

```bash
npx skills add aotenjou/paddleOCR-UI-test --skill paddleocr-ui-test -g -a claude-code -y
```

列出仓库中可用的 skills：

```bash
npx skills add aotenjou/paddleOCR-UI-test --list
```

### 手动安装

将仓库根目录复制或符号链接到以下位置之一：
- `~/.agents/skills/paddleocr-ui-test/`
- `~/.claude/skills/paddleocr-ui-test/`
- `.claude/skills/paddleocr-ui-test/`（项目本地）

## 前置要求

```bash
pip install openai playwright Pillow
playwright install chromium
export SILICONFLOW_API_KEY="your-api-key"
```

## 使用方法

通过关键词触发："test UI"、"check screenshot"、"verify UI"、"visual regression"、"OCR test" 等。

或直接运行：

```bash
# 最小：只需 URL
python3 scripts/ui_test.py --url https://example.com

# 使用 profile（自动设置 levels、viewport、规则）
python3 scripts/ui_test.py --url https://example.com --profile form

# 指定预期文字
python3 scripts/ui_test.py --url https://example.com --config test-config.json --annotate

# 全面检查 + 标注截图
python3 scripts/ui_test.py --url https://example.com --levels L1,L2,L3,L4,L5 --annotate

# 消费预采集产物（dev-browser / Playwright MCP 输出）
python3 scripts/ui_test.py --input-mode artifacts --artifacts-dir ./artifacts --source playwright-mcp

# 消费 MCP payload JSON（v1 路径字段）
python3 scripts/ui_test.py --input-mode mcp --input-json ./mcp-payload.json --source ui-test-generation-mcp
```

### MCP Payload（v1 路径型）

```json
{
  "source": "playwright-mcp",
  "url": "https://example.com",
  "viewport": "1280x720",
  "screenshot_path": "./artifacts/screenshot.png",
  "a11y_tree_path": "./artifacts/a11y_tree.json",
  "dom_path": "./artifacts/dom.html"
}
```

### 5 个控制旋钮

| 旋钮 | 参数 | 说明 |
|------|------|------|
| 测试范围 | `--levels` | L1-L6，默认 L1,L3 |
| 页面类型 | `--profile` | saas/ecommerce/form/content/dashboard/mobile |
| 规则调优 | `rules/*.json` | 修改阈值、策略、开关 |
| 具体期望 | `--config` | 预期文字、语言等 |
| 回归对比 | `--baseline` | 保存基线或与历史对比 |

## 测试级别

| 级别 | 场景 | 检测方法 |
|------|------|---------|
| L1 | 文字一致性 | OCR 文字 vs 预期文字（精确/子串/模糊） |
| L2 | 布局合理性 | 溢出、重叠、触控区域大小 |
| L3 | DOM 一致性 | OCR vs A11y Tree 交叉验证 |
| L4 | 无障碍 | 缺失 alt/label、canvas 文字、emoji 图标 |
| L5 | 国际化 | 语言检测（zh/en/ja/ko） |
| L6 | 动态内容 | 动作序列 + 截图前后对比 |

## 项目结构

```
paddleOCR-UItest/
├── SKILL.md                          # Agent 指令（5 个控制旋钮）
├── skill.json                        # Skill 元数据
├── README.md                         # 英文文档
├── README.zh-CN.md                   # 中文文档
├── LICENSE                           # Apache-2.0
├── rules/                            # 数据驱动规则（6 个文件，含 agent_hints）
│   ├── text-consistency.json         # L1: 匹配策略、阈值、忽略模式
│   ├── layout-anomaly.json           # L2: 溢出、重叠、触控区域
│   ├── dom-ocr-crossval.json         # L3: 模糊匹配、数量差异
│   ├── accessibility.json            # L4: alt、label、canvas、emoji
│   ├── i18n.json                     # L5: 语言正则、误判词
│   └── dynamic-content.json          # L6: 状态转换、追踪数
├── profiles/                         # 行业预设（6 个文件，含 when_to_use）
│   ├── saas.json                     # 后台管理系统
│   ├── ecommerce.json                # 电商网站
│   ├── form.json                     # 表单/登录页
│   ├── content.json                  # 博客/文章页
│   ├── dashboard.json                # 数据大屏
│   └── mobile.json                   # 移动端 H5
├── scripts/
│   ├── ui_test.py                    # 主测试脚本
│   ├── smoke_input_modes.py          # 输入模式轻量 smoke 检查
│   ├── compare_ocr_dom.py            # OCR vs DOM 交叉验证引擎（支持 --ci）
│   ├── baseline_diff.py              # 基线回归对比引擎
│   ├── annotate_screenshot.py        # 标注截图生成
│   ├── source_map_lookup.py          # 源码位置映射
│   └── adapters/                     # 柔性输入适配层
│       ├── base.py                   # Evidence bundle 契约
│       ├── registry.py               # 自动输入模式选择
│       ├── standalone_url.py         # 兼容原有 URL 采集模式
│       ├── artifact_dir.py           # 消费 screenshot/a11y/dom 产物
│       └── mcp_payload.py            # 消费 MCP payload JSON
├── references/
│   ├── ocr-api.md                    # PaddleOCR API 配置
│   ├── a11y-tree.md                  # 无障碍树格式
│   └── test-patterns.md              # 常见测试模式 + CI/CD 示例
└── examples/
    └── test-config.json              # 测试配置示例
```

## 与其他 Skill 协作

本 skill 设计为与其他 UI 测试 skill 协同工作：

- **dogfood**：探索性测试 → 发现的问题转为 `expected_texts` → 本 skill 做回归守卫
- **dev-browser**：浏览器自动化 → 导航页面 → 本 skill 验证最终状态
- **ui-ux-pro-max**：设计系统 → 定义预期 UI → 本 skill 验证实现匹配设计

### 轻量柔性适配层

- 保持 L1-L6 检测引擎不变，仅扩展输入采集边界。
- 向后兼容：原有 `--url` 工作流保持不变。
- 新增 MCP 友好输入模式：
  - `--input-mode artifacts --artifacts-dir <dir>`
  - `--input-mode mcp --input-json <file>`
- 当前限制：`L6 --actions` 仅在 `url` 模式支持。

完整协作协议与输入/输出契约见 `SKILL.md`。

## CI/CD 集成

```yaml
# .github/workflows/ui-test.yml
name: UI Test
on: [push]
jobs:
  ui-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install openai playwright Pillow
          playwright install chromium
      - name: Run UI tests
        env:
          SILICONFLOW_API_KEY: ${{ secrets.SILICONFLOW_API_KEY }}
        run: |
          python3 scripts/ui_test.py \
            --url https://staging.example.com \
            --levels L1,L3 \
            --config tests/ui-config.json \
            --output test-results \
            --format json
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: ui-test-results
          path: test-results/
```

## 许可证

Apache-2.0。详见 [LICENSE](LICENSE)。
