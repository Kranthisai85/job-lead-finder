import { apiClient } from "./apiClient";

export async function fetchSenderProfile() {
  const response = await apiClient.get("/api/v1/profile");
  return response.data;
}

export async function updateSenderProfile(payload) {
  const response = await apiClient.put("/api/v1/profile", payload);
  return response.data;
}
