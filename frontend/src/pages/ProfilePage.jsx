import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import Layout from "../components/Layout";
import { fetchSenderProfile, updateSenderProfile } from "../services/profileService";

const emptyForm = {
  display_name: "",
  linkedin_url: "",
  github_url: ""
};

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const { data, isLoading, isError, error: loadError } = useQuery({
    queryKey: ["sender-profile"],
    queryFn: fetchSenderProfile
  });

  useEffect(() => {
    const profile = data?.data;
    if (!profile) {
      return;
    }
    setForm({
      display_name: profile.display_name || "",
      linkedin_url: profile.linkedin_url || "",
      github_url: profile.github_url || ""
    });
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: updateSenderProfile,
    onSuccess: async (response) => {
      setError("");
      setMessage(response?.message || "Profile saved. New emails will use this signature.");
      await queryClient.invalidateQueries({ queryKey: ["sender-profile"] });
    },
    onError: (mutationError) => {
      setMessage("");
      setError(mutationError.response?.data?.message || "Unable to save profile.");
    }
  });

  const onChange = (field) => (event) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
  };

  const onSubmit = (event) => {
    event.preventDefault();
    saveMutation.mutate({
      display_name: form.display_name.trim(),
      linkedin_url: form.linkedin_url.trim(),
      github_url: form.github_url.trim()
    });
  };

  return (
    <Layout>
      <section className="mx-auto max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Profile</h1>
          <p className="mt-2 text-sm text-slate-400">
            Your name, LinkedIn, and GitHub are used in outbound email signatures. Save these
            before approving emails so{" "}
            <code className="text-slate-300">{"{{sender_name}}"}</code> is replaced.
          </p>
        </div>

        {isLoading ? <p className="text-slate-400">Loading profile…</p> : null}
        {isError ? (
          <p className="text-rose-300">
            {loadError?.response?.data?.message || "Unable to load profile."}
          </p>
        ) : null}
        {message ? <p className="text-emerald-300">{message}</p> : null}
        {error ? <p className="text-rose-300">{error}</p> : null}

        <form onSubmit={onSubmit} className="space-y-4 rounded-xl border border-slate-800 bg-slate-950 p-6">
          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-300">Display name</span>
            <input
              type="text"
              value={form.display_name}
              onChange={onChange("display_name")}
              placeholder="Your full name"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-slate-500"
              required
            />
          </label>

          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-300">LinkedIn URL</span>
            <input
              type="url"
              value={form.linkedin_url}
              onChange={onChange("linkedin_url")}
              placeholder="https://linkedin.com/in/you"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-slate-500"
            />
          </label>

          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-300">GitHub URL</span>
            <input
              type="url"
              value={form.github_url}
              onChange={onChange("github_url")}
              placeholder="https://github.com/you"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white outline-none focus:border-slate-500"
            />
          </label>

          <button
            type="submit"
            disabled={saveMutation.isPending}
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {saveMutation.isPending ? "Saving…" : "Save profile"}
          </button>
        </form>

        {form.display_name ? (
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-6">
            <p className="text-xs uppercase tracking-[0.15em] text-slate-500">Signature preview</p>
            <pre className="mt-3 whitespace-pre-wrap text-sm text-slate-300">
              {`Best regards,\n${form.display_name.trim()}${
                form.linkedin_url.trim() ? `\nLinkedIn: ${form.linkedin_url.trim()}` : ""
              }${form.github_url.trim() ? `\nGitHub: ${form.github_url.trim()}` : ""}`}
            </pre>
          </div>
        ) : null}
      </section>
    </Layout>
  );
}
