import { requestJson } from "./http";

export function listWorkflowHistory(workflowId, options = {}) {
  const limit = options.limit ?? 20;
  const offset = options.offset ?? 0;
  return requestJson(`/api/workflows/${workflowId}/threads/history?limit=${limit}&offset=${offset}`, {
    target: options.target,
  });
}

export function getWorkflowTrace(workflowId, threadId, options = {}) {
  return requestJson(`/api/workflows/${workflowId}/threads/${encodeURIComponent(threadId)}/trace`, {
    target: options.target,
  });
}
