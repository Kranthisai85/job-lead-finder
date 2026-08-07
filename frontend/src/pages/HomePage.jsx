import Layout from "../components/Layout";

export default function HomePage() {
  return (
    <Layout>
      <section className="mx-auto flex min-h-[70vh] max-w-3xl flex-col items-center justify-center gap-4 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-white">lead-finder</h1>
        <p className="text-slate-300">
          Dashboard scaffold is ready. Use the sidebar to manage companies and review the email
          queue.
        </p>
      </section>
    </Layout>
  );
}
