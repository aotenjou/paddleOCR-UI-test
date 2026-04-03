---
name: paddleocr-ui-test
description: This skill should be used when the user asks to "test UI from screenshot", "verify UI matches expected", "check if button text is correct", "validate UI rendering", "compare screenshot content with code", "run visual UI test", "check accessibility from screenshot", "run OCR-based UI test", or mentions combining OCR with DOM analysis for UI testing. Provides dual-path UI validation using PaddleOCR screenshot text extraction cross-referenced with Playwright Accessibility Tree snapshots.
version: 0.1.0
---

# PaddleOCR UI Testing

AI-driven UI testing that combines PaddleOCR screenshot analysis with DOM/Accessibility Tree cross-validation for intelligent visual regression testing.

## Overview

This skill provides six-level UI testing capabilities:

| Level | Scenario | Detection Method |
|-------|----------|-----------------|
| L1 | Text consistency | OCR text vs expected text |
| L2 | Layout合理性 | OCR box coordinate analysis |
| L3 | DOM consistency | OCR vs A11y Tree cross-validation |
| L4 | Accessibility | OCR + A11y joint analysis |
| L5 | Internationalization | OCR language detection |
| L6 | Dynamic content | Screenshot sequence comparison |

## Quick Start

### Prerequisites

- Python 3.8+ with `openai`, `playwright`, `Pillow` installed
- PaddleOCR API key via `PADDLEOCR_API_KEY` environment variable (or `SILICONFLOW_API_KEY`)
- Playwright browsers installed (`playwright install`)

### Basic Usage

Run the `/ui-test` command or execute the test script directly:

```bash
python3 scripts/ui_test.py --url https://example.com --config examples/test-config.json
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--url` | Target URL to test (required) |
| `--config` | Test configuration JSON file |
| `--levels` | Test levels to run: L1,L2,L3,L4,L5,L6 (default: L1,L3) |
| `--viewport` | Browser viewport size, e.g. "1920x1080" (default: 1280x720) |
| `--wait` | Milliseconds to wait after page load (default: 2000) |
| `--output` | Output directory for results (default: ./test-results) |
| `--format` | Output format: json, markdown, both (default: both) |
| `--source-map` | Path to source map directory for code location lookup |
| `--annotate` | Generate annotated screenshot with issue markers |

## Test Execution Flow

```
1. Navigate to URL with Playwright
2. Wait for page to stabilize
3. Capture screenshot
4. Extract accessibility tree snapshot
5. Send screenshot to PaddleOCR for text + coordinate extraction
6. Cross-validate OCR results against A11y Tree
7. Map issues to source code locations (if --source-map provided)
8. Generate report (JSON + Markdown)
9. Optionally generate annotated screenshot
```

## Test Levels Detail

### L1: Text Consistency

Compare text visible in screenshot against expected text values.

```bash
python3 scripts/ui_test.py --url https://example.com/login \
  --levels L1 \
  --config examples/test-config.json
```

Detects: typos, missing text, extra text, character encoding issues, text truncation.

### L2: Layout Reasonableness

Analyze OCR box coordinates to detect layout anomalies.

```bash
python3 scripts/ui_test.py --url https://example.com --levels L2
```

Detects: overlapping elements, text overflow, misaligned components, hidden content visible.

### L3: DOM Consistency (Core Feature)

Cross-reference what OCR sees vs what the DOM claims exists.

```bash
python3 scripts/ui_test.py --url https://example.com --levels L3
```

Detects: elements in DOM but not rendered, elements rendered but not in DOM, text content mismatches, count discrepancies.

### L4: Accessibility

Joint OCR + A11y analysis for visual accessibility issues.

```bash
python3 scripts/ui_test.py --url https://example.com --levels L4
```

Detects: low contrast text (inferred from OCR confidence), missing labels, unreadable text.

### L5: Internationalization

Detect language mismatches in multi-language UIs.

```bash
python3 scripts/ui_test.py --url https://example.com/zh --levels L5
```

Detects: untranslated strings, wrong language content, encoding issues.

### L6: Dynamic Content

Compare screenshot sequences to verify state transitions.

```bash
python3 scripts/ui_test.py --url https://example.com --levels L6 \
  --actions "click(#load-more);wait(2000);screenshot"
```

Detects: loading states not clearing, animations stuck, content not updating.

## Output Format

### JSON Report

```json
{
  "test_id": "ui-test-20260402-001",
  "url": "https://example.com/login",
  "timestamp": "2026-04-02T10:30:00Z",
  "summary": {
    "total_checks": 12,
    "passed": 10,
    "failed": 2,
    "warnings": 1
  },
  "results": [
    {
      "type": "text_mismatch",
      "severity": "error",
      "level": "L1",
      "element": "submit_button",
      "expected": "提交",
      "actual": "提 交",
      "source_location": "src/components/LoginForm.tsx:42",
      "screenshot_region": [[480, 280], [560, 320]],
      "suggestion": "检查 CSS letter-spacing 或 font-kerning 设置"
    }
  ]
}
```

### Markdown Report

Human-readable report with test summary, failed items, warnings, and annotated screenshot reference.

## Source Code Location Mapping

When `--source-map` is provided, issues are mapped to source code locations:

1. OCR identifies text at pixel coordinates (x, y)
2. Playwright provides DOM element at same coordinates
3. Source map resolves DOM element to original source file:line
4. Report includes exact file path and line number for fixes

## Integration with Other Skills

### With dogfood (Exploratory Testing)

1. Run dogfood first for exploratory page analysis
2. Extract issues found by dogfood as test cases
3. Run paddleocr-ui-test for automated regression verification

### With dev-browser (Browser Automation)

1. Use dev-browser to navigate to target pages
2. Capture screenshots via dev-browser
3. Feed screenshots to paddleocr-ui-test for analysis

## Additional Resources

### Reference Files

- **`references/ocr-api.md`** - PaddleOCR API configuration and model selection
- **`references/a11y-tree.md`** - Accessibility Tree format and parsing guide
- **`references/test-patterns.md`** - Common UI test patterns and configurations

### Example Files

- **`examples/test-config.json`** - Complete test configuration example

### Scripts

- **`scripts/ui_test.py`** - Main test execution script
- **`scripts/compare_ocr_dom.py`** - OCR vs DOM cross-validation engine
- **`scripts/source_map_lookup.py`** - Source code location resolver
