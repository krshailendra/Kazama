import { useState } from "react";
// import reactLogo from './assets/react.svg'
// import viteLogo from '/vite.svg'
import "./App.css";
import { generatePlan } from "./services/api";

function App() {
  const [task, setTask] = useState("");
  const [plan, setPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGeneratePlan = async () => {
    if (!task.trim()) return;
    setLoading(true);
    setError(null);
    setPlan(null);
    try {
      const respPlan = await generatePlan(task);
      setPlan(respPlan);
    } catch (err: any) {
      setError("Failed to generate plan.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-white flex flex-col items-center px-4">
      {/* Header */}
      <header className="w-full max-w-md py-8 flex justify-center">
        <h1 className="text-4xl font-bold tracking-tight text-indigo-600 drop-shadow-sm">
          Rade
        </h1>
      </header>

      {/* Task Input Section */}
      <section
        className="w-full max-w-md flex flex-col items-center justify-center grow"
        style={{ minHeight: "30vh" }}
      >
        <div className="bg-gray-100 rounded-2xl shadow-lg w-full flex flex-col items-center py-8 px-4">
          <label
            htmlFor="taskInput"
            className="block mb-4 text-lg font-medium text-gray-900 text-center"
          >
            Enter your main goal or task
          </label>
          <div className="flex w-full gap-2 flex-col sm:flex-row">
            <input
              id="taskInput"
              className="border border-gray-300 rounded-lg px-4 py-2 w-full focus:outline-none focus:ring-2 focus:ring-indigo-400 text-base"
              placeholder="e.g., Finish project proposal"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              disabled={loading}
            />
            <button
              className="bg-indigo-500 text-white px-6 py-2 rounded-lg shadow hover:bg-indigo-600 transition-colors disabled:bg-indigo-200 disabled:cursor-not-allowed min-w-[120px]"
              onClick={handleGeneratePlan}
              disabled={loading || !task.trim()}
            >
              {loading ? (
                <span className="inline-flex items-center">
                  <Spinner /> Generating…
                </span>
              ) : (
                "Generate Plan"
              )}
            </button>
          </div>
          {error && <p className="text-red-500 mt-4">{error}</p>}
        </div>
      </section>
      {/* Plan output Section */}
      <section className="w-full max-w-md my-8">
        {loading && !plan && (
          <div className="bg-gray-50 border border-gray-200 rounded-lg shadow p-6 mt-2 flex justify-center items-center min-h-[80px]">
            <Spinner />
          </div>
        )}
        {plan && (
          <div className="bg-green-50 border border-green-200 rounded-lg shadow-lg p-6 whitespace-pre-line text-gray-900 font-medium">
            {plan}
          </div>
        )}
      </section>
      {/* Task List / Reminder Placeholder */}
      <section className="w-full max-w-md mb-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg shadow p-4 text-yellow-900 text-center">
          {/* TODO: Integrate WhatsApp reminders & show planned tasks when backend supports it */}
          Task reminders and detailed breakdowns will appear here soon!
        </div>
      </section>
    </div>
  );
}

function Spinner() {
  return (
    <svg
      className="animate-spin h-6 w-6 text-indigo-500"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      ></circle>
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8z"
      ></path>
    </svg>
  );
}

export default App;
