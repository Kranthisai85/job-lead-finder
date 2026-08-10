import { apiClient } from "./apiClient";

export async function runPipelineNow() {
  const response = await apiClient.post("/api/v1/jobs/run-now");
  return response.data;
}

export async function fetchPipelineRunStatus() {
  const response = await apiClient.get("/api/v1/jobs/run-now/status");
  return response.data;
}
