# PaddleOCR UI Test Skill

> AI-driven UI testing skill combining PaddleOCR screenshot analysis with DOM/Accessibility Tree cross-validation.

[中文文档](README.zh-CN.md)

## Overview

Traditional UI testing tools have blind spots:

| Approach | Tools | Core Defect |
|----------|-------|-------------|
| Pixel comparison | Playwright `toHaveScreenshot`, Percy | Only detects "different", can't understand "what's wrong, why" |
| DOM/A11y Tree | axe-core, Playwright a11y | Only analyzes structure, can't verify "what the user actually sees" |

PaddleOCR bridges the gap between "pixels" and "semantics" — extracting structured UI information from screenshots (text content, position, layout relationships), enabling AI Agents to "understand" screenshots like humans do.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Upstream Output (Any Format)                     │
├─────────────┬──────────────┬──────────────┬─────────────────────────┤
│  dogfood    │ ui-ux-pro-   │ dev-browser  │ User Natural Language    │
│  Free Text  │ max Design   │ Page State   │                         │
└──────┬──────┴──────┬───────┴──────┬───────┴────────────┬────────────┘
       │             │              │                    │
       ▼             ▼              ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Adaptation Layer (Agent Transform)               │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ Text Extract │  │ Rule Mapping  │  │ Artifact Reuse│               │
│  │ Free text    │  │ Design advice│  │ Reuse existing│               │
│  │ → expected  │  │ → L4 rules   │  │ browser session│              │
│  │   _texts    │  │ Design copy  │  │ No reload     │               │
│  │             │  │ → expected_  │  │               │               │
│  │             │  │   texts      │  │               │               │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                │                  │                       │
│         └────────────────┼──────────────────┘                       │
│                          ▼                                          │
│              ┌───────────────────────┐                              │
│              │  Intent Recognition     │                              │
│              │  "check page" → standalone│                            │
│              │  "full check" → all levels│                            │
│              │  "explore then check" → dogfood│                       │
│              │  "compare with before" → baseline│                     │
│              │  "design correct?" → design verify│                    │
│              │  "check after action" → session reuse│                 │
│              └───────────┬───────────┘                              │
└──────────────────────────┼──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Standard Input Contract                           │
│          --url | --profile | --config | --levels | --annotate        │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Skill Processing Pipeline                       │
│                                                                     │
│  Load rules/*.json → thresholds/strategies/toggles                   │
│  Load profile      → levels/viewport/rule overrides                  │
│  Playwright screenshot → PaddleOCR text extraction                   │
│  A11y Tree extract → L1-L6 detection engine                          │
│  BaselineDiff      → regression comparison (optional)                │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Output Contract                                   │
│       report.json | annotated.png | baseline.json | screenshot.png   │
└──────────────────────────┬──────────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Downstream Consumption                          │
│  dev-browser ← coordinate locate | dogfood ← new findings | CI/CD   │
└─────────────────────────────────────────────────────────────────────┘
```

## Installation

### Recommended (`npx skills`)

Install from GitHub (global for OpenCode):

```bash
npx skills add aotenjou/paddleOCR-UI-test --skill paddleocr-ui-test -g -a opencode -y
```

Install from GitHub (global for Claude Code):

```bash
npx skills add aotenjou/paddleOCR-UI-test --skill paddleocr-ui-test -g -a claude-code -y
```

List available skills in the repository:

```bash
npx skills add aotenjou/paddleOCR-UI-test --list
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
# Minimal: just URL
python3 scripts/ui_test.py --url https://example.com

# With profile (auto-sets levels, viewport, rules)
python3 scripts/ui_test.py --url https://example.com --profile form

# With specific expected texts
python3 scripts/ui_test.py --url https://example.com --config test-config.json --annotate

# Full suite with annotated screenshot
python3 scripts/ui_test.py --url https://example.com --levels L1,L2,L3,L4,L5 --annotate
```

### 5 Control Knobs

| Knob | Parameter | Description |
|------|-----------|-------------|
| Test Scope | `--levels` | L1-L6, default L1,L3 |
| Page Type | `--profile` | saas/ecommerce/form/content/dashboard/mobile |
| Rule Tuning | `rules/*.json` | Adjust thresholds, strategies, toggles |
| Specific Expectations | `--config` | Expected texts, language, etc. |
| Regression Compare | `--baseline` | Save baseline or diff against history |

## Test Levels

| Level | Scenario | Method |
|-------|----------|--------|
| L1 | Text consistency | OCR vs expected text (exact/substring/fuzzy) |
| L2 | Layout reasonableness | Overflow, overlap, touch target size |
| L3 | DOM consistency | OCR vs A11y Tree cross-validation |
| L4 | Accessibility | Missing alt/labels, canvas text, emoji icons |
| L5 | Internationalization | Language detection (zh/en/ja/ko) |
| L6 | Dynamic content | Action sequences + screenshot comparison |

## Project Structure

```
paddleOCR-UItest/
├── SKILL.md                          # Agent instructions (5 control knobs)
├── skill.json                        # Skill metadata
├── README.md                         # English docs
├── README.zh-CN.md                   # Chinese docs
├── LICENSE                           # Apache-2.0
├── rules/                            # Data-driven rules (6 files, with agent_hints)
│   ├── text-consistency.json         # L1: match strategies, thresholds, ignore patterns
│   ├── layout-anomaly.json           # L2: overflow, overlap, touch targets
│   ├── dom-ocr-crossval.json         # L3: fuzzy matching, count mismatch
│   ├── accessibility.json            # L4: alt, labels, canvas, emoji
│   ├── i18n.json                     # L5: language patterns, false positives
│   └── dynamic-content.json          # L6: state transitions, tracking
├── profiles/                         # Industry presets (6 files, with when_to_use)
│   ├── saas.json                     # Backend management systems
│   ├── ecommerce.json                # E-commerce websites
│   ├── form.json                     # Login/registration forms
│   ├── content.json                  # Blogs/articles
│   ├── dashboard.json                # Data dashboards
│   └── mobile.json                   # Mobile H5 pages
├── scripts/
│   ├── ui_test.py                    # Main test runner
│   ├── compare_ocr_dom.py            # Standalone OCR vs DOM validator (--ci)
│   ├── baseline_diff.py              # Baseline regression engine
│   ├── annotate_screenshot.py        # Annotated screenshot generator
│   └── source_map_lookup.py          # Source code location resolver
├── references/
│   ├── ocr-api.md                    # PaddleOCR API configuration
│   ├── a11y-tree.md                  # Accessibility tree format
│   └── test-patterns.md              # Common test patterns + CI/CD example
└── examples/
    └── test-config.json              # Test config example
```

## Integration

This skill is designed to work alongside other UI testing skills:

- **dogfood**: Exploratory testing → discoveries become `expected_texts` config → this skill guards against regressions
- **dev-browser**: Browser automation → navigates pages → this skill validates the final state
- **ui-ux-pro-max**: Design system → defines expected UI → this skill verifies implementation matches design

See `SKILL.md` for the full integration protocol including input/output contracts and collaboration modes.

## CI/CD Integration

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

## License

Apache-2.0. See [LICENSE](LICENSE).
