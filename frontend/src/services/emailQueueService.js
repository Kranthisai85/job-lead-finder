import { apiClient } from "./apiClient";

export async function fetchPendingEmails() {
  const response = await apiClient.get("/api/v1/email-queue/pending");
  return response.data;
}

export async function approveEmail(itemId) {
  const response = await apiClient.post(`/api/v1/email-queue/${itemId}/approve`);
  return response.data;
}

export async function skipEmail(itemId) {
  const response = await apiClient.post(`/api/v1/email-queue/${itemId}/skip`);
  return response.data;
}
