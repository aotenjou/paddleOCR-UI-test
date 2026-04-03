# PaddleOCR UI Test Skill

> AI-driven UI testing skill combining PaddleOCR screenshot analysis with DOM/Accessibility Tree cross-validation.

## Installation

### Claude Code

Place this skill in your skills directory:

```bash
# Clone into your skills directory
git clone https://github.com/PaddlePaddle/paddleocr-ui-test.git
cp -r paddleocr-ui-test/skills/paddleocr-ui-test ~/.agents/skills/paddleocr-ui-test
```

### Manual

Copy the `paddleocr-ui-test` directory to one of:
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

## License

Apache-2.0
