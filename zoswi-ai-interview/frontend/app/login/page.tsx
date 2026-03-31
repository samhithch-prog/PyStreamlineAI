import Link from "next/link";

export default function LoginPage() {
  return (
    <main className="relative mx-auto flex min-h-screen max-w-6xl flex-col items-center justify-center px-6 py-12">
      <Link
        href="/"
        className="fixed left-4 top-4 z-20 inline-flex items-center sm:left-7 sm:top-6"
        aria-label="ZoSwi Home"
      >
        <img src="/zoswi-wordmark.png" alt="ZoSwi" className="h-10 w-auto sm:h-12" />
      </Link>

      <section className="panel w-full max-w-xl p-8 sm:p-10">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-cyan-200/85">ZoSwi Access</p>
        <h1 className="mt-3 font-[var(--font-display)] text-3xl font-semibold text-slate-100 sm:text-4xl">Login</h1>
        <p className="mt-2 text-sm text-slate-300">Continue to your ZoSwi workspace.</p>

        <form className="mt-5 space-y-3">
          <div>
            <label htmlFor="email" className="text-sm font-semibold text-slate-100">
              Email
            </label>
            <input id="email" type="email" className="soft-input" placeholder="you@company.com" />
          </div>
          <div>
            <label htmlFor="password" className="text-sm font-semibold text-slate-100">
              Password
            </label>
            <input id="password" type="password" className="soft-input" placeholder="********" />
          </div>
          <div className="flex flex-wrap gap-2 pt-2">
            <Link href="/interview" className="primary-btn">
              Enter Interview Room
            </Link>
          </div>
        </form>
      </section>
    </main>
  );
}
