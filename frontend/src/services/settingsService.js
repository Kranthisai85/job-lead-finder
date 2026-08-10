import { apiClient } from "./apiClient";

export async function fetchAppSettings() {
  const response = await apiClient.get("/api/v1/settings");
  return response.data;
}

export async function updateAppSettings(payload) {
  const response = await apiClient.put("/api/v1/settings", payload);
  return response.data;
}
