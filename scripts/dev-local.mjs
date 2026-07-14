import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";


const root = resolve(import.meta.dirname, "..");
const python = resolve(root, "backend", ".venv", "Scripts", "python.exe");

if (!existsSync(python)) {
  console.error("缺少 backend/.venv，请先安装后端依赖。");
  process.exit(1);
}

const backend = spawn(python, ["run.py"], {
  cwd: resolve(root, "backend"),
  stdio: "inherit",
  windowsHide: true,
});
const frontend = spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", "npm.cmd run dev:web"], {
  cwd: root,
  stdio: "inherit",
  windowsHide: true,
});

let stopping = false;
function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  backend.kill();
  frontend.kill();
  setTimeout(() => process.exit(exitCode), 250);
}

backend.on("exit", (code) => stop(code ?? 1));
frontend.on("exit", (code) => stop(code ?? 1));
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
