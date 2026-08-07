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

export async function markReadyToSend(itemId) {
  const response = await apiClient.post(`/api/v1/email-queue/${itemId}/ready-to-send`);
  return response.data;
}

export async function sendEmail(itemId) {
  const response = await apiClient.post(`/api/v1/email-queue/${itemId}/send`);
  return response.data;
}

export async function sendReadyEmails(limit) {
  const response = await apiClient.post("/api/v1/email-queue/send-ready", {
    limit: limit ?? undefined
  });
  return response.data;
}
