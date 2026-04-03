# Accessibility Tree Format

## Overview

The accessibility tree (A11y Tree) is a structured representation of all UI elements on a page, similar to what screen readers use. It provides semantic information about each element beyond what is visible in a screenshot.

## Tree Structure

Each node in the tree contains:

```json
{
  "role": "button",
  "name": "Submit",
  "bounds": {
    "x": 480,
    "y": 280,
    "width": 80,
    "height": 40
  },
  "tagName": "BUTTON",
  "visible": true,
  "children": [...]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `role` | string | Semantic role (button, textbox, heading, etc.) |
| `name` | string | Accessible name (aria-label, alt, or text content) |
| `bounds` | object | Position and size in pixels |
| `bounds.x` | number | Left edge in pixels |
| `bounds.y` | number | Top edge in pixels |
| `bounds.width` | number | Element width in pixels |
| `bounds.height` | number | Element height in pixels |
| `tagName` | string | HTML tag name |
| `visible` | boolean | Whether element has non-zero dimensions |
| `children` | array | Nested child elements |

## Common Roles

| Role | HTML Element | Description |
|------|-------------|-------------|
| `button` | `<button>` | Clickable button |
| `textbox` | `<input>` | Text input field |
| `link` | `<a>` | Hyperlink |
| `heading` | `<h1>`-`<h6>` | Section heading |
| `img` | `<img>` | Image |
| `navigation` | `<nav>` | Navigation region |
| `main` | `<main>` | Main content area |
| `banner` | `<header>` | Page header |
| `contentinfo` | `<footer>` | Page footer |
| `list` | `<ul>`, `<ol>` | List container |
| `listitem` | `<li>` | List item |
| `generic` | `<div>`, `<span>` | Generic container |

## How This Plugin Builds the Tree

Unlike Playwright's built-in `accessibility.snapshot()`, this plugin uses a custom `page.evaluate()` script that:

1. Walks the DOM tree starting from `document.body`
2. Extracts role from `role` attribute or HTML tag name
3. Extracts name from `aria-label`, `alt`, or `textContent`
4. Gets bounding box via `getBoundingClientRect()`
5. Recurses into children up to depth 20

This approach works in any browser without Playwright-specific APIs and provides pixel-accurate bounds for coordinate matching with OCR results.

## Cross-Validation with OCR

The key insight: **A11y Tree tells you what SHOULD be visible, OCR tells you what IS visible.**

| Scenario | A11y Tree | OCR | Conclusion |
|----------|-----------|-----|------------|
| Normal | "Submit" | "Submit" | OK |
| Missing render | "Submit" | not found | Element hidden/off-screen |
| Text corruption | "Submit" | "Subm1t" | Font/rendering issue |
| Extra content | not found | "Debug: true" | Unexpected visible content |
| Count mismatch | 10 items | 7 items | Some items not rendered |

## Coordinate Matching

To correlate OCR text regions with DOM elements:

1. Take OCR box center point: `(x, y)`
2. Find DOM element whose `bounds` contains `(x, y)`
3. If multiple elements overlap, pick the smallest (most specific)
4. Use the matched element's `tagName` and `data-file` attribute for source mapping
