// API call for generating plan in Rade
export async function generatePlan(task: string): Promise<string> {
  // TODO: Replace the base URL if needed for backend integration
  const resp = await fetch("/api/generate_plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task }),
  });
  if (!resp.ok) {
    // TODO: Fine-tune error handling based on actual backend error payloads
    throw new Error("Backend error");
  }
  // TODO: Adjust this to fit your backend's response structure.
  const data = await resp.json();
  return data.plan || JSON.stringify(data);
}
