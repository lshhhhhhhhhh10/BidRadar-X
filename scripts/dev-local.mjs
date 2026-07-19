import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";


const root = resolve(import.meta.dirname, "..");
const isWindows = process.platform === "win32";
const python = resolve(
  root,
  "backend",
  ".venv",
  isWindows ? "Scripts" : "bin",
  isWindows ? "python.exe" : "python",
);
const npmCommand = isWindows ? "npm.cmd" : "npm";
const runtimeDataDir = process.env.TENDER_DATA_DIR || resolve(root, ".local-data", "product");
const childEnvironment = {
  ...process.env,
  TENDER_DATA_DIR: runtimeDataDir,
};

if (!existsSync(python)) {
  console.error("缺少 backend/.venv，请先安装后端依赖。");
  process.exit(1);
}

const backend = spawn(python, ["run.py"], {
  cwd: resolve(root, "backend"),
  env: childEnvironment,
  stdio: "inherit",
  windowsHide: true,
});
const frontend = spawn(npmCommand, ["run", "dev:web"], {
  cwd: root,
  env: childEnvironment,
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
backend.on("error", (error) => {
  console.error(`后端启动失败：${error.message}`);
  stop(1);
});
frontend.on("error", (error) => {
  console.error(`前端启动失败：${error.message}`);
  stop(1);
});
process.on("SIGINT", () => stop(0));
process.on("SIGTERM", () => stop(0));
