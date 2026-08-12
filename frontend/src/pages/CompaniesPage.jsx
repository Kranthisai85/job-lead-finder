import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import CompanyModal from "../components/CompanyModal";
import ConfirmDialog from "../components/ConfirmDialog";
import Layout from "../components/Layout";
import {
  createCompany,
  deleteCompany,
  fetchCompanies,
  updateCompany
} from "../services/companyService";
import { formatIstDateTime } from "../utils/datetime";

const PAGE_SIZE = 20;

export default function CompaniesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState("create");
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [companyToDelete, setCompanyToDelete] = useState(null);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    setPage(1);
  }, [search]);

  const queryParams = useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      search: search.trim() || undefined,
      sort: "created_at",
      order: "desc"
    }),
    [page, search]
  );

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["companies", queryParams],
    queryFn: () => fetchCompanies(queryParams)
  });

  const saveMutation = useMutation({
    mutationFn: async (payload) => {
      if (modalMode === "edit" && selectedCompany) {
        return updateCompany(selectedCompany.id, payload);
      }
      return createCompany(payload);
    },
    onSuccess: async () => {
      setActionError("");
      setModalOpen(false);
      setSelectedCompany(null);
      await queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (mutationError) => {
      setActionError(mutationError.response?.data?.message || "Unable to save company.");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (companyId) => deleteCompany(companyId),
    onSuccess: async () => {
      setActionError("");
      setConfirmOpen(false);
      setCompanyToDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (mutationError) => {
      setActionError(mutationError.response?.data?.message || "Unable to delete company.");
    }
  });

  const companies = data?.data?.items ?? [];
  const total = data?.data?.total ?? 0;
  const totalPages = Math.max(1, data?.data?.total_pages ?? 1);
  const currentPage = data?.data?.page ?? page;
  const canGoPrev = currentPage > 1;
  const canGoNext = currentPage < totalPages;
  const rangeStart = total === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(currentPage * PAGE_SIZE, total);

  function openCreateModal() {
    setModalMode("create");
    setSelectedCompany(null);
    setActionError("");
    setModalOpen(true);
  }

  function openEditModal(company) {
    setModalMode("edit");
    setSelectedCompany(company);
    setActionError("");
    setModalOpen(true);
  }

  function openDeleteDialog(company) {
    setCompanyToDelete(company);
    setActionError("");
    setConfirmOpen(true);
  }

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-white">Companies</h2>
            <p className="text-sm text-slate-400">Manage discovered startup leads.</p>
          </div>
          <button
            type="button"
            onClick={openCreateModal}
            className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400"
          >
            Create Company
          </button>
        </div>

        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search companies..."
            className="w-full max-w-md rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500 md:w-80"
          />
        </div>

        {actionError ? (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {actionError}
          </div>
        ) : null}

        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
          {isLoading ? (
            <div className="px-6 py-16 text-center text-slate-400">Loading companies...</div>
          ) : isError ? (
            <div className="px-6 py-16 text-center text-rose-300">
              {error?.response?.data?.message || "Failed to load companies."}
            </div>
          ) : companies.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <p className="text-lg font-medium text-white">No companies yet</p>
              <p className="mt-2 text-sm text-slate-400">
                Create your first company to start building your lead pipeline.
              </p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-800">
                  <thead className="bg-slate-900/80">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Name
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Website
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Industry
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Source
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Actions
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Created At
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {companies.map((company) => (
                      <tr key={company.id} className="hover:bg-slate-900/60">
                        <td className="px-4 py-3 text-sm text-white">{company.name}</td>
                        <td className="px-4 py-3 text-sm text-slate-300">{company.website}</td>
                        <td className="px-4 py-3 text-sm text-slate-300">
                          {company.industry || "-"}
                        </td>
                        <td className="px-4 py-3 text-sm text-slate-300">
                          {company.source || "-"}
                        </td>
                        <td className="px-4 py-3 text-right text-sm">
                          <button
                            type="button"
                            onClick={() => openEditModal(company)}
                            className="mr-3 text-sky-400 hover:text-sky-300"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => openDeleteDialog(company)}
                            className="text-rose-400 hover:text-rose-300"
                          >
                            Delete
                          </button>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-sm text-slate-300">
                          {formatIstDateTime(company.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-800 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-400">
                  Showing {rangeStart}–{rangeEnd} of {total}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={!canGoPrev}
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Previous
                  </button>
                  <span className="min-w-[7rem] text-center text-sm text-slate-300">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={!canGoNext}
                    onClick={() => setPage((current) => current + 1)}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <CompanyModal
        open={modalOpen}
        mode={modalMode}
        initialValues={selectedCompany || undefined}
        onClose={() => setModalOpen(false)}
        onSubmit={(payload) => saveMutation.mutate(payload)}
        isSubmitting={saveMutation.isPending}
      />

      <ConfirmDialog
        open={confirmOpen}
        title="Delete company"
        message={`Are you sure you want to delete ${companyToDelete?.name || "this company"}?`}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => deleteMutation.mutate(companyToDelete.id)}
        isSubmitting={deleteMutation.isPending}
      />
    </Layout>
  );
}
