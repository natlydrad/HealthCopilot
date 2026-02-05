# SVG Group API

Small Flask API that uses GPT to suggest logical rigging groups for an SVG character (e.g. frog) drawn in the canvas tool.

## Setup

```bash
cd web-dashboard/svg-group-api
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

## Run

```bash
python app.py
```

Runs on port 5002 by default (or set `PORT` in `.env`).

## Usage

With the dashboard dev server running (`npm run dev` in `web-dashboard/dashboard`), open `http://localhost:5173/5js_test.html`. The "Group with AI" button sends the current shapes to this API; the response is used to wrap elements in `<g id="groupName">` when exporting SVG.

## Endpoints

- `GET /health` — returns `{ "ok": true }`
- `POST /group-svg` — body: `{ "elements": [ { "type": "circle", "cx", "cy", "r", "fill" }, ... ] }`. Returns `{ "groups": { "body": [0, 1], "leftEye": [2], ... } }`.
