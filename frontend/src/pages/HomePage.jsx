import { useQuery } from "@tanstack/react-query";

import { apiClient } from "../services/apiClient";

function fetchHealth() {
  return apiClient.get("/health").then((response) => response.data);
}

export default function HomePage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth
  });

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-4xl font-bold tracking-tight">lead-finder</h1>
        <p className="text-slate-300">
          Frontend scaffold is ready. Business logic will be added later.
        </p>
        <p className="rounded border border-slate-700 bg-slate-900 px-4 py-2 text-sm">
          Backend status:{" "}
          {isLoading
            ? "checking..."
            : isError
              ? "unreachable"
              : data?.status ?? "unknown"}
        </p>
      </section>
    </main>
  );
}
