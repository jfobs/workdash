from __future__ import annotations

import json
import os

from openai import OpenAI


def ai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def draft_narrative(context: dict, enabled: bool = True) -> str:
    if not enabled:
        return "AI narrative disabled."
    if not ai_available():
        return "OPENAI_API_KEY not set; provide manual narrative text."

    client = OpenAI()
    prompt = (
        "Draft concise lease audit workpaper narrative in professional accounting tone. "
        "Do not invent numbers; use only provided context. "
        "Return JSON with key 'narrative'. Context: "
        + json.dumps(context)
    )
    response = client.responses.create(
        model="gpt-5.2",
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    try:
        payload = json.loads(response.output_text)
        return payload.get("narrative", "")
    except json.JSONDecodeError:
        return response.output_text
