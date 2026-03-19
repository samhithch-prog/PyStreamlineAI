import Link from "next/link";

type HomePageProps = {
  searchParams?: Record<string, string | string[] | undefined>;
};

function getFirstQueryValue(value: string | string[] | undefined) {
  if (Array.isArray(value)) {
    return String(value[0] || "").trim();
  }
  return String(value || "").trim();
}

export default function HomePage({ searchParams }: HomePageProps) {
  const query = new URLSearchParams();
  const candidate = getFirstQueryValue(searchParams?.candidate);
  const role = getFirstQueryValue(searchParams?.role);
  const type = getFirstQueryValue(searchParams?.type);
  const source = getFirstQueryValue(searchParams?.source);
  const launchToken = getFirstQueryValue(searchParams?.launch_token);

  if (candidate) {
    query.set("candidate", candidate);
  }
  if (role) {
    query.set("role", role);
  }
  if (type) {
    query.set("type", type);
  }
  if (source) {
    query.set("source", source);
  }
  if (launchToken) {
    query.set("launch_token", launchToken);
  }
  const interviewHref = query.size > 0 ? `/interview?${query.toString()}` : "/interview";

  return (
    <main className="relative mx-auto flex min-h-screen max-w-6xl flex-col items-center justify-center px-6 py-12">
      <Link
        href="/"
        className="fixed left-4 top-4 z-20 inline-flex items-center sm:left-7 sm:top-6"
        aria-label="ZoSwi Home"
      >
        <img
          src="/zoswi-wordmark.png"
          alt="ZoSwi"
          className="h-10 w-auto sm:h-12"
        />
      </Link>
      <section className="panel w-full p-10 text-center sm:p-14">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200/85">ZoSwi Platform</p>
        <h1 className="mt-4 font-[var(--font-display)] text-4xl font-semibold tracking-tight text-slate-100 sm:text-6xl">
          Live AI Interviewer
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-base text-slate-300">
          High-impact live interview practice with adaptive AI questioning, natural voice conversation, and actionable feedback.
        </p>
        <Link
          href={interviewHref}
          className="mt-8 inline-flex items-center justify-center rounded-xl border border-cyan-200/30 bg-cyan-400/90 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
        >
          Enter Interview Room
        </Link>
        <Link
          href="/recruiter"
          className="ml-3 mt-8 inline-flex items-center justify-center rounded-xl border border-white/25 bg-white/10 px-6 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/20"
        >
          Recruiter Dashboard
        </Link>
      </section>
    </main>
  );
}
