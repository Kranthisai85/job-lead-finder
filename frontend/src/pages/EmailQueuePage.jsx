import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Layout from "../components/Layout";
import {
  approveEmail,
  fetchPendingEmails,
  skipEmail,
  updateEmailDraft
} from "../services/emailQueueService";

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

function EditableText({
  label,
  value,
  multiline = false,
  editable,
  onSave,
  saving
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");

  useEffect(() => {
    if (!editing) {
      setDraft(value || "");
    }
  }, [value, editing]);

  const commit = async () => {
    const next = draft.trim();
    if (!next) {
      setDraft(value || "");
      setEditing(false);
      return;
    }
    if (next === (value || "").trim()) {
      setEditing(false);
      return;
    }
    await onSave(next);
    setEditing(false);
  };

  if (editing && editable) {
    return (
      <div>
        <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
        {multiline ? (
          <textarea
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => {
              void commit();
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setDraft(value || "");
                setEditing(false);
              }
            }}
            rows={10}
            disabled={saving}
            className="mt-1 w-full whitespace-pre-wrap rounded-lg border border-sky-700 bg-slate-950 p-3 text-sm text-slate-100 outline-none focus:border-sky-500"
          />
        ) : (
          <input
            autoFocus
            type="text"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => {
              void commit();
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void commit();
              }
              if (event.key === "Escape") {
                setDraft(value || "");
                setEditing(false);
              }
            }}
            disabled={saving}
            className="mt-1 w-full rounded-lg border border-sky-700 bg-slate-950 px-3 py-2 text-sm font-medium text-white outline-none focus:border-sky-500"
          />
        )}
        <p className="mt-1 text-xs text-slate-500">Click away to save · Esc to cancel</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      {multiline ? (
        <pre
          title={editable ? "Double-click to edit" : undefined}
          onDoubleClick={() => {
            if (editable) {
              setEditing(true);
            }
          }}
          className={[
            "mt-1 whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-200",
            editable ? "cursor-text hover:border-slate-600" : ""
          ].join(" ")}
        >
          {value}
        </pre>
      ) : (
        <p
          title={editable ? "Double-click to edit" : undefined}
          onDoubleClick={() => {
            if (editable) {
              setEditing(true);
            }
          }}
          className={[
            "mt-1 text-sm font-medium text-white",
            editable ? "cursor-text rounded-md px-1 py-0.5 hover:bg-slate-800/80" : ""
          ].join(" ")}
        >
          {value}
        </p>
      )}
      {editable ? (
        <p className="mt-1 text-xs text-slate-500">Double-click to edit before Approve &amp; Send</p>
      ) : null}
    </div>
  );
}

export default function EmailQueuePage() {
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [localStatus, setLocalStatus] = useState({});
  const [draftOverrides, setDraftOverrides] = useState({});

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["email-queue-pending"],
    queryFn: fetchPendingEmails
  });

  const invalidateQueue = async () => {
    await queryClient.invalidateQueries({ queryKey: ["email-queue-pending"] });
  };

  const approveMutation = useMutation({
    mutationFn: approveEmail,
    onSuccess: async (response, itemId) => {
      const status = response?.data?.status || "SENT";
      setLocalStatus((current) => ({ ...current, [itemId]: status }));
      if (status === "SENT") {
        setActionError("");
        setActionMessage(response?.message || "Approved and sent.");
      } else if (status === "FAILED") {
        setActionMessage("");
        setActionError(
          response?.data?.error_message ||
            response?.message ||
            "Approved but send failed. Check SMTP settings."
        );
      } else {
        setActionError("");
        setActionMessage(response?.message || "Approved.");
      }
      await invalidateQueue();
    },
    onError: (mutationError) => {
      setActionError(
        mutationError.response?.data?.message || "Unable to approve and send email."
      );
    }
  });

  const skipMutation = useMutation({
    mutationFn: skipEmail,
    onSuccess: async (response, itemId) => {
      setActionError("");
      setActionMessage("");
      setLocalStatus((current) => ({
        ...current,
        [itemId]: response?.data?.status || "SKIPPED"
      }));
      await invalidateQueue();
    },
    onError: (mutationError) => {
      setActionError(mutationError.response?.data?.message || "Unable to skip email.");
    }
  });

  const saveDraftMutation = useMutation({
    mutationFn: ({ itemId, subject, body }) => updateEmailDraft(itemId, { subject, body }),
    onSuccess: async (response, variables) => {
      setActionError("");
      setActionMessage(response?.message || "Draft saved.");
      const updated = response?.data;
      if (updated) {
        setDraftOverrides((current) => ({
          ...current,
          [variables.itemId]: {
            subject: updated.subject,
            body: updated.body
          }
        }));
      }
      await invalidateQueue();
    },
    onError: (mutationError) => {
      setActionMessage("");
      setActionError(mutationError.response?.data?.message || "Unable to save draft.");
    }
  });

  const items = data?.data?.items ?? [];
  const busyId =
    approveMutation.isPending || skipMutation.isPending || saveDraftMutation.isPending
      ? approveMutation.variables ||
        skipMutation.variables ||
        saveDraftMutation.variables?.itemId
      : null;

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-white">Email Queue</h2>
          <p className="text-sm text-slate-400">
            Double-click subject or body to edit, then Approve &amp; Send (or Skip).
          </p>
        </div>

        {actionError ? (
          <div className="rounded-lg border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
            {actionError}
          </div>
        ) : null}
        {actionMessage && !actionError ? (
          <div className="rounded-lg border border-emerald-800 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-200">
            {actionMessage}
          </div>
        ) : null}

        {isLoading ? <p className="text-sm text-slate-400">Loading email queue...</p> : null}
        {isError ? (
          <p className="text-sm text-rose-300">
            {error?.response?.data?.message || "Failed to load email queue."}
          </p>
        ) : null}

        {!isLoading && !isError && items.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-6 py-10 text-center">
            <p className="text-sm text-slate-300">No emails awaiting review or send.</p>
          </div>
        ) : null}

        <div className="space-y-4">
          {items.map((item) => {
            const displayStatus = localStatus[item.id] || item.status;
            const isBusy = busyId === item.id;
            const canEdit = displayStatus === "PENDING";
            const subject = draftOverrides[item.id]?.subject ?? item.subject;
            const body = draftOverrides[item.id]?.body ?? item.body;

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

                {item.error_message || displayStatus === "FAILED" ? (
                  <div className="mt-4 rounded-lg border border-rose-900/60 bg-rose-950/30 px-3 py-2">
                    <p className="text-xs uppercase tracking-wide text-rose-400">Failure reason</p>
                    <p className="mt-1 text-sm text-rose-200">
                      {item.error_message || "Send failed"}
                    </p>
                  </div>
                ) : null}

                <div className="mt-4 space-y-4">
                  <EditableText
                    label="Subject"
                    value={subject}
                    editable={canEdit}
                    saving={isBusy}
                    onSave={async (next) => {
                      await saveDraftMutation.mutateAsync({
                        itemId: item.id,
                        subject: next,
                        body
                      });
                    }}
                  />
                  <EditableText
                    label="Body"
                    value={body}
                    multiline
                    editable={canEdit}
                    saving={isBusy}
                    onSave={async (next) => {
                      await saveDraftMutation.mutateAsync({
                        itemId: item.id,
                        subject,
                        body: next
                      });
                    }}
                  />
                </div>

                {displayStatus === "PENDING" ? (
                  <div className="mt-5 flex flex-wrap gap-3">
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => approveMutation.mutate(item.id)}
                      className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Approve &amp; Send
                    </button>
                    <button
                      type="button"
                      disabled={isBusy}
                      onClick={() => skipMutation.mutate(item.id)}
                      className="rounded-lg border border-slate-600 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Skip
                    </button>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </Layout>
  );
}
