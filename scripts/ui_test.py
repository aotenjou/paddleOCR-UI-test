#!/usr/bin/env python3
"""PaddleOCR UI test orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

from core.config import (
    list_available_profiles,
    load_profile,
    load_rules,
    load_runtime_config,
    resolve_run_settings,
)
from core.pipeline import (
    apply_baseline_stage,
    build_detection_context,
    collect_evidence,
    enrich_findings,
    run_ocr_stage,
    write_output_stage,
)
from core.reporting import summarize_issues
from engines.registry import execute_levels
from providers.ocr import list_ocr_providers


def _env_api_key() -> str:
    return os.environ.get("PADDLEOCR_API_KEY") or os.environ.get("SILICONFLOW_API_KEY", "")


async def run_test(args: argparse.Namespace) -> None:
    start_time = time.time()
    api_key = _env_api_key()
    if not api_key:
        print("Error: PADDLEOCR_API_KEY or SILICONFLOW_API_KEY not set")
        sys.exit(1)

    raw_config = load_runtime_config(args.config)
    rules = load_rules(args.rules)
    profile: Dict[str, Any] = {}
    if args.profile:
        profile = load_profile(args.profile, rules=rules)
        print(f"Using profile: {args.profile} ({profile.get('description', '')})")

    settings = resolve_run_settings(
        args=args,
        raw_config=raw_config,
        rules=rules,
        profile=profile,
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    collected = await collect_evidence(
        args,
        viewport=settings.viewport,
        wait_ms=settings.wait_ms,
        output_dir=output_dir,
        enable_actions="L6" in settings.levels,
    )
    ocr_artifacts = await run_ocr_stage(
        args,
        api_key=api_key,
        collected=collected,
        run_action_ocr="L6" in settings.levels,
    )

    print(f"Running test levels: {', '.join(settings.levels)} ...")
    context = build_detection_context(
        settings=settings,
        collected=collected,
        ocr_artifacts=ocr_artifacts,
    )
    outcome = execute_levels(settings.levels, context)
    results = apply_baseline_stage(
        args,
        output_dir=output_dir,
        collected=collected,
        ocr_artifacts=ocr_artifacts,
        viewport=settings.viewport,
        summary=summarize_issues(outcome.issues),
        results=outcome.issues,
    )
    results, source_map_execution = enrich_findings(
        results,
        a11y_elements=collected.a11y_elements,
        source_map_dir=args.source_map,
    )

    duration = time.time() - start_time

    reporter, outputs = write_output_stage(
        args,
        collected=collected,
        ocr_artifacts=ocr_artifacts,
        results=results,
        duration=duration,
        profile_name=args.profile or "",
        levels=settings.levels,
        detector_execution=outcome.execution,
        source_map_execution=source_map_execution,
    )

    print(f"Generating reports to {args.output} ...")
    for name, output_path in outputs.items():
        print(f"  {name}: {output_path}")

    if args.annotate:
        from annotate_screenshot import annotate_screenshot

        annotated_path = output_dir / "annotated.png"
        annotate_screenshot(str(collected.screenshot_path), results, str(annotated_path))
        print(f"  annotated: {annotated_path}")

    summary = reporter.summary()
    print(
        f"\nDone in {duration:.1f}s - "
        f"{summary['total']} checks: "
        f"errors {summary['error']}, warnings {summary['warning']}, info {summary['info']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="PaddleOCR UI Test")
    parser.add_argument("--url", help="Target URL (required for URL mode)")
    parser.add_argument(
        "--input-mode",
        choices=["auto", "url", "artifacts", "mcp"],
        default="auto",
        help="Input mode: url (default), artifacts directory, or mcp payload JSON",
    )
    parser.add_argument(
        "--artifacts-dir",
        help="Artifacts directory containing screenshot/a11y/dom files",
    )
    parser.add_argument(
        "--input-json",
        help="MCP payload JSON file (path-based payload in v1)",
    )
    parser.add_argument(
        "--source",
        help="Source label for metadata (e.g. dev-browser, playwright-mcp)",
    )
    parser.add_argument("--config", help="Test config JSON file")
    parser.add_argument(
        "--levels",
        default=None,
        help="Test levels (L1-L6, comma-separated). Overrides profile/config.",
    )
    parser.add_argument("--viewport", default=None, help="Viewport size WxH")
    parser.add_argument("--wait", type=int, default=2000, help="Wait ms after load")
    parser.add_argument("--output", default="./test-results", help="Output directory")
    parser.add_argument(
        "--format",
        choices=["json", "markdown", "both", "junit", "sarif", "all"],
        default="both",
        help="Output report format",
    )
    parser.add_argument("--source-map", help="Source map directory")
    parser.add_argument(
        "--annotate", action="store_true", help="Generate annotated screenshot"
    )
    parser.add_argument("--rules", help="Rules directory (default: rules/)")
    parser.add_argument(
        "--profile",
        help=f"Industry profile: {', '.join(list_available_profiles()) if list_available_profiles() else 'see profiles/'}",
    )
    parser.add_argument(
        "--baseline", action="store_true", help="Save current run as baseline"
    )
    parser.add_argument(
        "--baseline-file", help="Path to baseline JSON file for regression diff"
    )
    parser.add_argument(
        "--diff-threshold",
        type=float,
        default=0.1,
        help="Layout shift threshold (ratio of max dimension)",
    )
    parser.add_argument(
        "--actions",
        help="Action sequence: 'click(#btn);wait(2000);screenshot'",
    )
    parser.add_argument(
        "--ocr-provider",
        choices=list_ocr_providers(),
        default="paddleocr-vl",
        help="OCR provider backend",
    )

    args = parser.parse_args()
    asyncio.run(run_test(args))


if __name__ == "__main__":
    main()
