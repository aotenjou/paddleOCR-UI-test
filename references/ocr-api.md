# PaddleOCR API Configuration

## API Endpoint

Default endpoint (SiliconFlow):

```
https://api.siliconflow.cn/v1/chat/completions
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PADDLEOCR_API_KEY` | API key for authentication | (required) |
| `SILICONFLOW_API_KEY` | Fallback API key | (required) |
| `PADDLEOCR_MODEL` | Model identifier | `PaddlePaddle/PaddleOCR-VL-1.5` |
| `PADDLEOCR_API_URL` | API endpoint URL | `https://api.siliconflow.cn/v1/chat/completions` |

## Supported Models

| Model | Description | Best For |
|-------|-------------|----------|
| `PaddlePaddle/PaddleOCR-VL-1.5` | Latest PaddleOCR vision-language model | General OCR, Chinese + English |
| `PaddlePaddle/PaddleOCR-VL-1.0` | Previous version | Legacy compatibility |

## Request Format

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key="your-api-key",
    base_url="https://api.siliconflow.cn/v1/chat/completions"
)

response = await client.chat.completions.create(
    model="PaddlePaddle/PaddleOCR-VL-1.5",
    messages=[
        {"role": "system", "content": "Extract all text with coordinates."},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64,..."
            }}
        ]}
    ],
    max_tokens=4000,
    temperature=0,
)
```

## Response Format

```json
{
  "texts": [
    {
      "text": "识别的文字",
      "box": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
    }
  ]
}
```

## Rate Limits

| Tier | Requests/min | Notes |
|------|-------------|-------|
| Free | 10 | Suitable for development |
| Paid | 100+ | Contact SiliconFlow for higher limits |

## Getting API Key

1. Visit https://siliconflow.cn
2. Register an account
3. Generate API key from dashboard
4. Set as environment variable: `export SILICONFLOW_API_KEY="your-key"`
