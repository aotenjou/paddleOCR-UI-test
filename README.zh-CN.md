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

## 安装

### 推荐方式（`npx skills`）

从 GitHub 安装（OpenCode 全局）：

```bash
npx skills add aotenjou/paddleocr-ui-test --skill paddleocr-ui-test -g -a opencode -y
```

从 GitHub 安装（Claude Code 全局）：

```bash
npx skills add aotenjou/paddleocr-ui-test --skill paddleocr-ui-test -g -a claude-code -y
```

列出仓库中可用的 skills：

```bash
npx skills add aotenjou/paddleocr-ui-test --list
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
python3 scripts/ui_test.py --url https://example.com --levels L1,L2,L3 --output results
```

### 命令行选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--url` | 目标 URL（必填） | — |
| `--levels` | 测试级别（L1-L6，逗号分隔） | L1,L3 |
| `--viewport` | 浏览器视口大小（宽x高） | 1280x720 |
| `--wait` | 页面加载后等待时间（毫秒） | 2000 |
| `--output` | 结果输出目录 | ./test-results |
| `--format` | 输出格式：json, markdown, both | both |
| `--source-map` | 源码映射目录（用于定位问题代码） | 无 |
| `--annotate` | 生成标注截图 | false |
| `--config` | 测试配置文件 JSON 路径 | 无 |

## 测试级别

| 级别 | 场景 | 检测方法 |
|------|------|---------|
| L1 | 文字一致性 | OCR 文字 vs 预期文字 |
| L2 | 布局合理性 | OCR 框坐标分析 |
| L3 | DOM 一致性 | OCR vs A11y Tree 交叉验证 |
| L4 | 无障碍 | OCR + A11y 联合分析 |
| L5 | 国际化 | OCR 语言检测 |
| L6 | 动态内容 | 截图序列对比 |

## 测试结果

### Benchmark 对比

基于 VisualWebArena 范式的对比实验（7 个任务，9 个 ground truth issues）：

| 指标 | 纯 A11y | OCR+A11y | 提升 |
|------|---------|----------|------|
| **精确率** | 0.0% | 61.5% | +61.5pp |
| **召回率** | 0.0% | 88.9% | +88.9pp |
| **F1 分数** | 0.0% | 72.7% | +72.7pp |
| **问题覆盖率** | 0.0% | 88.9% | +88.9pp |

### 单元测试

| 测试套件 | 通过 | 失败 | 总计 |
|---------|------|------|------|
| 核心算法（text_similarity, compare 等） | 40 | 0 | 40 |
| 引擎 + 报告（L1-L6, ReportGenerator） | 24 | 0 | 24 |
| **总计** | **64** | **0** | **64** |

### 逐任务结果

| 任务 | 描述 | A11y-only | 真实 OCR 结果 | 说明 |
|------|------|-----------|-------------|------|
| **T1** | 正常登录页 | ✅ 0/0 | ✅ 0 issues | 无问题页面，正确通过 |
| **T2** | 按钮空格 | ❌ 0/1 | ⚠️ 自动纠正 | PaddleOCR-VL 的 LM 自动纠正了空格 |
| **T3** | 错误信息可见 | ❌ 0/1 | ✅ 检测到 | OCR 发现隐藏元素意外可见 |
| **T4** | 页脚文字缺失 | ❌ 0/1 | ✅ 检测到 | OCR 发现 DOM 声明的文字未渲染 |
| **T5** | 中文字符错误 | ❌ 0/1 | ⚠️ 自动纠正 | PaddleOCR-VL 的 LM 自动纠正了形近字 |
| **T6** | 国际化问题 | ❌ 0/1 | ⚠️ 需配置 | 需要预期语言配置才能检测 |
| **T7** | 多问题组合 | ❌ 0/4 | ✅ 3/4 | 检测到 3/4 个真实问题 |

### 关键发现

1. **纯 A11y 方案对视觉渲染问题零检测率** — 只能看到"DOM 声明了什么"，无法验证"用户实际看到了什么"
2. **OCR+A11y 交叉验证有效检测视觉问题** — 在模拟 benchmark 中检测到 8/9 个 ground truth issues（召回率 88.9%）
3. **PaddleOCR-VL 的 LM 自动纠正** — 内置语言模型会自动纠正识别结果（如"登 录"→"登录"），适合语义理解但不适合精确字符级检测。对于需要精确检测的场景，建议使用不带 LM 的两阶段 PaddleOCR 模型
4. **中文 UI 测试是 PaddleOCR 的天然优势** — 大多数 OCR 方案对中文支持差，PaddleOCR 是差异化竞争点

## 架构

```
┌─────────────────────────────────────────────────────┐
│                  AI Agent (LLM)                      │
│         综合分析 → 测试报告 → 修复建议                │
└───────────────┬──────────────────────┬──────────────┘
                │                      │
    ┌───────────▼──────────┐  ┌───────▼──────────────┐
    │   PaddleOCR 引擎      │  │  前端代码分析层        │
    │  截图 → 结构化UI信息   │  │  DOM + A11y Tree     │
    │  - 文字内容 + 坐标    │  │  - 组件树             │
    │  - 文本区域框        │  │  - 元素属性/状态       │
    │  - 布局关系          │  │  - 样式信息            │
    └───────────┬──────────┘  └───────┬──────────────┘
                │                      │
    ┌───────────▼──────────────────────▼──────────────┐
    │           测试执行层 (Playwright)                 │
    │         截图 + DOM Snapshot + A11y Tree          │
    └─────────────────────────────────────────────────┘
```

## 项目结构

```
paddleOCR-UItest/
├── SKILL.md                  # Skill 核心指令
├── skill.json                # Skill 元数据
├── README.md                 # 英文文档
├── README.zh-CN.md           # 中文文档
├── LICENSE                   # Apache-2.0
├── scripts/
│   ├── ui_test.py            # 主测试脚本
│   ├── compare_ocr_dom.py    # OCR vs DOM 交叉验证引擎
│   └── source_map_lookup.py  # 源码位置映射
├── references/
│   ├── ocr-api.md            # PaddleOCR API 配置
│   ├── a11y-tree.md          # 无障碍树格式
│   └── test-patterns.md      # 常见测试模式
└── examples/
    └── test-config.json      # 测试配置示例
```

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
