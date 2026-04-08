from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from playwright.async_api import async_playwright

from .base import EvidenceBundle


A11Y_TREE_SCRIPT = """() => {
    function buildA11yTree(node, depth = 0) {
        if (depth > 20) return null;
        const role = node.getAttribute('role') ||
            (node.tagName === 'BUTTON' ? 'button' : '') ||
            (node.tagName === 'INPUT' ? 'textbox' : '') ||
            (node.tagName === 'IMG' ? 'img' : '') ||
            (node.tagName === 'A' ? 'link' : '') ||
            (node.tagName === 'H1' ? 'heading' : '') ||
            (node.tagName === 'H2' ? 'heading' : '') ||
            (node.tagName === 'H3' ? 'heading' : '') ||
            (node.tagName === 'H4' ? 'heading' : '') ||
            (node.tagName === 'H5' ? 'heading' : '') ||
            (node.tagName === 'H6' ? 'heading' : '') ||
            (node.tagName === 'NAV' ? 'navigation' : '') ||
            (node.tagName === 'MAIN' ? 'main' : '') ||
            (node.tagName === 'HEADER' ? 'banner' : '') ||
            (node.tagName === 'FOOTER' ? 'contentinfo' : '') ||
            node.tagName?.toLowerCase() || '';
        const name = node.getAttribute('aria-label') ||
            node.getAttribute('alt') ||
            node.textContent?.trim().substring(0, 200) || '';
        const rect = node.getBoundingClientRect();
        const result = {
            role: role || 'generic',
            name: name,
            bounds: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            },
            tagName: node.tagName,
            visible: rect.width > 0 && rect.height > 0
        };
        const children = [];
        for (const child of node.children) {
            const childTree = buildA11yTree(child, depth + 1);
            if (childTree) children.push(childTree);
        }
        if (children.length) result.children = children;
        return result;
    }
    return buildA11yTree(document.body);
}"""


async def capture_from_url(
    *,
    url: str,
    viewport: str,
    wait_ms: int,
    screenshot_path: Path,
    source: str = "standalone",
    actions: Optional[str] = None,
    after_screenshot_path: Optional[Path] = None,
) -> Tuple[EvidenceBundle, Optional[str]]:
    viewport_tuple = tuple(map(int, viewport.split("x")))
    after_path = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": viewport_tuple[0], "height": viewport_tuple[1]}
        )

        print(f"Navigating to {url} ...")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(wait_ms)

        print("Capturing screenshot ...")
        await page.screenshot(path=str(screenshot_path), full_page=True)

        print("Extracting accessibility tree ...")
        a11y_tree = await page.evaluate(A11Y_TREE_SCRIPT)
        dom_html = await page.content()

        if actions:
            await execute_actions(page, actions)
            if after_screenshot_path:
                await page.screenshot(path=str(after_screenshot_path), full_page=True)
                after_path = str(after_screenshot_path)

        await browser.close()

    return (
        EvidenceBundle(
            screenshot_path=str(screenshot_path),
            a11y_tree=a11y_tree or {},
            dom_html=dom_html,
            url=url,
            viewport=viewport,
            source=source,
            capabilities={
                "has_dom": bool(dom_html),
                "has_a11y": bool(a11y_tree),
                "has_actions": bool(actions),
            },
            provenance={
                "browser": "playwright-chromium",
                "capture_mode": "standalone_url",
            },
        ),
        after_path,
    )


async def execute_actions(page, actions_str: str) -> None:
    actions = actions_str.split(";")
    for action in actions:
        action = action.strip()
        if not action:
            continue
        if action.startswith("click("):
            selector = action[6:-1]
            print(f"  Clicking: {selector}")
            await page.click(selector)
        elif action.startswith("wait("):
            ms = int(action[5:-1])
            print(f"  Waiting: {ms}ms")
            await page.wait_for_timeout(ms)
        elif action.startswith("type("):
            inner = action[5:-1]
            comma_idx = inner.find(",")
            if comma_idx != -1:
                selector = inner[:comma_idx].strip()
                text = inner[comma_idx + 1 :].strip().strip('"').strip("'")
                print(f"  Typing '{text}' into: {selector}")
                await page.fill(selector, text)
        elif action == "screenshot":
            pass
        else:
            print(f"  Unknown action: {action}")
