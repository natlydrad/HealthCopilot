import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export default function Insights() {
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

        // extract date from report header, e.g. "(2025-10-01 – 2025-10-07)"
        const match = rText.match(/\((\d{4}-\d{2}-\d{2})/);
        if (match) setLastRun(match[1]);
      } catch (err) {
        console.error("Failed to load Markdown:", err);
      }
    }
    loadReports();
  }, []);

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-12">
      <h1 className="text-3xl font-bold mb-2">📊 Insights Dashboard</h1>
      {lastRun && (
        <p className="text-gray-600 mb-8">Last pipeline run: {lastRun}</p>
      )}

      <section>
        <h2 className="text-2xl font-semibold mb-4">Weekly Health Report</h2>
        <div className="prose max-w-none">
          <ReactMarkdown>{report}</ReactMarkdown>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold mb-4">Current Experiment Plan</h2>
        <div className="prose max-w-none">
          <ReactMarkdown>{experiment}</ReactMarkdown>
        </div>
      </section>
    </div>
  );
}
