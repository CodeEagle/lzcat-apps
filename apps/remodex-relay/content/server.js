// FILE: server.js
// Purpose: HTTP server with WebSocket relay for Remodex pairing
// Layer: Main entry point

const http = require("http");
const fs = require("fs");
const path = require("path");
const WebSocket = require("ws");
const { setupRelay, getRelayStats } = require("./relay");

const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 3000;
const HOST = process.env.HOST || "0.0.0.0";

// Create HTTP server
const server = http.createServer((req, res) => {
  // Handle static files
  const urlPath = new URL(req.url, `http://${req.headers.host}`).pathname;

  // API endpoint for stats
  if (req.method === "GET" && urlPath === "/api/stats") {
    const stats = getRelayStats();
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(stats, null, 2));
    return;
  }

  // API endpoint for health check
  if (req.method === "GET" && urlPath === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", timestamp: new Date().toISOString() }));
    return;
  }

  // Serve index.html for root path
  if (req.method === "GET" && (urlPath === "/" || urlPath === "/index.html")) {
    const indexPath = path.join(__dirname, "index.html");
    if (fs.existsSync(indexPath)) {
      const content = fs.readFileSync(indexPath, "utf-8");
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(content);
      return;
    }
  }

  // 404 for everything else
  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("Not Found\n");
});

// Create WebSocket server attached to HTTP server
const wss = new WebSocket.Server({ server });

// Setup relay behavior
setupRelay(wss);

// Start server
server.listen(PORT, HOST, () => {
  console.log(`[remodex-relay] Server running on http://${HOST}:${PORT}`);
  console.log(`[remodex-relay] WebSocket endpoint: ws://${HOST}:${PORT}/relay/{sessionId}`);
  console.log(`[remodex-relay] Health check: http://${HOST}:${PORT}/health`);
  console.log(`[remodex-relay] Stats endpoint: http://${HOST}:${PORT}/api/stats`);
});

// Graceful shutdown
process.on("SIGTERM", () => {
  console.log("[remodex-relay] SIGTERM received, shutting down gracefully");
  server.close(() => {
    console.log("[remodex-relay] Server closed");
    process.exit(0);
  });
});

process.on("SIGINT", () => {
  console.log("[remodex-relay] SIGINT received, shutting down gracefully");
  server.close(() => {
    console.log("[remodex-relay] Server closed");
    process.exit(0);
  });
});
