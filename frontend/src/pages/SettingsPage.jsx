import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Layout from "../components/Layout";
import { fetchAppSettings, updateAppSettings } from "../services/settingsService";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const { data, isLoading, isError, error: loadError } = useQuery({
    queryKey: ["app-settings"],
    queryFn: fetchAppSettings
  });

  useEffect(() => {
    const settings = data?.data;
    if (!settings) {
      return;
    }
    setSkipDuplicates(Boolean(settings.skip_duplicate_companies));
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: updateAppSettings,
    onSuccess: async (response) => {
      setError("");
      setMessage(response?.message || "Settings saved.");
      await queryClient.invalidateQueries({ queryKey: ["app-settings"] });
    },
    onError: (mutationError) => {
      setMessage("");
      setError(mutationError.response?.data?.message || "Unable to save settings.");
    }
  });

  const onSubmit = (event) => {
    event.preventDefault();
    saveMutation.mutate({ skip_duplicate_companies: skipDuplicates });
  };

  return (
    <Layout>
      <section className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Settings</h1>
          <p className="mt-2 text-sm text-slate-400">
            Control how lead generation handles companies you have already queued or emailed.
          </p>
        </div>

        {isLoading ? <p className="text-slate-400">Loading settings…</p> : null}
        {isError ? (
          <p className="text-rose-300">
            {loadError?.response?.data?.message || "Unable to load settings."}
          </p>
        ) : null}
        {message ? <p className="text-emerald-300">{message}</p> : null}
        {error ? <p className="text-rose-300">{error}</p> : null}

        <form
          onSubmit={onSubmit}
          className="space-y-5 rounded-xl border border-slate-800 bg-slate-950 p-6"
        >
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={skipDuplicates}
              onChange={(event) => setSkipDuplicates(event.target.checked)}
              className="mt-1 h-4 w-4 rounded border-slate-600 bg-slate-900 text-sky-500"
            />
            <span>
              <span className="block text-sm font-medium text-slate-200">
                Skip duplicate companies
              </span>
              <span className="mt-1 block text-sm text-slate-400">
                When on, companies (and recipient emails) already in the email queue as Pending,
                Skipped, Approved, Sent, or Failed are not collected or emailed again. Turn off
                only if you intentionally want to re-queue the same company.
              </span>
            </span>
          </label>

          <button
            type="submit"
            disabled={saveMutation.isPending}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saveMutation.isPending ? "Saving…" : "Save settings"}
          </button>
        </form>
      </section>
    </Layout>
  );
}
