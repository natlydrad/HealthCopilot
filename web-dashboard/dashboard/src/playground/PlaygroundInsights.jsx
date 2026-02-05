import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export default function PlaygroundInsights() {
  const [report, setReport] = useState("");
  const [experiment, setExperiment] = useState("");
  const [lastRun, setLastRun] = useState("");

  useEffect(() => {
    async function loadReports() {
      try {
        const [rResp, eResp] = await Promise.all([
          fetch("/reports/weekly_report_latest.md"),
          fetch("/reports/experiment_plan_latest.md"),
        ]);
        const [rText, eText] = await Promise.all([rResp.text(), eResp.text()]);
        setReport(rText);
        setExperiment(eText);
        const match = rText.match(/\((\d{4}-\d{2}-\d{2})/);
        if (match) setLastRun(match[1]);
      } catch (err) {
        console.error("Failed to load Markdown:", err);
      }
    }
    loadReports();
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <div>
        <h1 className="mb-2 text-2xl font-semibold text-stone-800">Insights</h1>
        {lastRun && (
          <p className="text-sm text-stone-500">Last pipeline run: {lastRun}</p>
        )}
      </div>

      <section className="rounded-3xl border border-amber-200/60 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-stone-700">Weekly Health Report</h2>
        <div className="prose prose-stone max-w-none prose-headings:text-stone-800 prose-p:text-stone-600">
          <ReactMarkdown>{report}</ReactMarkdown>
        </div>
      </section>

      <section className="rounded-3xl border border-amber-200/60 bg-white p-6 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-stone-700">Current Experiment Plan</h2>
        <div className="prose prose-stone max-w-none prose-headings:text-stone-800 prose-p:text-stone-600">
          <ReactMarkdown>{experiment}</ReactMarkdown>
        </div>
      </section>
    </div>
  );
}
