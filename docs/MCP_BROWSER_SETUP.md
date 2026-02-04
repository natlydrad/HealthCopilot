# MCP Browser Tools Setup (Console Diagnostic)

To let the AI inspect your browser console (e.g. for the `📊 [diagnostic]` nutrition logs), enable MCP browser tools.

## Option A: Cursor IDE Browser (Built-in)

1. **Open Simple Browser in Cursor**
   - `View` → `Open View` → `Simple Browser`
   - Or: `Cmd+Shift+P` → "Simple Browser: Show"
   - Navigate to your dashboard URL (e.g. `http://localhost:5173` or production)

2. **Ensure the extension is active**
   - The "Cursor IDE Browser Automation" extension should be enabled (Settings → Extensions)
   - If you see "No browser view available", open the Simple Browser first

3. **Use the browser**
   - With the Simple Browser open and focused, the MCP tools (browser_snapshot, get console logs, etc.) should become available to the agent

## Option B: Browser-Tools MCP (External) — Installed

This project has Browser-Tools MCP configured in [`.cursor/mcp.json`](../.cursor/mcp.json).

### 1. Install the Chrome extension

Either:

**A) Download from releases (recommended)**
- [BrowserTools 1.2.0 extension zip](https://github.com/AgentDeskAI/browser-tools-mcp/releases/download/v1.2.0/BrowserTools-1.2.0-extension.zip)
- Unzip, then Chrome → `chrome://extensions/` → Developer mode → Load unpacked → select the unzipped folder

**B) Use the cloned repo**
- The repo is at `browser-tools-mcp/` (in .gitignore)
- Chrome → `chrome://extensions/` → Developer mode → Load unpacked → select `browser-tools-mcp/chrome-extension`

### 2. Run the browser-tools-server (required)

In a **separate terminal**, run:

```bash
npx @agentdeskai/browser-tools-server@latest
```

Keep this running. It's the middleware that gathers logs from the Chrome extension.

### 3. Restart Cursor

Restart Cursor so it picks up the MCP config. The `browser-tools` server will start automatically.

### 4. Use it

- Open your dashboard in Chrome
- Open DevTools (F12) → find the **BrowserToolsMCP** panel
- The AI can now use "Get Console Logs" to capture output including `📊 [diagnostic]` lines

## Nutrition diagnostic

When the dashboard fetches ingredients, the console shows:
```
📊 [diagnostic] first ingredient keys: [...] nutrition: array[18] | missing | ...
```

- `array[N]` = nutrition present with N nutrients
- `missing` = API returned no nutrition field
