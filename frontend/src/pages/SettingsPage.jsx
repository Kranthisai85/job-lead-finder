import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Layout from "../components/Layout";
import { fetchAppSettings, updateAppSettings } from "../services/settingsService";

function formatTime(hour, minute) {
  return `${String(hour ?? 9).padStart(2, "0")}:${String(minute ?? 0).padStart(2, "0")}`;
}

function parseTime(value) {
  const [hourText, minuteText] = String(value || "09:00").split(":");
  const hour = Number.parseInt(hourText, 10);
  const minute = Number.parseInt(minuteText, 10);
  return {
    hour: Number.isFinite(hour) ? Math.min(23, Math.max(0, hour)) : 9,
    minute: Number.isFinite(minute) ? Math.min(59, Math.max(0, minute)) : 0
  };
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [scheduleTime, setScheduleTime] = useState("09:00");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
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
    setScheduleTime(formatTime(settings.scheduler_hour, settings.scheduler_minute));
    if (settings.scheduler_timezone) {
      setTimezone(settings.scheduler_timezone);
    }
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
    const { hour, minute } = parseTime(scheduleTime);
    saveMutation.mutate({
      skip_duplicate_companies: skipDuplicates,
      scheduler_hour: hour,
      scheduler_minute: minute
    });
  };

  return (
    <Layout>
      <section className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Settings</h1>
          <p className="mt-2 text-sm text-slate-400">
            Control lead generation schedule and how duplicates are handled.
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
          <div>
            <label htmlFor="scheduler-time" className="block text-sm font-medium text-slate-200">
              Daily automatic run time
            </label>
            <p className="mt-1 text-sm text-slate-400">
              Lead generation runs once every day at this time ({timezone}). Default is 09:00.
            </p>
            <input
              id="scheduler-time"
              type="time"
              value={scheduleTime}
              onChange={(event) => setScheduleTime(event.target.value || "09:00")}
              className="mt-3 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
            />
          </div>

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
