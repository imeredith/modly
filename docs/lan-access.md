# LAN access over HTTP

## What works today

You can run the Python API on the computer with the GPU and call it over HTTP
from other computers on your LAN. You cannot currently open the full Modly
interface in those computers' browsers. Modly is an Electron desktop app, not a
standalone web app. Changing a bind address or adding HTTPS does not provide the
Electron services the interface needs.

The normal desktop launch deliberately starts the API on `127.0.0.1:8765`
(`electron/main/python-bridge.ts`). There is no desktop LAN-listen setting.
The following is a separate backend-only development setup, not a change to
the desktop application's listener.

## Try the API on a trusted LAN

The API has no incoming authentication layer and permits all CORS origins
(`api/main.py`). It exposes generation, settings, model/extension operations,
and workspace files. Only expose it to computers you trust, restrict the port
with the host firewall, and do not forward it through your internet router.
HTTP does not encrypt requests or files. CORS is not access control.

1. On the GPU host, complete the Python environment setup in the
   [backend README](../api/README.md). Close Modly before using its port or data
   directories for this standalone server.
2. In a terminal on that host, from the repository's `api` directory with its
   Python environment activated, run:

   ```bash
   python -m uvicorn main:app --host 0.0.0.0 --port 8765
   ```

   `0.0.0.0` listens on all IPv4 interfaces. To limit the listener to one
   interface, replace it with the host's LAN IP address.
3. Allow inbound TCP port `8765` from the intended LAN clients in your firewall.
   Find the host's LAN IP address (for example, `192.168.1.50`). From another
   computer, open `http://192.168.1.50:8765/health`; expect
   `{"status":"ok"}`. Use the real address, not `0.0.0.0`, `localhost`, or
   `127.0.0.1`, in the client URL. If it times out, check the address, firewall,
   and Wi-Fi client isolation.
4. Open `http://192.168.1.50:8765/docs` for interactive API documentation.
   This is FastAPI's API explorer, not the Modly interface. Alternatively, from
   a checkout on the client computer:

   ```bash
   python tools/modly-cli/agent.py --base-url http://192.168.1.50:8765 health
   python tools/modly-cli/agent.py --base-url http://192.168.1.50:8765 model list
   ```

Stop the server with Ctrl+C when finished. A successful health check proves API
reachability, not that a model is installed or generation is ready. Inference
runs on the server's GPU; server-side file paths refer to that computer.

### Models and data directories

A direct Uvicorn launch does not read Electron's saved settings. By default it
uses `~/.modly/models` and `~/.modly/workspace`, and `EXTENSIONS_DIR` is unset.
For your existing installation, set `MODELS_DIR`, `WORKSPACE_DIR`, and
`EXTENSIONS_DIR` in the server's environment to the actual host directories
before launching. Install/configure model extensions in the desktop app first;
a fresh API process alone does not replace desktop setup and extension
installation. Do not run two processes against the same data simultaneously.

The repository also provides `python tools/modly-cli/agent.py dev serve-api
--host 0.0.0.0 --port 8765` (run as one line from the repository root). Its
`--python`, `--models-dir`, `--workspace-dir`, and `--extensions-dir` options
allow explicit configuration; `--print-command` previews the resolved launch
without starting it. This helper starts only FastAPI, not the Electron bridge
or the desktop workflow editor.

## Why the full interface needs more work

- `electron/preload/index.ts` installs `window.electron` via Electron IPC.
  `src/App.tsx`, `src/shared/stores/appStore.ts`, and the workflow, model, and
  library screens depend on it for startup, settings, file access, extension
  management, events, and other operations. A browser has no such bridge.
- `src/index.html` restricts API connections to specific local origins in its
  content security policy. A client computer's loopback address refers to that
  client, not the GPU host. Remote URLs and host filesystem paths need an
  explicit browser transport and file-transfer design.
- Workflow and generation code calls `crypto.randomUUID()`. Browsers restrict
  that API to secure contexts; plain HTTP at a LAN IP does not qualify. A web
  version would need an HTTP-compatible UUID implementation or HTTPS. See
  [MDN's randomUUID documentation](https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID)
  and [secure contexts](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Secure_Contexts).

A browser version is feasible, but requires a browser adapter for the desktop
bridge backed by reviewed server endpoints, upload/download and event support,
configurable or same-origin API routing, a web build/serving entry point, and
authentication/access controls before sharing host file and execution features.
It also needs remote-browser tests for startup, image upload, generation,
workflow execution, and artifact download. Exposing the Vite development server
alone would not supply these features.

This assessment is based on the source and CLI launch configuration. It does
not establish end-to-end access from a second physical computer or GPU inference
on this machine.
