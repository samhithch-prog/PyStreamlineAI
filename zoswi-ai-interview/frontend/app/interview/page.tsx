import { InterviewClient } from "../../components/interview/InterviewClient";

export default function InterviewPage() {
  return (
    <main className="relative mx-auto max-w-[1400px] px-4 py-8 sm:px-6 lg:px-10 lg:py-10">
      <div className="pointer-events-none absolute -top-20 left-6 h-44 w-44 rounded-full bg-cyan-400/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-4 top-20 h-52 w-52 rounded-full bg-emerald-400/20 blur-3xl" />
      <InterviewClient />
    </main>
  );
}
