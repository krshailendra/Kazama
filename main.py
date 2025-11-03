print("✅ main.py started")

import json
from llm_utils import generate_plan_with_groq

def main():
    print("\n🚀 Welcome to the AI Auto Planner (Groq-Powered)\n")
    print("This tool helps you break a big goal into daily actionable tasks.\n")
    print("Type 'exit' at any prompt to quit.\n")

    while True:
        goal = input("🎯 Enter your goal: ").strip()
        if goal.lower() == "exit":
            break

        deadline = input("📅 Enter your deadline (YYYY-MM-DD): ").strip()
        if deadline.lower() == "exit":
            break

        daily_hours = input("⏰ Enter daily available hours: ").strip()
        if daily_hours.lower() == "exit":
            break

        mode = input("📘 Mode (study/project/practice): ").strip().lower()
        if mode.lower() == "exit":
            break
        if mode not in ["study", "project", "practice"]:
            mode = "project"  # default fallback

        print("\n🧠 Generating your personalized plan using Groq LLM... Please wait...\n")

        try:
            tasks = generate_plan_with_groq(
                goal=goal,
                deadline=deadline,
                daily_hours=float(daily_hours),
                mode=mode
            )
            print("\n✅ Plan generated successfully!\n")

            print(json.dumps(tasks, indent=2, ensure_ascii=False))

            # optional: save to file
            save = input("\n💾 Save plan as JSON file? (y/n): ").strip().lower()
            if save == "y":
                filename = "plan_output.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
                print(f"📁 Saved as {filename}\n")

        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            continue

if __name__ == "__main__":
    main()
