"""xAI Grok LLM provider — vision and text for all environments."""
import base64
import json
import logging
import re
from dataclasses import dataclass
from io import BytesIO

import httpx
from PIL import Image

from app.utils.image import open_normalized

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

XAI_API_BASE = "https://api.x.ai/v1"


@dataclass
class LlmUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


def parse_json_response(text: str) -> dict:
    """Extract JSON from model output, tolerating markdown fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace = re.search(r"\{[\s\S]*\}", text)
        if brace:
            return json.loads(brace.group())
        raise


def encode_image_jpeg(image_bytes: bytes, max_dim: int = 1536) -> str:
    """Resize and return base64 JPEG data URL for xAI vision input."""
    img = open_normalized(image_bytes)
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _headers() -> dict[str, str]:
    if not settings.xai_api_key:
        raise ValueError("XAI_API_KEY is not configured")
    return {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "Content-Type": "application/json",
    }


def _extract_output_text(body: dict) -> str:
    if body.get("output_text"):
        return body["output_text"]
    chunks: list[str] = []
    for item in body.get("output", []):
        if isinstance(item, dict):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("type") in (
                        "output_text",
                        "text",
                    ):
                        chunks.append(part.get("text", ""))
            elif item.get("type") in ("output_text", "text"):
                chunks.append(item.get("text", ""))
    if chunks:
        return "\n".join(chunks)
    return body.get("response", "") or json.dumps(body)


def _parse_usage(body: dict, model: str) -> LlmUsage:
    usage = body.get("usage") or {}
    inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or inp + out)
    return LlmUsage(model=model, input_tokens=inp, output_tokens=out, total_tokens=total)


async def _responses_request(payload: dict, *, timeout: float = 900.0) -> tuple[str, LlmUsage]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{XAI_API_BASE}/responses",
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()
    model = payload.get("model", "unknown")
    return _extract_output_text(body), _parse_usage(body, model)


@dataclass
class AgenticResult:
    """Output of a server-side agentic Grok run (x_search / web_search tools)."""

    text: str
    citations: list[str]
    tool_trace: list[dict]
    usage: LlmUsage
    response_id: str | None = None


def _extract_tool_trace(body: dict) -> list[dict]:
    """Collect server-side tool calls (x_search/web_search) for UI display.

    xAI emits tool calls as output items like:
      {"type": "custom_tool_call", "name": "x_keyword_search",
       "input": "{\"query\": \"from:handle\", ...}", "status": "completed"}
    Older/other shapes use "<tool>_call" types with an "action" dict.
    """
    trace: list[dict] = []
    for item in body.get("output", []):
        if not isinstance(item, dict):
            continue
        item_type = item.get("type", "")
        if not item_type.endswith("_call") or item_type == "function_call":
            continue

        tool = item.get("name") or item_type.replace("_call", "")

        query = ""
        raw_input = item.get("input") or item.get("arguments")
        if isinstance(raw_input, str) and raw_input.strip():
            try:
                parsed = json.loads(raw_input)
                query = parsed.get("query") or parsed.get("q") or raw_input
            except json.JSONDecodeError:
                query = raw_input
        elif isinstance(raw_input, dict):
            query = raw_input.get("query") or raw_input.get("q") or ""
        if not query:
            action = item.get("action") or {}
            query = action.get("query") or item.get("query") or ""

        trace.append(
            {
                "tool": str(tool),
                "query": str(query)[:300],
                "status": item.get("status", "completed"),
            }
        )
    return trace


def _extract_citations(body: dict) -> list[str]:
    """Collect cited source URLs from search tool results."""
    urls: list[str] = []
    for raw in body.get("citations") or []:
        if isinstance(raw, str):
            urls.append(raw)
        elif isinstance(raw, dict) and raw.get("url"):
            urls.append(raw["url"])
    for item in body.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if not isinstance(part, dict):
                continue
            for ann in part.get("annotations") or []:
                if isinstance(ann, dict) and ann.get("url"):
                    urls.append(ann["url"])
    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique[:20]


async def generate_agentic(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    tools: list[dict] | None = None,
    max_turns: int | None = None,
    previous_response_id: str | None = None,
    timeout: float = 900.0,
) -> AgenticResult:
    """Agentic Grok run with server-side tools (x_search, web_search, code_interpreter).

    xAI executes the tool loop server-side: Grok autonomously searches X and the
    web, iterates as needed, and returns a final answer with citations. We surface
    the tool-call trace so the UI can show the investigation live.
    """
    model = model or settings.xai_text_reason
    input_msgs: list[dict] = []
    if system:
        input_msgs.append({"role": "system", "content": system})
    input_msgs.append({"role": "user", "content": prompt})
    payload: dict = {
        "model": model,
        "input": input_msgs,
        "tools": tools or [{"type": "x_search"}, {"type": "web_search"}],
    }
    if max_turns:
        payload["max_turns"] = max_turns
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{XAI_API_BASE}/responses",
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()
        body = resp.json()

    return AgenticResult(
        text=_extract_output_text(body),
        citations=_extract_citations(body),
        tool_trace=_extract_tool_trace(body),
        usage=_parse_usage(body, model),
        response_id=body.get("id"),
    )


async def generate_agentic_json(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    tools: list[dict] | None = None,
    max_turns: int | None = None,
    timeout: float = 900.0,
) -> tuple[dict, AgenticResult]:
    """Agentic run expecting a JSON payload in the final answer."""
    result = await generate_agentic(
        prompt,
        model=model,
        system=system,
        tools=tools,
        max_turns=max_turns,
        timeout=timeout,
    )
    return parse_json_response(result.text), result


async def generate_text(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    timeout: float = 600.0,
) -> tuple[str, LlmUsage]:
    """Text completion via xAI Responses API."""
    model = model or settings.xai_text_fast
    input_msgs: list[dict] = []
    if system:
        input_msgs.append({"role": "system", "content": system})
    input_msgs.append({"role": "user", "content": prompt})
    payload = {"model": model, "input": input_msgs}
    return await _responses_request(payload, timeout=timeout)


async def generate_json(
    prompt: str,
    *,
    model: str | None = None,
    system: str | None = None,
    timeout: float = 600.0,
) -> tuple[dict, LlmUsage]:
    """Text prompt expecting JSON response."""
    text, usage = await generate_text(
        prompt, model=model, system=system, timeout=timeout
    )
    return parse_json_response(text), usage


async def analyze_image_json(
    prompt: str,
    image_bytes: bytes,
    *,
    model: str | None = None,
    max_dim: int = 1536,
    detail: str = "high",
    timeout: float = 900.0,
) -> tuple[dict, LlmUsage]:
    """Vision + text prompt expecting JSON response."""
    model = model or settings.xai_vision_model
    image_url = encode_image_jpeg(image_bytes, max_dim=max_dim)
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": image_url, "detail": detail},
                    {"type": "input_text", "text": prompt},
                ],
            }
        ],
    }
    text, usage = await _responses_request(payload, timeout=timeout)
    return parse_json_response(text), usage


async def analyze_images_json(
    prompt: str,
    images: list[bytes],
    *,
    model: str | None = None,
    max_dim: int = 1536,
    detail: str = "high",
    timeout: float = 900.0,
) -> tuple[dict, LlmUsage]:
    """Multi-image vision prompt expecting JSON (e.g. cross-platform photo check)."""
    model = model or settings.xai_vision_model
    content: list[dict] = [
        {
            "type": "input_image",
            "image_url": encode_image_jpeg(img, max_dim=max_dim),
            "detail": detail,
        }
        for img in images
    ]
    content.append({"type": "input_text", "text": prompt})
    payload = {
        "model": model,
        "input": [{"role": "user", "content": content}],
    }
    text, usage = await _responses_request(payload, timeout=timeout)
    return parse_json_response(text), usage


async def health_check() -> dict:
    """Probe xAI API availability."""
    if not settings.xai_api_key:
        return {"llm": "error", "detail": "XAI_API_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{XAI_API_BASE}/models",
                headers=_headers(),
            )
            resp.raise_for_status()
            models = [
                m.get("id", m.get("name", ""))
                for m in resp.json().get("data", [])
            ]
        return {
            "llm": "ok",
            "provider": "xai",
            "models_available": len(models),
            "vision_model": settings.xai_vision_model,
            "text_fast": settings.xai_text_fast,
            "text_reason": settings.xai_text_reason,
        }
    except Exception as exc:
        return {"llm": "error", "provider": "xai", "detail": str(exc)}