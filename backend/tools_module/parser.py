import json
import re
from typing import List, Dict, Any


def extract_balanced_json_objects(text: str) -> List[dict]:
    """
    Extracts all valid top-level JSON objects from text by tracking brace depth.
    Handles nested braces, strings, escapes cleanly.
    """
    objects = []
    i = 0
    n = len(text)

    while i < n:
        if text[i] == '{':
            start = i
            depth = 0
            in_string = False
            escape = False

            for j in range(start, n):
                char = text[j]

                if escape:
                    escape = False
                    continue

                if char == '\\' and in_string:
                    escape = True
                    continue

                if char == '"':
                    in_string = not in_string
                    continue

                if not in_string:
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            candidate = text[start:j + 1]
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, dict):
                                    objects.append(parsed)
                                    i = j
                            except json.JSONDecodeError:
                                pass
                            break
        i += 1

    return objects


def parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """
    Extracts tool call JSON objects from LLM output.
    Supports markdown code fences (```json ... ```) as well as raw JSON blocks.
    Matches objects with a "tool" key.
    """
    if not text:
        return []

    results = []

    # 1. Search inside fenced code blocks: ```(?:json)? ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in fence_pattern.finditer(text):
        snippet = match.group(1).strip()
        parsed_objs = extract_balanced_json_objects(snippet)
        for obj in parsed_objs:
            if "tool" in obj and isinstance(obj["tool"], str):
                results.append({
                    "tool": obj["tool"].strip(),
                    "params": obj.get("params", {}) if isinstance(obj.get("params"), dict) else {}
                })

    if results:
        return results

    # 2. Search entire text for balanced JSON objects
    parsed_objs = extract_balanced_json_objects(text)
    for obj in parsed_objs:
        if "tool" in obj and isinstance(obj["tool"], str):
            results.append({
                "tool": obj["tool"].strip(),
                "params": obj.get("params", {}) if isinstance(obj.get("params"), dict) else {}
            })

    return results
