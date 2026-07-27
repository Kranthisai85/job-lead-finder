const emptyForm = {
  name: "",
  website: "",
  description: "",
  industry: "",
  source: ""
};

export default function CompanyModal({ open, mode, initialValues, onClose, onSubmit, isSubmitting }) {
  if (!open) {
    return null;
  }

  const formId = "company-form";

  function handleSubmit(event) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    onSubmit({
      name: formData.get("name"),
      website: formData.get("website"),
      description: formData.get("description") || null,
      industry: formData.get("industry") || null,
      source: formData.get("source") || null
    });
  }

  const values = { ...emptyForm, ...initialValues };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4">
      <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl">
        <div className="mb-6 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">
            {mode === "edit" ? "Edit Company" : "Create Company"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-slate-400 hover:bg-slate-800 hover:text-white"
          >
            Close
          </button>
        </div>

        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">Company Name</span>
            <input
              name="name"
              required
              defaultValue={values.name}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">Website</span>
            <input
              name="website"
              required
              defaultValue={values.website}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">Description</span>
            <textarea
              name="description"
              rows={3}
              defaultValue={values.description}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">Industry</span>
            <input
              name="industry"
              defaultValue={values.industry}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none focus:border-sky-500"
            />
          </label>

          <label className="block space-y-1 text-sm">
            <span className="text-slate-300">Source</span>
            <input
              name="source"
              defaultValue={values.source}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-white outline-none focus:border-sky-500"
            />
          </label>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
