import { Type } from "@sinclair/typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import { createControlApiClient } from "./controlApi.js";

function mapToolToAction(toolName: string): string | null {
  const normalized = toolName.trim().toLowerCase();
  if (!normalized) return null;

  const exactMatches: Record<string, string> = {
    "git.push": "git_push",
    "pull_request": "pull_request",
    "pr.create": "pull_request",
    "file.write": "file_write",
    "file.edit": "file_write",
    "secret.read": "secret_access",
    "shell.rm": "destructive_shell",
    "shell.delete": "destructive_shell",
    "test.run": "test_run",
  };
  if (exactMatches[normalized]) return exactMatches[normalized];

  if (normalized.startsWith("http.") || normalized.startsWith("web.")) return "network_request";
  return null;
}

function extractTargetHost(args: Record<string, unknown> | undefined): string | undefined {
  const directHost = args?.targetHost;
  if (typeof directHost === "string" && directHost.trim()) return directHost.trim();

  const urlValue = args?.url;
  if (typeof urlValue !== "string" || !urlValue.trim()) return undefined;
  try {
    return new URL(urlValue).host;
  } catch {
    return undefined;
  }
}

function asText(payload: unknown): string {
  return JSON.stringify(payload, null, 2);
}

export default definePluginEntry({
  id: "studio-control",
  name: "Studio Control",
  description: "Bridges OpenClaw to the AI Venture Studio control API.",
  register(api) {
    const apiAny = api as any;
    const getClient = () => createControlApiClient(apiAny.pluginConfig);

    apiAny.registerTool({
      name: "studio_attention",
      description: "Returns current founder attention items from the control plane.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const limit = Number(params?.limit ?? 20);
        const payload = await client.get(`/v1/attention?limit=${limit}`);
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_task_state",
      description: "Returns the latest control-plane state for one task.",
      parameters: Type.Object({
        taskId: Type.Number(),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const taskId = Number(params?.taskId);
        const payload = await client.get(`/v1/tasks/${taskId}/state`);
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_pending_approvals",
      description: "Returns unresolved approval requests.",
      parameters: Type.Object({
        limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 })),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const limit = Number(params?.limit ?? 20);
        const payload = await client.get(`/v1/approvals/pending?limit=${limit}`);
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerTool({
      name: "studio_create_signal",
      description: "Creates a routed control-plane signal and attention item when needed.",
      parameters: Type.Object({
        source: Type.String(),
        kind: Type.String(),
        severity: Type.String(),
        summary: Type.String(),
        task_id: Type.Optional(Type.Number()),
        venture: Type.Optional(Type.String()),
      }),
      async execute(_toolCallId: string, params: Record<string, unknown>) {
        const client = getClient();
        const payload = await client.post("/v1/signals", {
          source: params?.source,
          kind: params?.kind,
          severity: params?.severity,
          summary: params?.summary,
          task_id: params?.task_id,
          venture: params?.venture,
        });
        return {
          content: [{ type: "text", text: asText(payload) }],
        };
      },
    } as any);

    apiAny.registerHook(
      "before_tool_call",
      async (event: any) => {
        const client = getClient();
        const toolName = event.tool?.name ?? event.toolName ?? "";
        const actionType = mapToolToAction(toolName);
        if (!actionType) return {};
        const taskId = Number(event.metadata?.taskId ?? 0);
        if (!Number.isFinite(taskId) || taskId <= 0) {
          return {
            block: true,
            reason: "Risky tool calls must be attached to a tracked task.",
          };
        }

        const evaluation = await client.post("/v1/policy/evaluate", {
          task_id: taskId,
          agent_run_id: event.metadata?.agentRunId,
          story_id: event.metadata?.storyId,
          agent_role: event.metadata?.agentRole ?? "implementer",
          tool_name: toolName,
          action_type: actionType,
          target_host: extractTargetHost(event.args),
          target_repo: event.metadata?.targetRepo,
          metadata: event.metadata ?? {},
        });

        if (evaluation.decision === "block") {
          return {
            block: true,
            reason: String(evaluation.reason),
          };
        }

        if (evaluation.decision === "require_approval") {
          return {
            requireApproval: true,
            reason: String(evaluation.reason),
          };
        }

        return {};
      },
      { priority: 50 }
    );
  },
});
