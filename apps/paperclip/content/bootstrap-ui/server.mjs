import http from "node:http";
import https from "node:https";
import net from "node:net";
import { readFile } from "node:fs/promises";

const port = Number(process.env.PORT || 8080);
const target = new URL(process.env.PAPERCLIP_INTERNAL_URL || "http://paperclip:3100");
const inviteFile = process.env.PAPERCLIP_BOOTSTRAP_INVITE_PATH || "/paperclip/instances/default/bootstrap-invite-url.txt";
const statusPath = "/__lazycat/bootstrap-status";
const invitePattern = /^https?:\/\/\S+\/invite\/pcp_bootstrap_[A-Za-z0-9]+$/;

async function readInviteUrl() {
  const value = (await readFile(inviteFile, "utf8").catch(() => "")).trim();
  return invitePattern.test(value) ? value : "";
}

async function getPaperclipHealth() {
  const inviteUrl = await readInviteUrl();
  try {
    const response = await fetch(new URL("/api/health", target), {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return {
        reachable: false,
        bootstrapPending: true,
        bootstrapInviteActive: false,
        inviteUrl,
      };
    }
    const data = await response.json();
    return {
      reachable: true,
      bootstrapPending: data.bootstrapStatus === "bootstrap_pending",
      bootstrapInviteActive: Boolean(data.bootstrapInviteActive),
      inviteUrl,
    };
  } catch {
    return {
      reachable: false,
      bootstrapPending: true,
      bootstrapInviteActive: false,
      inviteUrl,
    };
  }
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function bootstrapPage(initialState) {
  const showInvite = initialState.inviteUrl && initialState.bootstrapInviteActive;
  const inviteBlock = showInvite
    ? `<a class="primary" href="${escapeHtml(initialState.inviteUrl)}">Open bootstrap invite</a>
       <pre id="invite-url">${escapeHtml(initialState.inviteUrl)}</pre>`
    : `<div class="hint"><span class="spinner"></span>Initializing Paperclip — running first-time setup in the background. This may take 20–30 seconds.</div>
       <pre id="invite-url">Waiting for bootstrap invite...</pre>
       <div class="elapsed" id="elapsed"></div>`;

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Paperclip Setup</title>
  <style>
    :root { color-scheme: light; --bg:#f4efe8; --panel:#fffaf3; --line:#dbcdb8; --text:#241d16; --muted:#74695b; --accent:#b85c38; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; font-family: ui-sans-serif, system-ui, sans-serif; background: radial-gradient(circle at top, #fff8ef, var(--bg)); color:var(--text); }
    .wrap { max-width:760px; margin:0 auto; padding:48px 20px; }
    .panel { background:rgba(255,250,243,.92); border:1px solid var(--line); border-radius:24px; padding:28px; box-shadow:0 20px 50px rgba(36,29,22,.08); }
    .eyebrow { font-size:12px; letter-spacing:.18em; text-transform:uppercase; color:var(--muted); }
    h1 { margin:10px 0 12px; font-size:34px; line-height:1.1; }
    p { margin:0; color:var(--muted); line-height:1.6; }
    .stack { display:grid; gap:16px; margin-top:24px; }
    .primary { display:inline-flex; align-items:center; justify-content:center; min-height:48px; padding:0 18px; border-radius:999px; background:var(--accent); color:#fff; text-decoration:none; font-weight:600; }
    pre { margin:0; padding:16px; border-radius:18px; background:#231f1c; color:#f8efe4; overflow:auto; white-space:pre-wrap; word-break:break-all; }
    .hint { padding:16px; border-radius:18px; background:#f6ead8; color:#5d4f40; border:1px solid #e3d4be; }
    .footer { margin-top:18px; font-size:13px; color:var(--muted); }
    .spinner { display:inline-block; width:14px; height:14px; border:2px solid #c9b49a; border-top-color:#b85c38; border-radius:50%; animation:spin .8s linear infinite; margin-right:8px; vertical-align:middle; }
    @keyframes spin { to { transform:rotate(360deg); } }
    .elapsed { font-size:12px; color:var(--muted); margin-top:6px; }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="panel">
      <div class="eyebrow">LazyCat Guided Setup</div>
      <h1>Paperclip is preparing the first admin invite</h1>
      <p>Bootstrap runs automatically in the background. As soon as the first CEO invite URL is ready, this page will surface it here and you can open it directly.</p>
      <div class="stack" id="invite-block">${inviteBlock}</div>
      <div class="footer">Once the first admin is created, this page will hand traffic back to Paperclip automatically. Already have an account? <a href="/login" style="color:var(--accent)">Sign in →</a></div>
    </section>
  </main>
  <script>
    async function refresh() {
      try {
        const res = await fetch("${statusPath}", { headers: { Accept: "application/json" } });
        const state = await res.json();
        if (!state.bootstrapPending) {
          window.location.reload();
          return;
        }
        const block = document.getElementById("invite-block");
        if (state.inviteUrl && state.bootstrapInviteActive) {
          block.innerHTML = '<a class="primary" href="' + state.inviteUrl + '">Open bootstrap invite</a><pre id="invite-url"></pre>';
          document.getElementById("invite-url").textContent = state.inviteUrl;
        }
      } catch {}
    }
    const start = Date.now();
    function updateElapsed() {
      const el = document.getElementById("elapsed");
      if (el) el.textContent = "Running for " + Math.floor((Date.now() - start) / 1000) + "s…";
    }
    setInterval(refresh, 2000);
    setInterval(updateElapsed, 1000);
    refresh();
  </script>
</body>
</html>`;
}

function proxyHttp(req, res) {
  const isHttps = target.protocol === "https:";
  const requestImpl = isHttps ? https.request : http.request;
  const forwardedProto = req.headers["x-forwarded-proto"] || "https";
  const forwardedHost = req.headers["x-forwarded-host"] || req.headers.host || "";
  const upstreamReq = requestImpl(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (isHttps ? 443 : 80),
      method: req.method,
      path: req.url,
      headers: {
        ...req.headers,
        host: req.headers.host,
        "x-forwarded-host": forwardedHost,
        "x-forwarded-proto": forwardedProto,
      },
    },
    (upstreamRes) => {
      res.writeHead(upstreamRes.statusCode || 502, upstreamRes.headers);
      upstreamRes.pipe(res);
    },
  );
  upstreamReq.on("error", (error) => {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: `proxy failed: ${error.message}` }));
  });
  req.pipe(upstreamReq);
}

function proxyUpgrade(req, socket, head) {
  const upstream = net.connect(Number(target.port || 80), target.hostname, () => {
    upstream.write(`${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`);
    for (let i = 0; i < req.rawHeaders.length; i += 2) {
      const key = req.rawHeaders[i];
      const value = req.rawHeaders[i + 1];
      upstream.write(`${key}: ${value}\r\n`);
    }
    upstream.write("\r\n");
    if (head.length > 0) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.on("error", () => socket.destroy());
}

const server = http.createServer(async (req, res) => {
  const state = await getPaperclipHealth();
  if (req.url === statusPath) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(state));
    return;
  }
  if (state.bootstrapPending && (req.url === "/" || req.url?.startsWith("/?"))) {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
    res.end(bootstrapPage(state));
    return;
  }
  proxyHttp(req, res);
});

server.on("upgrade", proxyUpgrade);
server.listen(port, "0.0.0.0");
