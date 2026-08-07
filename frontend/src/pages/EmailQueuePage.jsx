import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Layout from "../components/Layout";
import { approveEmail, fetchPendingEmails, skipEmail } from "../services/emailQueueService";

function StatusBadge({ status }) {
  const toneByStatus = {
    PENDING: "bg-amber-500/20 text-amber-300",
    APPROVED: "bg-emerald-500/20 text-emerald-300",
    READY_TO_SEND: "bg-sky-500/20 text-sky-300",
    SKIPPED: "bg-slate-500/20 text-slate-300",
    SENT: "bg-emerald-700/30 text-emerald-200",
    FAILED: "bg-rose-500/20 text-rose-300",
    SENDING: "bg-indigo-500/20 text-indigo-300",
    CANCELLED: "bg-slate-600/30 text-slate-300"
  };
  const tone = toneByStatus[status] || "bg-slate-700 text-slate-200";

  return (
    <span className={`rounded-md px-2 py-1 text-xs font-medium uppercase tracking-wide ${tone}`}>
      {status}
    </span>
  );
}

export default function EmailQueuePage() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState("");
  const [localStatus, setLocalStatus] = useState({});

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["email-queue-pending"],
    queryFn: fetchPendingEmails
  });

  const approveMutation = useMutation({
    mutationFn: approveEmail,
    onSuccess: async (response, itemId) => {
      setActionError("");
      setLocalStatus((current) => ({
        ...current,
        [itemId]: response?.data?.status || "APPROVED"
      }));
      await queryClient.invalidateQueries({ queryKey: ["email-queue-pending"] });
    },
    onError: (mutationError) => {
      setActionError(mutationError.response?.data?.message || "Unable to approve email.");
    }
  });

  const skipMutation = useMutation({
    mutationFn: skipEmail,
    onSuccess: async (response, itemId) => {
      setActionError("");
      setLocalStatus((current) => ({
        ...current,
        [itemId]: response?.data?.status || "SKIPPED"
      }));
      await queryClient.invalidateQueries({ queryKey: ["email-queue-pending"] });
    },
    onError: (mutationError) => {
      setActionError(mutationError.response?.data?.message || "Unable to skip email.");
    }
  });

  const items = data?.data?.items ?? [];
  const busyId =
    approveMutation.isPending || skipMutation.isPending
      ? approveMutation.variables || skipMutation.variables
      : null;

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-white">Email Queue</h2>
          <p className="text-sm text-slate-400">
            Review pending outbound drafts. Approve or skip before any send.
          </p>
        </div>

        {actionError ? (
          <div className="rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
            {actionError}
          </div>
        ) : null}

        {isLoading ? <p className="text-sm text-slate-400">Loading pending emails...</p> : null}
        {isError ? (
          <p className="text-sm text-rose-300">
            {error?.response?.data?.message || "Failed to load pending emails."}
          </p>
        ) : null}

        {!isLoading && !isError && items.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-6 py-10 text-center">
            <p className="text-sm text-slate-300">No pending emails to review.</p>
          </div>
        ) : null}

        <div className="space-y-4">
          {items.map((item) => {
            const displayStatus = localStatus[item.id] || item.status;
            const actionDisabled = busyId === item.id || displayStatus !== "PENDING";

            return (
              <article
                key={item.id}
                className="rounded-xl border border-slate-800 bg-slate-900/70 p-5 shadow-sm"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-white">
                      {item.company_name || "Unknown company"}
                    </h3>
                    <p className="text-sm text-slate-400">
                      {item.company_website || "No website"} · {item.contact_name} &lt;
                      {item.contact_email}&gt;
                    </p>
                  </div>
                  <div className="flex flex-col items-start gap-2 md:items-end">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Queue status</p>
                    <StatusBadge status={displayStatus} />
                  </div>
                </div>

                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-slate-500">
                      Qualification score
                    </p>
                    <p className="mt-1 text-sm text-white">
                      {item.qualification_score ?? item.lead_score ?? "—"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-slate-500">
                      Qualification status
                    </p>
                    <p className="mt-1 text-sm text-white">
                      {item.qualification_status || "—"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-slate-500">Generation</p>
                    <p className="mt-1 text-sm text-white">{item.generation_source || "—"}</p>
                  </div>
                </div>

                {item.qualification_reasons?.length ? (
                  <div className="mt-4">
                    <p className="text-xs uppercase tracking-wide text-slate-500">
                      Qualification reasons
                    </p>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
                      {item.qualification_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="mt-4 space-y-2">
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-500">Subject</p>
                    <p className="mt-1 text-sm font-medium text-white">{item.subject}</p>
                  </div>
                  <div>
                    <p className="text-xs uppercase tracking-wide text-slate-500">Body</p>
                    <pre className="mt-1 whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-200">
                      {item.body}
                    </pre>
                  </div>
                </div>

                <div className="mt-5 flex flex-wrap gap-3">
                  <button
                    type="button"
                    disabled={actionDisabled}
                    onClick={() => approveMutation.mutate(item.id)}
                    className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={actionDisabled}
                    onClick={() => skipMutation.mutate(item.id)}
                    className="rounded-lg border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Skip
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </Layout>
  );
}
