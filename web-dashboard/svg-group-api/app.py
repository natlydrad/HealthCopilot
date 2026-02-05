"""
Standalone API for AI-powered SVG grouping (e.g. rigging).
Single route: POST /group-svg — accepts element list, returns suggested groups from GPT.
"""

import json
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# #region agent log
DEBUG_LOG = "/Users/natalieradu/Desktop/HealthCopilot/.cursor/debug.log"
def _agent_log(msg, data, hypothesis_id="server500"):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(json.dumps({"location": "svg-group-api/app.py", "message": msg, "data": data, "hypothesisId": hypothesis_id}) + "\n")
    except Exception:
        pass
# #endregion

app = Flask(__name__)
CORS(app)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", "5002"))


def build_element_description(elements):
    """Turn element list into a short text description for GPT."""
    lines = []
    for i, el in enumerate(elements):
        t = el.get("type", "?")
        if t == "circle":
            lines.append(f"{i}: circle cx={el.get('cx')} cy={el.get('cy')} r={el.get('r')} fill={el.get('fill', '')}")
        elif t == "rect":
            lines.append(f"{i}: rect x={el.get('x')} y={el.get('y')} w={el.get('width')} h={el.get('height')} fill={el.get('fill', '')}")
        elif t == "path":
            d = (el.get("d") or "")[:80]
            lines.append(f"{i}: path d={d}... stroke={el.get('stroke', '')}")
        else:
            lines.append(f"{i}: {t} {json.dumps(el)[:60]}")
    return "\n".join(lines)


SYSTEM_PROMPT = """You suggest logical rigging groups for an SVG character (e.g. a frog or animal).
Given a list of SVG elements (circles, rects, paths) with index, position, size, and color, assign each element to exactly one group.

Return ONLY valid JSON: a single object. Keys are group names (use camelCase, e.g. body, head, leftEye, rightEye, leftLeg, rightLeg, mouth).
Values are arrays of 0-based element indices. Every index from 0 to N-1 must appear in exactly one group.

Use position (center vs top vs bottom), size (large vs small), and color to infer roles:
- Large central green shape = body
- Smaller circles above = eyes, pupils
- Rects at bottom = legs/feet
- Dark small circles = pupils, mouth
- Similar-sized pairs = left/right (e.g. leftEye, rightEye)

Output nothing else, no markdown, no explanation — only the JSON object."""


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/group-svg", methods=["POST"])
def group_svg():
    try:
        # #region agent log
        _agent_log("group_svg entry", {"content_type": request.content_type, "has_openai_key": bool(OPENAI_API_KEY)}, "H1")
        # #endregion
        if not OPENAI_API_KEY:
            return jsonify({"error": "OPENAI_API_KEY not set. Add it to web-dashboard/svg-group-api/.env"}), 500

        body = request.get_json(silent=True)
        # #region agent log
        _agent_log("after get_json", {"body_is_none": body is None, "has_elements": body and "elements" in body if body else False}, "H2")
        # #endregion
        if not body or "elements" not in body:
            return jsonify({"error": "Missing 'elements' array"}), 400

        elements = body["elements"]
        if not elements:
            return jsonify({"error": "elements array is empty"}), 400

        text = build_element_description(elements)
        user_message = f"Elements (index: type attrs):\n{text}"

        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
        # Strip markdown code block if present
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        groups = json.loads(content)
        if not isinstance(groups, dict):
            return jsonify({"error": "Invalid response: not an object"}), 502
        n = len(elements)
        seen = set()
        for name, indices in groups.items():
            if not isinstance(indices, list):
                return jsonify({"error": f"Group '{name}' value is not an array"}), 502
            for i in indices:
                if not isinstance(i, int) or i < 0 or i >= n:
                    return jsonify({"error": f"Invalid index {i} in group '{name}'"}), 502
                if i in seen:
                    return jsonify({"error": f"Index {i} appears in more than one group"}), 502
                seen.add(i)
        if len(seen) != n:
            missing = sorted(set(range(n)) - seen)
            groups["other"] = groups.get("other", []) + missing
        return jsonify({"groups": groups})
    except json.JSONDecodeError as e:
        # #region agent log
        _agent_log("JSONDecodeError", {"error": str(e)}, "H4")
        # #endregion
        return jsonify({"error": f"Invalid JSON from model: {e}"}), 502
    except Exception as e:
        # #region agent log
        _agent_log("Exception", {"type": type(e).__name__, "error": str(e)}, "H3")
        # #endregion
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
