// Managed product timing policy; the selected ordinary Web entrypoint is retained.
import {createWebServer, parseRuntime} from '/app/server/serving.mjs';

try {
  const config = parseRuntime(process.env);
  const server = createWebServer({...config, assetsDir:'/app/dist'}, {
    timeoutMs:5000, responseTimeoutMs:6500,
  });
  server.on('error', () => { process.exitCode = 1; });
  server.listen(config.port, '0.0.0.0');
  let stopping = false;
  function stop() {
    if (stopping) return;
    stopping = true;
    server.close(() => process.exit(0));
    setTimeout(() => {
      server.closeAllConnections();
      process.exit(1);
    }, 7000).unref();
  }
  process.on('SIGTERM', stop);
  process.on('SIGINT', stop);
} catch {
  process.exitCode = 1;
}
