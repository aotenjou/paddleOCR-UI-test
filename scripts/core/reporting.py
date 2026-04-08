from __future__ import annotations

import json
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .models import coerce_issues


def summarize_issues(results: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    summary = {"total": 0, "error": 0, "warning": 0, "info": 0}
    for result in results:
        summary["total"] += 1
        severity = result.get("severity", "info")
        if severity in summary:
            summary[severity] += 1
    return summary


class ReportWriter:
    """Generate report artifacts in multiple formats."""

    def __init__(
        self,
        *,
        url: str,
        results: Iterable[Dict[str, Any]],
        output_dir: str,
        image_size: tuple[int, int],
        duration: float,
        metadata: Optional[Dict[str, Any]] = None,
        snapshots: Optional[Dict[str, Any]] = None,
    ):
        self.url = url
        self.results = coerce_issues(results)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_size = image_size
        self.duration = duration
        self.metadata = metadata or {}
        self.snapshots = snapshots or {}
        self._payload: Optional[Dict[str, Any]] = None

    def summary(self) -> Dict[str, int]:
        return summarize_issues(self.results)

    def build_payload(self) -> Dict[str, Any]:
        if self._payload is None:
            summary = self.summary()
            self._payload = {
                "schema_version": "1.1",
                "test_id": f"ui-test-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
                "url": self.url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "image_size": list(self.image_size),
                "duration_seconds": round(self.duration, 2),
                "metadata": self.metadata,
                "summary": {
                    "total_checks": summary["total"],
                    "passed": max(summary["total"] - summary["error"] - summary["warning"], 0),
                    "failed": summary["error"],
                    "warnings": summary["warning"],
                    "info": summary["info"],
                },
                "results": self.results,
                "snapshots": self.snapshots,
            }
        return self._payload

    def generate_json(self) -> str:
        path = self.output_dir / "report.json"
        path.write_text(
            json.dumps(self.build_payload(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(path)

    def generate_markdown(self) -> str:
        payload = self.build_payload()
        summary = payload["summary"]
        results = payload["results"]
        lines = [
            f"# UI Test Report — {payload['url']}",
            "",
            "| Item | Value |",
            "|------|-------|",
            f"| URL | {payload['url']} |",
            f"| Time | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |",
            f"| Image Size | {payload['image_size'][0]}x{payload['image_size'][1]} |",
            f"| Duration | {payload['duration_seconds']:.1f}s |",
            f"| Checks | {summary['total_checks']} total (✅ {summary['passed']} ❌ {summary['failed']} ⚠️ {summary['warnings']}) |",
            "",
        ]

        grouped = {
            "error": [result for result in results if result.get("severity") == "error"],
            "warning": [result for result in results if result.get("severity") == "warning"],
            "info": [result for result in results if result.get("severity") == "info"],
        }
        headings = {
            "error": "## Errors",
            "warning": "## Warnings",
            "info": "## Info",
        }

        if not results:
            lines.append("## All checks passed")
        for severity in ("error", "warning", "info"):
            findings = grouped[severity]
            if not findings:
                continue
            lines.extend([headings[severity], ""])
            for idx, finding in enumerate(findings, start=1):
                lines.append(
                    f"**{idx}. [{finding.get('level', '?')}] {finding.get('type', '?')}** — {finding.get('element', '')}"
                )
                lines.append(f"- Expected: `{finding.get('expected', '')}`")
                lines.append(f"- Actual: `{finding.get('actual', '')}`")
                if finding.get("suggestion"):
                    lines.append(f"- Suggestion: {finding['suggestion']}")
                if finding.get("source_location", {}).get("file"):
                    location = finding["source_location"]
                    lines.append(
                        f"- Source: `{location.get('file')}:{location.get('line', '?')}`"
                    )
                lines.append("")

        path = self.output_dir / "report.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    def generate_junit(self) -> str:
        payload = self.build_payload()
        summary = payload["summary"]
        results = payload["results"]
        suite = ET.Element(
            "testsuite",
            name="paddleocr-ui-test",
            tests=str(max(len(results), 1)),
            failures=str(summary["failed"]),
            time=f"{payload['duration_seconds']:.3f}",
        )

        if not results:
            testcase = ET.SubElement(suite, "testcase", classname="ui", name="ui_test")
            ET.SubElement(testcase, "system-out").text = "All checks passed"
        else:
            for index, result in enumerate(results, start=1):
                testcase = ET.SubElement(
                    suite,
                    "testcase",
                    classname=f"ui.{result.get('level', 'unknown').lower()}",
                    name=f"{index}_{result.get('type', 'issue')}",
                    time="0",
                )
                text = (
                    f"Expected: {result.get('expected', '')}\n"
                    f"Actual: {result.get('actual', '')}\n"
                    f"Suggestion: {result.get('suggestion', '')}"
                )
                if result.get("severity") == "error":
                    failure = ET.SubElement(
                        testcase,
                        "failure",
                        message=result.get("type", "issue"),
                    )
                    failure.text = text
                else:
                    ET.SubElement(testcase, "system-out").text = text

        path = self.output_dir / "report.junit.xml"
        ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
        return str(path)

    def generate_sarif(self) -> str:
        payload = self.build_payload()
        rules = []
        rule_index: Dict[str, int] = {}
        results = []

        for finding in payload["results"]:
            rule_id = f"{finding.get('level', 'L?')}/{finding.get('type', 'issue')}"
            if rule_id not in rule_index:
                rule_index[rule_id] = len(rules)
                rules.append(
                    {
                        "id": rule_id,
                        "name": finding.get("type", "issue"),
                        "shortDescription": {"text": finding.get("type", "issue")},
                        "help": {"text": finding.get("suggestion", "") or finding.get("actual", "")},
                        "properties": {"problem.severity": finding.get("severity", "warning")},
                    }
                )

            location_payload = []
            source_location = finding.get("source_location", {})
            if source_location.get("file"):
                region: Dict[str, Any] = {}
                if source_location.get("line"):
                    region["startLine"] = int(source_location["line"])
                location_payload.append(
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": source_location["file"]},
                            "region": region,
                        }
                    }
                )

            results.append(
                {
                    "ruleId": rule_id,
                    "level": "error" if finding.get("severity") == "error" else "warning",
                    "message": {"text": finding.get("actual", "") or finding.get("type", "issue")},
                    "locations": location_payload,
                    "properties": {"level": finding.get("level", "")},
                }
            )

        payload = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "paddleocr-ui-test",
                            "informationUri": "https://github.com/",
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }
        path = self.output_dir / "report.sarif.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def write_selected(self, format_name: str) -> Dict[str, str]:
        format_name = format_name or "both"
        outputs: Dict[str, str] = {}
        if format_name in {"json", "both", "all"}:
            outputs["json"] = self.generate_json()
        if format_name in {"markdown", "both", "all"}:
            outputs["markdown"] = self.generate_markdown()
        if format_name in {"junit", "all"}:
            outputs["junit"] = self.generate_junit()
        if format_name in {"sarif", "all"}:
            outputs["sarif"] = self.generate_sarif()
        return outputs
