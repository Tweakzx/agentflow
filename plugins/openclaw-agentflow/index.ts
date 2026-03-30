import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { definePluginEntry } from "openclaw/plugin-sdk/core";

const execFileAsync = promisify(execFile);

type PluginConfig = {
  dbPath: string;
  defaultProject?: string;
  defaultAdapter?: string;
  defaultAgentName?: string;
};

async function runAgentflow(args: string[]): Promise<{ stdout: string; stderr: string }> {
  const { stdout, stderr } = await execFileAsync("python3", ["-m", "agentflow.cli", ...args], {
    env: { ...process.env, PYTHONPATH: "src" },
    cwd: process.cwd()
  });
  return { stdout: String(stdout ?? ""), stderr: String(stderr ?? "") };
}

export default definePluginEntry({
  id: "agentflow",
  name: "AgentFlow",
  register(api: any) {
    const cfg: PluginConfig = (api?.config ?? {}) as PluginConfig;
    const dbPath = cfg.dbPath || "./data/agentflow.db";
    const defaultProject = cfg.defaultProject || "default";
    const defaultAdapter = cfg.defaultAdapter || "mock";
    const defaultAgentName = cfg.defaultAgentName || "openclaw-agent";

    api.registerCommand?.({
      id: "agentflow.run",
      description: "Run one AgentFlow task through adapter",
      async handler(input: { project?: string; adapter?: string; agent?: string }) {
        const project = input?.project || defaultProject;
        const adapter = input?.adapter || defaultAdapter;
        const agent = input?.agent || defaultAgentName;
        const result = await runAgentflow([
          "--db",
          dbPath,
          "run-once",
          "--project",
          project,
          "--adapter",
          adapter,
          "--agent",
          agent
        ]);
        return { ok: true, output: result.stdout || result.stderr };
      }
    });

    api.registerTool?.({
      id: "agentflow_status",
      description: "Read AgentFlow queue status",
      inputSchema: {
        type: "object",
        properties: {
          project: { type: "string" }
        }
      },
      async run(input: { project?: string }) {
        const project = input?.project || defaultProject;
        const result = await runAgentflow(["--db", dbPath, "board", "--project", project]);
        return { content: result.stdout || result.stderr };
      }
    });

    api.registerHttpRoute?.({
      method: "POST",
      path: "/agentflow/webhook/comment",
      async handler(req: any) {
        const payload = req?.body ?? {};
        const project = payload?.project || defaultProject;
        const adapter = payload?.adapter || defaultAdapter;
        const agent = payload?.agent || defaultAgentName;

        const fs = await import("node:fs/promises");
        const os = await import("node:os");
        const path = await import("node:path");
        const tmp = path.join(os.tmpdir(), `agentflow-comment-${Date.now()}.json`);
        await fs.writeFile(tmp, JSON.stringify(payload), "utf-8");

        const result = await runAgentflow([
          "--db",
          dbPath,
          "handle-comment",
          "--project",
          project,
          "--payload-file",
          tmp,
          "--adapter",
          adapter,
          "--agent",
          agent
        ]);

        await fs.rm(tmp, { force: true });
        return { status: 200, body: { ok: true, output: result.stdout || result.stderr } };
      }
    });
  }
});
