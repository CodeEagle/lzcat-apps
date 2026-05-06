import http from "node:http";
import { Readable } from "node:stream";

const PORT = 8787;
const allowedHosts = new Set(["github.com", "raw.githubusercontent.com"]);
const UPSTREAM_TIMEOUT_MS = 5 * 60 * 1000;

function setCorsHeaders(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization, Git-Protocol, Accept");
  res.setHeader("Access-Control-Expose-Headers", "*");
}

function isAllowedHost(hostname) {
  return Array.from(allowedHosts).some((host) => hostname === host || hostname.endsWith(`.${host}`));
}

function collectBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function createAbortSignal(timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new Error("Upstream request timed out")), timeoutMs);
  return {
    signal: controller.signal,
    clear() {
      clearTimeout(timeout);
    },
  };
}

const server = http.createServer(async (req, res) => {
  setCorsHeaders(res);

  if (req.method === "OPTIONS") {
    res.writeHead(200);
    res.end();
    return;
  }

  try {
    const requestUrl = new URL(req.url, `http://${req.headers.host}`);
    if (requestUrl.pathname !== "/api/proxy") {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Not found" }));
      return;
    }

    const target = requestUrl.searchParams.get("url");
    if (!target) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Missing url query parameter" }));
      return;
    }

    let upstreamUrl;
    try {
      upstreamUrl = new URL(target);
    } catch {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Invalid URL" }));
      return;
    }

    if (!isAllowedHost(upstreamUrl.hostname)) {
      res.writeHead(403, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Only GitHub URLs are allowed" }));
      return;
    }

    const headers = { "User-Agent": "git/isomorphic-git" };
    if (req.headers.authorization) headers.Authorization = req.headers.authorization;
    if (req.headers["content-type"]) headers["Content-Type"] = req.headers["content-type"];
    if (req.headers["git-protocol"]) headers["Git-Protocol"] = req.headers["git-protocol"];
    if (req.headers.accept) headers.Accept = req.headers.accept;

    const body = req.method === "POST" ? await collectBody(req) : undefined;
    const { signal, clear } = createAbortSignal(UPSTREAM_TIMEOUT_MS);

    const response = await fetch(upstreamUrl, {
      method: req.method,
      headers,
      body,
      signal,
    });

    for (const [key, value] of response.headers.entries()) {
      const lower = key.toLowerCase();
      if (["content-encoding", "transfer-encoding", "connection", "www-authenticate"].includes(lower)) {
        continue;
      }
      res.setHeader(key, value);
    }

    res.writeHead(response.status);

    if (!response.body) {
      clear();
      res.end();
      return;
    }

    const upstreamStream = Readable.fromWeb(response.body);
    upstreamStream.on("error", (streamError) => {
      if (!res.headersSent) {
        res.writeHead(502, { "Content-Type": "application/json" });
      }
      res.end(JSON.stringify({ error: "Proxy stream failed", details: String(streamError) }));
    });
    upstreamStream.on("close", clear);
    req.on("close", () => upstreamStream.destroy());
    upstreamStream.pipe(res);
  } catch (error) {
    const status = error?.name === "AbortError" ? 504 : 500;
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Proxy request failed", details: String(error) }));
  }
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Git proxy server listening on ${PORT}`);
});
