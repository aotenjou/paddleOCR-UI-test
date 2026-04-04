# PaddleOCR UI Test Skill

> AI-driven UI testing skill combining PaddleOCR screenshot analysis with DOM/Accessibility Tree cross-validation.

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

## Test Levels

| Level | Scenario | Method |
|-------|----------|--------|
| L1 | Text consistency | OCR vs expected text (exact/substring/fuzzy) |
| L2 | Layout reasonableness | Overflow, overlap, touch target size |
| L3 | DOM consistency | OCR vs A11y Tree cross-validation |
| L4 | Accessibility | Missing alt/labels, canvas text, emoji icons |
| L5 | Internationalization | Language detection (zh/en/ja/ko) |
| L6 | Dynamic content | Action sequences + screenshot comparison |

## Architecture

```
paddleocr-ui-test/
├── SKILL.md                          # Agent instructions (5 control knobs)
├── rules/                            # Data-driven detection rules (6 files)
│   ├── text-consistency.json         # L1: match strategies, thresholds
│   ├── layout-anomaly.json           # L2: overflow, overlap, touch targets
│   ├── dom-ocr-crossval.json         # L3: fuzzy matching, count mismatch
│   ├── accessibility.json            # L4: alt, labels, canvas, emoji
│   ├── i18n.json                     # L5: language patterns
│   └── dynamic-content.json          # L6: state transitions
├── profiles/                         # Industry presets (6 files)
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
├── references/                       # Technical reference docs
└── examples/
    └── test-config.json              # Config format example
```

## Integration

This skill is designed to work alongside other UI testing skills:

- **dogfood**: Exploratory testing → discoveries become `expected_texts` config → this skill guards against regressions
- **dev-browser**: Browser automation → navigates pages → this skill validates the final state
- **ui-ux-pro-max**: Design system → defines expected UI → this skill verifies implementation matches design

See `SKILL.md` for the full integration protocol including input/output contracts and collaboration modes.

## License

Apache-2.0
