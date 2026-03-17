#!/usr/bin/env node
/**
 * contextmesh-mcp — npx entrypoint
 * Launches the Python MCP server via stdio.
 *
 * Usage (in mcp.json / cursor settings):
 *   {
 *     "contextmesh": {
 *       "command": "npx",
 *       "args": ["contextmesh-mcp"],
 *       "env": { "CM_KEY": "cm_live_..." }
 *     }
 *   }
 */

const { spawn } = require('child_process');
const path      = require('path');
const fs        = require('fs');

const pythonServer = path.join(__dirname, '..', 'mcp_server.py');

if (!fs.existsSync(pythonServer)) {
  process.stderr.write(`[contextmesh-mcp] ERROR: mcp_server.py not found at ${pythonServer}\n`);
  process.exit(1);
}

// Prefer python3, fall back to python
const python = process.platform === 'win32' ? 'python' : 'python3';

const child = spawn(python, [pythonServer], {
  stdio: 'inherit',
  env:   process.env,
});

child.on('error', (err) => {
  process.stderr.write(`[contextmesh-mcp] Failed to start: ${err.message}\n`);
  if (err.code === 'ENOENT') {
    process.stderr.write('[contextmesh-mcp] Python 3 not found. Install from https://python.org\n');
  }
  process.exit(1);
});

child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});

// Forward signals
['SIGINT', 'SIGTERM', 'SIGHUP'].forEach(sig => {
  process.on(sig, () => child.kill(sig));
});
