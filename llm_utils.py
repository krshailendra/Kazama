# llm_utils.py
import os
import json
import time
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

import openai

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")  # change if you want

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not found. Add it to .env or env vars.")

# instantiate OpenAI-compatible client for Groq
# NOTE: openai.OpenAI(...) is the modern client usage
client = openai.OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

AUTOPLAN_SYSTEM = (
    "You are an expert productivity planner. Given a high-level goal, a deadline, "
    "and the user's daily capacity (hours per day), produce a JSON array of tasks "
    "that, when executed sequentially, will achieve the goal. Output only valid JSON."
)

AUTOPLAN_INSTRUCTIONS = (
    "Input format (EXACT):\n"
    "{\n"
    '  \"goal\": \"<goal description>\",\n'
    '  \"deadline\": \"YYYY-MM-DD\",\n'
    '  \"daily_hours\": <float>,\n'
    '  \"mode\": \"study\" | \"project\" | \"practice\"\n'
    "}\n\n"
    "Output (EXACT): A JSON array of objects like:\n"
    "[\n"
    "  {\n"
    "    \"title\": \"Short task title\",\n"
    "    \"description\": \"Optional 1-2 sentence description\",\n"
    "    \"estimated_hours\": 1.5,\n"
    "    \"priority\": 3\n"
    "  }, ...\n"
    "]\n\n"
    "Constraints:\n"
    "- Prefer task chunks of 0.5–4.0 hours; keep many ~1–3 hours.\n"
    "- Total estimated hours should be realistic for the timeframe.\n"
    "- Output only JSON array (no markdown, no explanation)."
)

def build_prompt_payload(goal: str, deadline: str, daily_hours: float, mode: str = "project") -> str:
    data = {"goal": goal, "deadline": deadline, "daily_hours": float(daily_hours), "mode": mode}
    prompt = AUTOPLAN_INSTRUCTIONS + "\n\n" + json.dumps(data, ensure_ascii=False)
    return prompt

def extract_json_from_text(text: str) -> Optional[str]:
    """
    Try to locate the first JSON array in the text and return it as a string.
    """
    if not text:
        return None
    text = text.strip()
    # find first '[' and matching closing ']'
    first = text.find("[")
    last = text.rfind("]")
    if first != -1 and last != -1 and last > first:
        return text[first:last+1]
    return None

def parse_model_response_text_to_tasks(text: str) -> List[Dict]:
    """
    Given text from the model, attempt to extract JSON and parse into tasks list.
    Returns list of dicts or raises ValueError.
    """
    json_text = extract_json_from_text(text)
    if not json_text:
        # maybe the model returned a bare object, try to parse entire text
        json_text = text
    try:
        parsed = json.loads(json_text)
    except Exception as e:
        raise ValueError(f"Failed to parse JSON from model output: {e}\nRaw output:\n{text}")
    if not isinstance(parsed, list):
        raise ValueError("Parsed output is not a JSON array.")
    # validate / normalize each task
    tasks = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or ""
        if not title:
            continue
        est = item.get("estimated_hours") or item.get("hours") or item.get("estimate") or 2.0
        try:
            est = float(est)
        except Exception:
            est = 2.0
        priority = item.get("priority", 5)
        try:
            priority = int(priority)
        except Exception:
            priority = 5
        desc = item.get("description", "")
        tasks.append({
            "title": title.strip(),
            "description": desc.strip() if isinstance(desc, str) else "",
            "estimated_hours": max(0.25, est),
            "priority": max(1, min(10, priority))
        })
    return tasks

def generate_plan_with_groq(goal: str, deadline: str, daily_hours: float, mode: str = "project", max_retries: int = 2, timeout_sec: int = 30) -> List[Dict]:
    """
    Call Groq (via OpenAI-compatible client) and return validated list of task dicts.
    Each dict: title, description, estimated_hours, priority
    """
    prompt = build_prompt_payload(goal, deadline, daily_hours, mode)

    system_message = {"role": "system", "content": AUTOPLAN_SYSTEM}
    user_message = {"role": "user", "content": prompt}

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.responses.create(
            model=GROQ_MODEL,
            input=[system_message, user_message],
            temperature=0.15
        )


            
        except Exception as e:
            last_err = e
            # simple retry backoff
            time.sleep(1.5 * attempt)
            continue

        # try to extract output text robustly (different SDKs/versions may vary)
        text = None
        try:
            # Groq/OpenAI responses might expose 'output_text' property
            if hasattr(resp, "output_text") and resp.output_text:
                text = resp.output_text
            else:
                # try resp.output => list of objects containing 'content'
                out = getattr(resp, "output", None) or getattr(resp, "choices", None) or []
                # many variants: iterate and concat text pieces
                parts = []
                if isinstance(out, list):
                    for block in out:
                        # block may be a dict-like with 'content'
                        # often block.get("content") -> list of {type, text}
                        try:
                            content = block.get("content", []) if isinstance(block, dict) else []
                        except Exception:
                            content = []
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") in ("output_text","text"):
                                    parts.append(c.get("text",""))
                                elif isinstance(c, str):
                                    parts.append(c)
                        else:
                            # fallback: convert block to string
                            parts.append(str(block))
                elif isinstance(out, dict):
                    parts.append(json.dumps(out))
                if parts:
                    text = "\n".join([p for p in parts if p])
        except Exception:
            text = None

        # Final fallback to raw resp string
        if not text:
            try:
                text = str(resp)
            except Exception:
                text = None

        if not text:
            last_err = RuntimeError("Empty response from model")
            time.sleep(1.5 * attempt)
            continue

        # attempt parse
        try:
            tasks = parse_model_response_text_to_tasks(text)
            if not tasks:
                raise ValueError("Model returned empty task list")
            return tasks
        except Exception as e:
            # if parse failed, retry once more; but capture last error
            last_err = e
            time.sleep(1.5 * attempt)
            continue

    raise RuntimeError(f"LLM autoplan failed after {max_retries} attempts. Last error: {last_err}")
