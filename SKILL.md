---
name: paddleocr-ui-test
description: This skill should be used when the user asks to "test UI from screenshot", "verify UI matches expected", "check if button text is correct", "validate UI rendering", "compare screenshot content with code", "run visual UI test", "check accessibility from screenshot", "run OCR-based UI test", or "baseline UI regression". Provides dual-path UI validation using PaddleOCR screenshot text extraction cross-referenced with Playwright Accessibility Tree snapshots.
version: 0.2.0
---

# PaddleOCR UI Testing

OCR screenshot text extraction + Playwright Accessibility Tree cross-validation, with 6 levels of UI defect detection.

## Prerequisites

- Environment variables: `PADDLEOCR_API_KEY` or `SILICONFLOW_API_KEY` (required)
- Python packages: `openai`, `playwright`, `Pillow`
- Browser: `playwright install chromium`

## Control Knobs

### 1. Test Scope (`--levels`)

| Level | What It Detects | When to Use |
|-------|------------------|-------------|
| L1 | Text consistency: whether visible text matches expectations | Check copy, button labels, and headings |
| L2 | Layout sanity: overflow, overlap, touch target size | Check layout anomalies and mobile touch accessibility |
| L3 | DOM cross-validation: OCR-visible text vs A11y Tree | Core feature: detect rendering issues and canvas-rendered text |
| L4 | Accessibility: missing alt/label, emoji used as icons | Form pages and image-heavy pages |
| L5 | Internationalization: detect incorrect language content | Localized pages |
| L6 | Dynamic content: text changes before and after actions | Loading states, pagination, async updates |

Default: `L1,L3`. If the user asks for a "full check", enable `L1,L2,L3,L4,L5`.

### 2. Page Type (`--profile`)

| Profile | Typical Use Case | Auto Settings |
|---------|------------------|---------------|
| `saas` | Admin systems and data table pages | L1,L2,L3,L5 / 1920x1080 / lenient count mismatch tolerance |
| `ecommerce` | E-commerce sites and product listings | L1,L2,L3,L4,L5 / 1440x900 / fuzzy matching + touch checks |
| `form` | Login, signup, and form pages | L1,L3,L4 / 1280x720 / enable label checks |
| `content` | Blog, news, and article pages | L1,L2,L3 / 1440x900 / lenient full-page text thresholds |
| `dashboard` | Analytics dashboards and data wall screens | L2,L3,L6 / 1920x1080 / overlap detection + content persistence |
| `mobile` | Mobile H5 or responsive pages | L1,L2,L3,L4 / 375x812 / touch target + overflow checks |

Profiles automatically set levels, viewport, `wait_ms`, and rule overrides.

### 3. Rule Tuning (`rules/*.json`)

Each rule file controls the detection behavior for one level. The agent may adjust them as needed.

#### L1: `rules/text-consistency.json`
- `default_strategy`: `exact` (strict) / `substring` (default) / `fuzzy` (tolerant)
- `match_strategies.fuzzy.threshold`: fuzzy match threshold, default 0.8
- `ignore_patterns`: text patterns to ignore, such as versions or hash strings

#### L2: `rules/layout-anomaly.json`
- `overflow.enabled`: whether to detect overflow
- `element_overlap.enabled` + `iou_threshold`: overlap detection toggle and IoU threshold
- `touch_target_size.enabled` + `min_width_px/min_height_px`: minimum touch target size
- `full_page_text.width_threshold/height_threshold`: thresholds for full-page text detection

#### L3: `rules/dom-ocr-crossval.json`
- `fuzzy_match.enabled` + `threshold`: fuzzy match toggle and threshold (`0.6` means match, `0.7` means warning)
- `count_mismatch.delta_threshold`: tolerated ratio for count differences, default 0.3
- `ignore_patterns`: text patterns to ignore

#### L4: `rules/accessibility.json`
- `missing_alt.enabled`: image alt checks (enabled by default)
- `missing_label.enabled`: interactive element label checks (disabled by default, enabled in the `form` profile)
- `canvas_rendered_text.enabled`: detect text visible in OCR but invisible in A11y
- `emoji_as_icon.enabled`: detect emoji used as icons

#### L5: `rules/i18n.json`
- `languages`: regex patterns for each language (`zh/en/ja/ko`)
- `common_false_positives`: terms that should not be falsely flagged, such as `OK`, `API`, `URL`

#### L6: `rules/dynamic-content.json`
- `state_transitions`: predefined state transition patterns (`loading→content`, `content→error`)
- `max_tracked_changes`: maximum number of tracked changes, default 5

### 4. Specific Expectations (`--config`)

When the user has explicit text expectations, generate a config JSON:

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

### 5. Regression Comparison (`--baseline` / `--baseline-file`)

- `--baseline`: save the current run result as the baseline (for first-time testing or when the user says "save baseline")
- `--baseline-file baseline.json`: compare against a historical baseline to detect removed/added text, layout drift, and count changes
- The baseline file is automatically saved as `baseline.json` in the output directory

### Supporting Parameters

- `--annotate`: mark issue regions on the screenshot; recommended when failures occur
- `--actions`: action sequence for L6 dynamic testing, such as `"click(#btn);wait(2000);screenshot"`
- `--output`: output directory, default `./test-results`

## Output Artifacts

| File | Description |
|------|-------------|
| `report.json` | Structured results including issue types, severity, and suggestions |
| `report.md` | Human-readable report |
| `screenshot.png` | Captured screenshot |
| `annotated.png` | Screenshot annotated with issue regions (generated when `--annotate` is used) |
| `baseline.json` | Baseline file (generated when `--baseline` is used) |

## Integration

### Input Contract

The minimum required input for this skill is `--url`.
Upstream skills do not need to understand this skill's config format; the agent is responsible for converting inputs.

Added lightweight flexible input modes while preserving the original behavior:

- `--input-mode url` (default): original mode, the skill captures screenshot + a11y data by itself
- `--input-mode artifacts --artifacts-dir <dir>`: consume page artifacts exported upstream
- `--input-mode mcp --input-json <file>`: consume an MCP payload (v1 currently supports path-based fields only)

Example MCP payload v1:

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

### Upstream Output Adaptation

| Upstream Output | Conversion Strategy | Example |
|----------------|---------------------|---------|
| Free-form dogfood text description | Extract key text into `expected_texts` | `"Button shows Submit"` → `{"submit_button": "Submit"}` |
| Dogfood screenshots / issue list | Map issues to the corresponding level checks | `"Text overlap"` → enable L2 |
| ui-ux-pro-max design system | Extract copy requirements into `expected_texts` | Button text from the design spec → config |
| ui-ux-pro-max accessibility guidance | Map to L4 rule switches | `"Check labels"` → `accessibility.missing_label.enabled=true` |
| ui-ux-pro-max i18n requirements | Map to L5 rules | `"Need Chinese/Japanese/Korean support"` → enable `ja/ko` language detection |
| dev-browser page state | Reuse screenshot + HTML + A11y Tree | Do not reload the page; consume artifacts directly |
| User natural-language description | Generate config directly | `"Confirm the title is Hello"` → `{"title": "Hello"}` |

### Collaboration Mode Selection

Choose the collaboration mode automatically based on user intent:

| User Says... | Mode | Flow |
|-------------|------|------|
| `"Check this page"` | standalone | Run only this skill (`L1,L3`) |
| `"Full check"` | standalone+ | Run all levels in this skill + `--annotate` |
| `"Explore first, then check"` | dogfood → this skill | dogfood discovers issues → generate config → this skill validates |
| `"Has anything changed compared with before?"` | baseline | Detect `baseline.json` → use `--baseline-file` |
| `"Does the implementation match the design?"` | ui-ux-pro-max → this skill | Convert design intent → extract expectations → validate |
| `"Help me operate it and then check"` | dev-browser → this skill | dev-browser navigates/interacts → this skill validates the final state |

### dev-browser Session Reuse

When collaborating with `dev-browser`, avoid launching a duplicate browser session:

1. After `dev-browser` finishes navigation/interactions, export:
   - Screenshot: `page.screenshot()`
   - HTML: `page.content()`
   - A11y Tree: `page.evaluate(A11Y_TREE_SCRIPT)`
2. This skill consumes those artifacts directly without reloading the page
3. Benefits: preserve session/cookies and reduce API calls

Recommended downstream integration for Playwright MCP / UI test generation MCP:

1. The upstream MCP exports screenshot + a11y tree + DOM into local artifacts
2. This skill consumes them directly with `--input-mode artifacts` or `--input-mode mcp`
3. This skill outputs `report.json` / `annotated.png` for downstream agents or MCP tools

Note: `L6 --actions` is only executed in `url` mode in the current lightweight version.

### Output Contract

Artifacts produced by this skill can be consumed by downstream skills:

| Artifact | Format | Downstream Usage |
|---------|--------|------------------|
| `report.json` | Structured issue list | dogfood can read the results and add new findings |
| `annotated.png` | Annotated screenshot | dev-browser can use `screenshot_region` coordinates to confirm issues |
| `baseline.json` | Baseline snapshot | Future runs can compare with `--baseline-file` |
| `screenshot.png` | Raw screenshot | Can be fed into other visual analysis skills |

### Collaboration Flow With Other Skills

```text
ui-ux-pro-max  →  Define design intent (color / typography / copy / accessibility requirements)
     ↓
dogfood        →  Explore the real page (find issues / unexpected behavior)
     ↓
paddleocr-ui-test →  Validate and guard (turn findings into automated regression checks)
```

- **dev-browser** is the execution engine: all skills can use it for page navigation and interaction
- **ui-ux-pro-max** defines the ideal state: what the page should look like
- **dogfood** is the discovery layer: what is actually wrong on the page
- **This skill** is the validation layer: turn findings into repeatable automated checks
