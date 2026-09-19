// Minimal production Next server for the all-in-one deployment role.
// Next's stock `next start` does not accept WebSocket upgrades, so keep the
// normal HTTP request handler and proxy only the authenticated realtime route
// to the loopback FastAPI process. No browser credential is put in the URL.
import http from "node:http";
import net from "node:net";
import next from "next";

const hostname = "0.0.0.0";
const port = Number.parseInt(process.env.PORT || "10000", 10);
const apiOrigin = new URL(process.env.API_ORIGIN || "http://127.0.0.1:8000");

if (apiOrigin.protocol !== "http:") {
  throw new Error("The self-hosted realtime upstream must use loopback HTTP.");
}

const app = next({ dev: false, hostname, port });
const handle = app.getRequestHandler();

function isRealtimeRequest(request) {
  try {
    return new URL(request.url || "/", "http://localhost").pathname === "/api/v1/realtime";
  } catch {
    return false;
  }
}

function proxyRealtimeUpgrade(request, socket, head) {
  if (!isRealtimeRequest(request)) {
    socket.destroy();
    return;
  }
  const upstream = net.createConnection({ host: apiOrigin.hostname, port: Number(apiOrigin.port || 80) });
  const closeBoth = () => {
    if (!socket.destroyed) socket.destroy();
    if (!upstream.destroyed) upstream.destroy();
  };
  const timeout = setTimeout(closeBoth, 15_000);
  upstream.once("connect", () => {
    clearTimeout(timeout);
    // rawHeaders preserves the WebSocket subprotocol, Origin, and browser
    // headers without trying to reconstruct or log a credential-bearing
    // handshake. FastAPI validates the preserved Origin and ticket itself.
    const lines = [`${request.method} ${request.url} HTTP/${request.httpVersion}`];
    for (let index = 0; index < request.rawHeaders.length; index += 2) {
      lines.push(`${request.rawHeaders[index]}: ${request.rawHeaders[index + 1]}`);
    }
    upstream.write(`${lines.join("\r\n")}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.once("error", closeBoth);
  socket.once("error", closeBoth);
}

await app.prepare();
const server = http.createServer((request, response) => handle(request, response));
server.on("upgrade", proxyRealtimeUpgrade);
server.listen(port, hostname, () => {
  process.stdout.write(`[web] listening on ${hostname}:${port}\n`);
});
