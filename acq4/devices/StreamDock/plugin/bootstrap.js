/*
ACQ4 Stream Dock plugin bootstrap.

VSD Craft launches this with

    -port <port> -pluginUUID <uuid> -registerEvent <event> -info <json>

and it does exactly two things: publish those arguments to ws-meta.json, and stay alive so
that VSD Craft keeps the plugin loaded. ACQ4 connects to the same websocket server as a
second client and does all the real work; that keeps every dependency (PyQt, rendering,
device state) in the one interpreter that already has them.

The -info payload is the only authoritative source of panel geometry -- willAppear reports
a key's own column and row but never the panel dimensions -- so it is republished verbatim.

VSD Craft hands out a fresh port and pluginUUID on every restart, and restarts routinely
(during its own startup, and whenever a profile is rewritten), so ACQ4 re-reads this file
before every connection attempt and uses its mtime to tell a new session from a stale one.
*/

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("-")) {
      continue;
    }
    const value = argv[i + 1];
    if (typeof value === "undefined" || value.startsWith("-")) {
      out[key] = "";
      continue;
    }
    out[key] = value;
    i += 1;
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = args["-port"];
  const pluginUUID = args["-pluginUUID"] || "";
  const registerEvent = args["-registerEvent"] || "";

  let info = null;
  try {
    info = args["-info"] ? JSON.parse(args["-info"]) : null;
  } catch (err) {
    console.error(`[acq4] could not parse -info: ${err.message}`);
  }

  if (!port) {
    console.error("[acq4] missing -port argument");
    process.exit(1);
  }

  const wsAddress = `ws://127.0.0.1:${port}`;
  const metaFile = process.env.ACQ4_WS_META_FILE
    ? path.resolve(process.env.ACQ4_WS_META_FILE)
    : path.join(__dirname, "ws-meta.json");

  // Write to a sibling temp file and rename, so ACQ4 -- which polls this file's mtime and
  // may read it at any moment -- never sees a half-written document.
  const tmpFile = `${metaFile}.tmp`;
  fs.writeFileSync(
    tmpFile,
    JSON.stringify(
      {
        ws: wsAddress,
        pluginUUID,
        registerEvent,
        info,
        pid: process.pid,
        argv: process.argv.slice(2),
      },
      null,
      2
    ) + "\n",
    "utf8"
  );
  fs.renameSync(tmpFile, metaFile);

  console.log(`[acq4] published websocket address ${wsAddress} to ${metaFile}`);

  // Keep the process alive; ACQ4 connects separately.
  setInterval(() => {}, 60000);
}

main();
