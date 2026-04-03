# PaddleOCR UI Test Skill

> AI-driven UI testing skill combining PaddleOCR screenshot analysis with DOM/Accessibility Tree cross-validation.

[中文文档](README.zh-CN.md)

## Installation

### Recommended (`npx skills`)

Install from GitHub (global for OpenCode):

```bash
npx skills add <owner>/paddleocr-ui-test --skill paddleocr-ui-test -g -a opencode -y
```

Install from GitHub (global for Claude Code):

```bash
npx skills add <owner>/paddleocr-ui-test --skill paddleocr-ui-test -g -a claude-code -y
```

List discoverable skills in the repository:

```bash
npx skills add <owner>/paddleocr-ui-test --list
```

### Manual

Copy or symlink the repository root to one of:
- `~/.agents/skills/paddleocr-ui-test/`
- `~/.claude/skills/paddleocr-ui-test/`
- `.claude/skills/paddleocr-ui-test/` (project-local)

## Prerequisites

```bash
pip install openai playwright Pillow
playwright install chromium
export SILICONFLOW_API_KEY="your-api-key"
```

## Usage

Trigger by mentioning: "test UI", "check screenshot", "verify UI", "visual regression", "OCR test", etc.

Or run directly:

```bash
python3 scripts/ui_test.py --url https://example.com --levels L1,L2,L3 --output results
```

## Test Levels

| Level | Scenario | Method |
|-------|----------|--------|
| L1 | Text consistency | OCR vs expected text |
| L2 | Layout reasonableness | OCR box coordinates |
| L3 | DOM consistency | OCR vs A11y Tree |
| L4 | Accessibility | Joint OCR + A11y |
| L5 | Internationalization | Language detection |
| L6 | Dynamic content | Screenshot sequences |

## Benchmark Results

Based on a [VisualWebArena](https://jykoh.com/vwa)-style benchmark (7 tasks, 9 ground truth issues):

| Metric | A11y-only | OCR+A11y | Improvement |
|--------|-----------|----------|-------------|
| **Precision** | 0.0% | 61.5% | +61.5pp |
| **Recall** | 0.0% | 88.9% | +88.9pp |
| **F1 Score** | 0.0% | 72.7% | +72.7pp |
| **Issue Coverage** | 0.0% | 88.9% | +88.9pp |

### Test Coverage

| Suite | Passed | Failed | Total |
|-------|--------|--------|-------|
| Core Algorithms (text_similarity, compare, etc.) | 40 | 0 | 40 |
| Engine + Reports (L1-L6, ReportGenerator) | 24 | 0 | 24 |
| **Total** | **64** | **0** | **64** |

### Key Findings

- **A11y-only has 0% detection rate** for visual rendering issues — it only sees what the DOM declares, not what users actually see
- **OCR+A11y cross-validation** detects 8/9 ground truth issues (88.9% recall) in simulated benchmark
- **PaddleOCR-VL auto-correction**: The built-in LM automatically fixes typos (e.g., "登 录" → "登录"), which is great for semantic understanding but limits precise character-level detection
- See [test/BENCHMARK_REPORT.md](https://github.com/aotenjou/paddleOCR-UItest-full/blob/main/test/BENCHMARK_REPORT.md) for full details

## License

Apache-2.0
