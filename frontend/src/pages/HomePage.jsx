import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Layout from "../components/Layout";
import { fetchPipelineRunStatus, runPipelineNow } from "../services/jobsService";

export default function HomePage() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const { data: statusData } = useQuery({
    queryKey: ["pipeline-run-status"],
    queryFn: fetchPipelineRunStatus,
    refetchInterval: (query) =>
      query.state.data?.data?.status === "running" ? 5000 : false
  });

  const running = statusData?.data?.status === "running";

  const runMutation = useMutation({
    mutationFn: runPipelineNow,
    onSuccess: async (response) => {
      setError("");
      setMessage(
        response?.message ||
          "Lead generation started. Check Email Queue when it finishes."
      );
      await queryClient.invalidateQueries({ queryKey: ["pipeline-run-status"] });
    },
    onError: (mutationError) => {
      setMessage("");
      const status = mutationError.response?.status;
      const apiMessage = mutationError.response?.data?.message;
      if (status === 409) {
        setError(apiMessage || "Lead generation is already running.");
      } else {
        setError(apiMessage || "Unable to start lead generation.");
      }
    }
  });

  return (
    <Layout>
      <section className="mx-auto flex min-h-[70vh] max-w-3xl flex-col items-center justify-center gap-6 text-center">
        <div className="space-y-3">
          <h1 className="text-4xl font-bold tracking-tight text-white">lead-finder</h1>
          <p className="text-slate-300">
            Run the full scrape → score → draft email pipeline now. This does not change the daily
            09:00 Asia/Kolkata schedule.
          </p>
        </div>

        <button
          type="button"
          disabled={runMutation.isPending || running}
          onClick={() => runMutation.mutate()}
          className="rounded-lg bg-emerald-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {running || runMutation.isPending ? "Running…" : "Run Now"}
        </button>

        {running ? (
          <p className="text-sm text-amber-300">
            Pipeline is running in the background. New drafts will appear in Email Queue when ready.
          </p>
        ) : null}
        {message ? <p className="text-sm text-emerald-300">{message}</p> : null}
        {error ? <p className="text-sm text-rose-300">{error}</p> : null}
      </section>
    </Layout>
  );
}
