/*
ACQ4 Stream Dock plugin bootstrap.

VSD Craft launches this with

    -port <port> -pluginUUID <uuid> -registerEvent <event> -info <json>

and it does three things: clear any bridge left over from a previous plugin session,
publish those arguments to ws-meta.json, and stay alive so that VSD Craft keeps the plugin
loaded. ACQ4 connects to the same websocket server as a second client and does all the real
work; that keeps every dependency (PyQt, rendering, device state) in the one interpreter
that already has them.

The -info payload is the only authoritative source of panel geometry -- willAppear reports
a key's own column and row but never the panel dimensions -- so it is republished verbatim.

VSD Craft hands out a fresh port and pluginUUID on every restart, and restarts routinely
(during its own startup, and whenever a profile is rewritten), so ACQ4 re-reads this file
before every connection attempt and uses its mtime to tell a new session from a stale one.

Clearing predecessors
---------------------
VSD Craft does not kill the plugin processes it started: after a few of its restarts
several bridges are alive at once, all of them having written this same ws-meta.json at
launch. Whichever wrote last owns the file, and nothing deletes it when its own process
dies -- so ACQ4 could read a port and pluginUUID belonging to a session VSD Craft had long
forgotten. That failure is silent and total: the websocket still opens, because the port
belongs to VSD Craft rather than to the plugin, and registerPlugin is accepted, but no
willAppear ever arrives, so ACQ4 binds no keys and every image it draws is dropped. The
panel stays blank with nothing in any log.

So the new bridge reaps the old ones before publishing, which makes the newest bridge the
only bridge and this file unambiguously its own. ACQ4 checks that invariant from its side
too (profile.meta_problem), because this can still fail -- and when it does, the reason is
recorded in the file rather than only written to a console nobody reads.
*/

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

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

// Node has no process enumeration of its own, and the command line is the only place a
// bridge's identity appears, so this goes through PowerShell's CIM provider.
function powershell(script) {
  return execFileSync(
    "powershell.exe",
    ["-NoProfile", "-NonInteractive", "-Command", script],
    { encoding: "utf8", timeout: 20000, windowsHide: true }
  );
}

// Every live bridge but this one. Matched on the plugin folder *and* bootstrap.js, so no
// other plugin's node process -- and not VSD Craft itself -- can be caught by it.
function findPredecessors() {
  const marker = path.basename(__dirname);
  const script =
    "Get-CimInstance Win32_Process | Where-Object { " +
    `$_.CommandLine -like '*${marker}*' -and $_.CommandLine -like '*bootstrap.js*'` +
    " } | ForEach-Object { $_.ProcessId }";
  return powershell(script)
    .split(/\s+/)
    .map((token) => parseInt(token, 10))
    .filter((pid) => Number.isInteger(pid) && pid !== process.pid);
}

function clearPredecessors() {
  const outcome = { reaped: [], errors: [] };

  let pids;
  try {
    pids = findPredecessors();
  } catch (err) {
    outcome.errors.push(`could not enumerate bridge processes: ${err.message}`);
    return outcome;
  }

  for (const pid of pids) {
    try {
      execFileSync("taskkill", ["/F", "/PID", String(pid)], {
        encoding: "utf8",
        timeout: 10000,
        windowsHide: true,
        // Capture taskkill's own stderr rather than letting "process not found" leak
        // into VSD Craft's console; the already-gone case is handled just below.
        stdio: ["ignore", "pipe", "pipe"],
      });
      outcome.reaped.push(pid);
    } catch (err) {
      // Already gone between the listing and the kill is the common case and not worth
      // reporting as a fault; anything else is.
      if (err.status === 128) {
        outcome.reaped.push(pid);
      } else {
        outcome.errors.push(`could not kill bridge pid ${pid}: ${err.message}`);
      }
    }
  }
  return outcome;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const port = args["-port"];
  const pluginUUID = args["-pluginUUID"] || "";
  const registerEvent = args["-registerEvent"] || "";

  let info = null;
  let infoError = null;
  try {
    info = args["-info"] ? JSON.parse(args["-info"]) : null;
  } catch (err) {
    infoError = `could not parse -info: ${err.message}`;
    console.error(`[acq4] ${infoError}`);
  }

  if (!port) {
    console.error("[acq4] missing -port argument");
    process.exit(1);
  }

  // Before publishing, so a predecessor cannot overwrite what we are about to write.
  const cleanup = clearPredecessors();
  for (const pid of cleanup.reaped) {
    console.log(`[acq4] cleared stale bridge process ${pid}`);
  }
  for (const message of cleanup.errors) {
    console.error(`[acq4] ${message}`);
  }
  if (infoError) {
    cleanup.errors.push(infoError);
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
        startedAt: Date.now() / 1000,
        reaped: cleanup.reaped,
        // ACQ4 logs these: a bridge it cannot verify is the one fault that otherwise
        // leaves the panel blank in silence.
        errors: cleanup.errors,
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
