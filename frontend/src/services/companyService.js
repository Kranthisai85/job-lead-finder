import { apiClient } from "./apiClient";

export async function fetchCompanies(params = {}) {
  const response = await apiClient.get("/api/v1/companies", { params });
  return response.data;
}

export async function createCompany(payload) {
  const response = await apiClient.post("/api/v1/companies", payload);
  return response.data;
}

export async function updateCompany(id, payload) {
  const response = await apiClient.patch(`/api/v1/companies/${id}`, payload);
  return response.data;
}

export async function deleteCompany(id) {
  const response = await apiClient.delete(`/api/v1/companies/${id}`);
  return response.data;
}
