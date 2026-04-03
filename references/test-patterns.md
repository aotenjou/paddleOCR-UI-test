# Common UI Test Patterns

This document describes common test patterns and configurations for paddleocr-ui-test.

## Pattern 1: Critical Text Verification (L1)

Verify that specific text elements are present and correct on a page.

```json
{
  "expected_texts": {
    "page_title": "Welcome to the-internet",
    "submit_button": "Submit",
    "login_button": "Login",
    "error_message": "Invalid credentials"
  },
  "expected_language": "en"
}
```

**Use case:** Regression testing after i18n changes, verifying copy updates.

## Pattern 2: Form Validation (L1 + L3)

Test that form fields render correctly and match DOM expectations.

```json
{
  "expected_texts": {
    "username_label": "Username",
    "password_label": "Password",
    "submit_button": "Login"
  },
  "expected_elements": [
    {"role": "textbox", "name": "Username"},
    {"role": "textbox", "name": "Password"},
    {"role": "button", "name": "Login"}
  ]
}
```

**Use case:** Ensuring form accessibility and visual rendering match.

## Pattern 3: List/Table Content (L3)

Verify that all items declared in DOM are actually rendered.

```json
{
  "expected_counts": {
    "list_items": 10,
    "table_rows": 5
  }
}
```

**Use case:** Pagination bugs, virtual scrolling issues, lazy loading failures.

## Pattern 4: Multi-Language Pages (L5)

Test that the correct language is displayed.

```json
{
  "expected_language": "zh",
  "expected_texts": {
    "nav_home": "首页",
    "nav_about": "关于",
    "nav_contact": "联系"
  }
}
```

**Use case:** i18n regression testing, detecting untranslated strings.

## Pattern 5: Loading State Transitions (L6)

Test that loading indicators disappear and content appears.

```json
{
  "dynamic_test": {
    "initial_state": {
      "should_contain": ["Loading...", "spinner"],
      "should_not_contain": ["data content"]
    },
    "action": "wait(3000)",
    "final_state": {
      "should_contain": ["data content"],
      "should_not_contain": ["Loading...", "spinner"]
    }
  }
}
```

**Use case:** Async content loading, skeleton screens, error states.

## Pattern 6: Responsive Layout (L2)

Test layout at different viewport sizes.

```bash
# Mobile viewport
python3 scripts/ui_test.py --url https://example.com \
  --viewport 375x812 --levels L2

# Tablet viewport
python3 scripts/ui_test.py --url https://example.com \
  --viewport 768x1024 --levels L2

# Desktop viewport
python3 scripts/ui_test.py --url https://example.com \
  --viewport 1920x1080 --levels L2
```

**Use case:** Responsive design regression, overflow detection.

## Pattern 7: Accessibility Audit (L4)

Joint OCR + A11y analysis for accessibility issues.

```bash
python3 scripts/ui_test.py --url https://example.com \
  --levels L4 --annotate
```

Detects:
- Images without alt text
- Buttons without accessible names
- Text that is visible but not in accessibility tree (canvas-rendered)
- Low-confidence OCR regions (possible contrast issues)

## Pattern 8: Full Suite (L1-L6)

Run all test levels for comprehensive analysis.

```bash
python3 scripts/ui_test.py --url https://example.com \
  --levels L1,L2,L3,L4,L5,L6 \
  --viewport 1920x1080 \
  --annotate \
  --source-map ./dist \
  --format both
```

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
          PADDLEOCR_API_KEY: ${{ secrets.PADDLEOCR_API_KEY }}
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

## Tips

1. **Start narrow:** Begin with L1 (text) tests on critical pages before expanding
2. **Use configs:** Keep expected texts in config files, not command lines
3. **Annotate:** Always use `--annotate` for visual debugging of failures
4. **Source maps:** Provide `--source-map` in CI to get file:line in reports
5. **Stable waits:** Adjust `--wait` based on page load characteristics
6. **Viewport matters:** Test at multiple viewports for responsive issues
