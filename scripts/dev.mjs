import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const apiPort = process.env.API_PORT ?? "8000";
const frontendPort = process.env.FRONTEND_PORT ?? "3000";
const children = [];
let stopping = false;

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (!child.pid) continue;
    try {
      if (process.platform === "win32") child.kill("SIGTERM");
      else process.kill(-child.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") console.error(error.message);
    }
  }
  process.exitCode = code;
}

function run(command, args, env = process.env) {
  const child = spawn(command, args, { cwd: root, env, stdio: "inherit", detached: process.platform !== "win32" });
  children.push(child);
  child.on("error", error => { console.error(error.message); stop(1); });
  child.on("exit", code => { if (!stopping) stop(code ?? 1); });
}

console.log(`Atelier : http://127.0.0.1:${frontendPort} · API : http://127.0.0.1:${apiPort}`);
run("uv", ["run", "embroidery-rungs-web", "--host", "127.0.0.1", "--port", apiPort]);
run(process.platform === "win32" ? "pnpm.cmd" : "pnpm", ["--dir", "frontend", "dev", "--hostname", "127.0.0.1", "--port", frontendPort], {
  ...process.env, PYTHON_API_URL: `http://127.0.0.1:${apiPort}`,
});
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
