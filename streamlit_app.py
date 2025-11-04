# streamlit_app.py
import streamlit as st
from datetime import date, datetime, timedelta
import json
import os
import uuid
from typing import List, Dict, Any

# Import your existing modules (must be in same project)
from llm_utils import generate_plan_with_groq
from import_utils import parse_sheet_input
#from scheduler import schedule_tasks_greedy, reschedule_on_partial_completion
from import_utils import parse_sheet_input
st.set_page_config(page_title="AI Goal Planner", layout="wide")
sheet_url = st.text_input("Paste Striver A2Z or other DSA sheet URL:")

if sheet_url:
    try:
        with st.spinner("Fetching topics from sheet..."):
            tasks_list = parse_sheet_input(sheet_url)
        st.success(f"Found {len(tasks_list)} topics!")
        st.dataframe(tasks_list)
    except Exception as e:
        st.error(f"Error: {e}")


# ---------- Constants & Data file helpers ----------
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "tasks.json")

def ensure_data_file():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if not os.path.exists(DATA_FILE):
        initial = {"goals": []}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=2, ensure_ascii=False)

def load_data() -> Dict[str, Any]:
    ensure_data_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: Dict[str, Any]):
    ensure_data_file()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------- Utility helpers ----------
def months_range_to_days(duration_range: str) -> int:
    # convert "2 months", "2-3 months", "3" etc -> use upper bound and multiply by 30
    txt = duration_range.lower().replace(" ", "")
    if "-" in txt:
        parts = txt.split("-")
        try:
            high = int(parts[-1].replace("months", "").replace("month",""))
            return high * 30
        except:
            return 60
    else:
        try:
            months = int(txt.replace("months", "").replace("month", ""))
            return months * 30
        except:
            return 60

def iso(d: date) -> str:
    return d.isoformat()

def parse_iso(dstr: str) -> date:
    return date.fromisoformat(dstr)

def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"

# ---------- Simple Greedy Scheduler ----------
def schedule_tasks_greedy(tasks: List[Dict], start_date: date, capacity_per_day: float, deadline: date) -> Dict[date, List[Dict]]:
    """
    A lightweight greedy scheduler to distribute tasks between start_date and deadline.
    Each task is assigned sequentially until its estimated_hours are filled.
    """
    cal = {}
    current_date = start_date
    remaining = []
    for idx, t in enumerate(tasks):
        remaining.append({
            "task_idx": idx,
            "hours_left": float(t["estimated_hours"]),
            "title": t["title"]
        })

    while remaining and current_date <= deadline:
        cap = capacity_per_day
        cal[current_date] = []
        still_left = []
        for r in remaining:
            if cap <= 0:
                still_left.append(r)
                continue
            assign = min(r["hours_left"], cap)
            cal[current_date].append({"task_idx": r["task_idx"], "hours": assign})
            r["hours_left"] -= assign
            cap -= assign
            if r["hours_left"] > 0:
                still_left.append(r)
        remaining = still_left
        current_date += timedelta(days=1)

    return cal


# ---------- Scheduling glue ----------
def schedule_goal_tasks(tasks: List[Dict], start_date: date, capacity_per_day: float, deadline: date) -> Dict[str, List[Dict]]:
    """
    tasks: list of dicts {"id","title","estimated_hours","priority","hours_done"}
    returns calendar mapping ISO date -> list of assignments: {"task_id","hours", optional "conflict"}
    """
    # prepare scheduler input order: use the same order as tasks list
    sched_input = [{"title": t["title"], "estimated_hours": t["estimated_hours"], "priority": t.get("priority", 5)} for t in tasks]
    cal = schedule_tasks_greedy(sched_input, start_date, capacity_per_day, deadline)
    # cal keys are date objects; convert to iso and map task_idx -> task_id
    out = {}
    for d, assigns in cal.items():
        day_iso = iso(d)
        out.setdefault(day_iso, [])
        for a in assigns:
            if "task_idx" in a:
                idx = a["task_idx"]
                task_id = tasks[idx]["id"]
                rec = {"task_id": task_id, "hours": a["hours"]}
                if a.get("conflict"):
                    rec["conflict"] = True
                out[day_iso].append(rec)
            elif "task_id" in a:
                out[day_iso].append({"task_id": a["task_id"], "hours": a["hours"]})
    return out

def reschedule_on_partial_completion(assignments: Dict[date, List[Dict]], tasks: List[Dict], capacity_per_day: float,
                                     start_from: date, deadline: date) -> Dict[date, List[Dict]]:
    """
    Re-schedule remaining work starting from `start_from`.
    Keeps already-done hours into account.
    """
    remaining_tasks = []
    for idx, t in enumerate(tasks):
        done = t.get("hours_done", 0.0)
        left = max(0.0, float(t["estimated_hours"]) - done)
        if left > 0:
            remaining_tasks.append({
                "task_idx": idx,
                "estimated_hours": left,
                "priority": t.get("priority", 5)
            })
    return schedule_tasks_greedy(remaining_tasks, start_from, capacity_per_day, deadline)


def rebuild_assignments_dict_from_storage(goal: Dict) -> Dict[str, List[Dict]]:
    """
    goal holds 'assignments' mapping iso-date -> list of {"task_id","hours"}
    This returns same structure (ensures consistent shape)
    """
    return goal.get("assignments", {})

def reschedule_from_tomorrow(goal: Dict, capacity_per_day: float):
    """
    Recompute assignments for dates >= tomorrow using reschedule_on_partial_completion.
    Mutates and saves the goal assignments in storage.
    """
    # prepare assignments: convert iso->date keys to date objects in required format
    data = load_data()
    goals = data["goals"]
    # find current goal in data (by id)
    # caller must ensure goal is a reference to storage object
    # we'll build inputs for rescheduler
    assignments_storage = goal.get("assignments", {})  # iso->list
    assignments_for_sched = {}
    for dstr, assigns in assignments_storage.items():
        try:
            dobj = parse_iso(dstr)
            # map to expected dict form {date: [{"task_id":id,"hours":h}, ...]}
            assignments_for_sched[dobj] = [{"task_id": a["task_id"], "hours": a["hours"]} for a in assigns]
        except Exception:
            continue

    # build tasks list expected by rescheduler with hours_done
    tasks_storage = goal.get("tasks", [])
    tasks_for_sched = []
    for t in tasks_storage:
        tasks_for_sched.append({
            "title": t["title"],
            "estimated_hours": t["estimated_hours"],
            "priority": t.get("priority", 5),
            "hours_done": t.get("hours_done", 0.0)
        })

    # start from tomorrow
    start_from = date.today() + timedelta(days=1)
    deadline = parse_iso(goal["deadline"])
    new_calendar = reschedule_on_partial_completion(assignments_for_sched, tasks_for_sched, capacity_per_day, start_from, deadline)
    # new_calendar has date keys, convert to iso and task_idx mapping -> task_id
    new_assignments = {}
    for d, assigns in new_calendar.items():
        d_iso = iso(d)
        new_assignments.setdefault(d_iso, [])
        for a in assigns:
            if "task_id" in a:
                new_assignments[d_iso].append({"task_id": a["task_id"], "hours": a["hours"]})
            elif "task_idx" in a:
                tid = tasks_storage[a["task_idx"]]["id"]
                new_assignments[d_iso].append({"task_id": tid, "hours": a["hours"]})
    # update goal assignments
    goal["assignments"] = new_assignments
    # persist
    data = load_data()
    for i, g in enumerate(data["goals"]):
        if g["id"] == goal["id"]:
            data["goals"][i] = goal
            break
    save_data(data)

# ---------- High-level operations ----------
def create_goal_autoplan(goal_text: str, duration_range: str, daily_hours: float, mode: str) -> Dict:
    days = months_range_to_days(duration_range)
    deadline_date = date.today() + timedelta(days=days)
    # call LLM to generate tasks
    tasks_from_llm = generate_plan_with_groq(goal=goal_text, deadline=str(deadline_date), daily_hours=float(daily_hours), mode=mode)
    # build goal object
    goal_obj = {
        "id": gen_id("goal"),
        "title": goal_text[:140],
        "description": goal_text,
        "created_at": iso(date.today()),
        "deadline": iso(deadline_date),
        "mode": "autoplan",
        "tasks": [],
        "assignments": {}
    }
    # create task entries
    for t in tasks_from_llm:
        task_obj = {
            "id": gen_id("task"),
            "title": t["title"],
            "description": t.get("description",""),
            "estimated_hours": float(t.get("estimated_hours", 2.0)),
            "priority": int(t.get("priority", 5)),
            "status": "planned",
            "hours_done": 0.0
        }
        goal_obj["tasks"].append(task_obj)
    # initial scheduling
    assignments = schedule_goal_tasks(goal_obj["tasks"], date.today(), daily_hours, parse_iso(goal_obj["deadline"]))
    goal_obj["assignments"] = assignments
    # persist
    data = load_data()
    data["goals"].append(goal_obj)
    save_data(data)
    return goal_obj

def create_goal_from_sheet(sheet_url: str, duration_range: str, daily_hours: float) -> Dict:
    days = months_range_to_days(duration_range)
    deadline_date = date.today() + timedelta(days=days)
    parsed = parse_sheet_input(sheet_url)
    if not parsed:
        raise RuntimeError("No tasks parsed from sheet")
    goal_obj = {
        "id": gen_id("goal"),
        "title": f"Imported: {sheet_url[:100]}",
        "description": sheet_url,
        "created_at": iso(date.today()),
        "deadline": iso(deadline_date),
        "mode": "import",
        "tasks": [],
        "assignments": {}
    }
    for t in parsed:
        task_obj = {
            "id": gen_id("task"),
            "title": t["title"],
            "description": t.get("description",""),
            "estimated_hours": float(t.get("estimated_hours", 2.0)),
            "priority": int(t.get("priority", 5)),
            "status": "planned",
            "hours_done": 0.0
        }
        goal_obj["tasks"].append(task_obj)
    assignments = schedule_goal_tasks(goal_obj["tasks"], date.today(), daily_hours, parse_iso(goal_obj["deadline"]))
    goal_obj["assignments"] = assignments
    data = load_data()
    data["goals"].append(goal_obj)
    save_data(data)
    return goal_obj

# ---------- Streamlit UI ----------

st.title("🧭 AI Goal Planner — Autoplan & Import (Groq)")

# Sidebar: create or import
with st.sidebar:
    st.header("Create new plan")
    mode = st.radio("Mode", ["Autoplan (LLM)", "Import sheet (URL)"])
    if mode == "Autoplan (LLM)":
        goal_text = st.text_area("Describe your goal (e.g. 'learn DSA and solve 200 problems')", height=120)
        duration_choice = st.selectbox("Duration range", ["1 month", "2 months", "2-3 months", "3 months", "4 months"], index=2)
        daily_hours_input = st.number_input("Daily available hours", value=3.0, min_value=0.5, max_value=16.0, step=0.5)
        plan_style = st.selectbox("Style", ["study", "project", "practice"])
        generate_btn = st.button("🧠 Generate Autoplan")
    else:
        sheet_url_input = st.text_input("Sheet / CSV URL")
        duration_choice = st.selectbox("Duration range (import)", ["1 month", "2 months", "2-3 months", "3 months", "4 months"], index=2, key="import_range")
        daily_hours_input = st.number_input("Daily available hours (import)", value=3.0, min_value=0.5, max_value=16.0, step=0.5, key="import_hours")
        import_btn = st.button("📥 Import and schedule")

# Load stored data
data = load_data()
goals = data.get("goals", [])

# Handle create actions
if mode == "Autoplan (LLM)" and generate_btn:
    if not goal_text or len(goal_text.strip()) < 6:
        st.error("Please write a clear goal (at least a few words).")
    else:
        with st.spinner("Asking the LLM to generate a plan..."):
            try:
                g = create_goal_autoplan(goal_text.strip(), duration_choice, daily_hours_input, plan_style)
                st.success(f"Created goal: {g['title']} with {len(g['tasks'])} tasks. Deadline approx {g['deadline']}")
                # refresh local data var
                data = load_data()
                goals = data.get("goals", [])
            except Exception as e:
                st.error(f"Autoplan failed: {e}")

if mode == "Import sheet (URL)" and import_btn:
    if not sheet_url_input or sheet_url_input.strip() == "":
        st.error("Provide a sheet URL")
    else:
        with st.spinner("Parsing the sheet and creating plan..."):
            try:
                g = create_goal_from_sheet(sheet_url_input.strip(), duration_choice, daily_hours_input)
                st.success(f"Imported goal: {g['title']} with {len(g['tasks'])} tasks. Deadline approx {g['deadline']}")
                data = load_data()
                goals = data.get("goals", [])
            except Exception as e:
                st.error(f"Import failed: {e}")

# Show existing goals selector
st.markdown("---")
st.header("Manage goals")
if not goals:
    st.info("No goals yet — create one from the sidebar.")
else:
    goal_map = {g["title"]: g for g in goals}
    selected_title = st.selectbox("Select goal", ["(choose)"] + [g["title"] for g in goals])
    if selected_title != "(choose)":
        goal = goal_map[selected_title]
        st.subheader(goal["title"])
        st.write("Description:", goal.get("description",""))
        st.write("Deadline (approx):", goal["deadline"])
        # summary progress
        total_est = sum(t["estimated_hours"] for t in goal["tasks"])
        done_hours = sum(t.get("hours_done", 0.0) for t in goal["tasks"])
        progress_frac = min(1.0, done_hours / max(1.0, total_est))
        st.progress(progress_frac)
        st.write(f"Tasks: {len(goal['tasks'])} — Estimated total hours: {total_est:.1f} — Done hours: {done_hours:.1f}")

        # Option to force rebalance from tomorrow
        if st.button("🔁 Rebalance schedule (from tomorrow)"):
            try:
                reschedule_from_tomorrow(goal, daily_hours_input)
                st.success("Rebalanced from tomorrow.")
                data = load_data(); goal = [g for g in data["goals"] if g["id"] == goal["id"]][0]
            except Exception as e:
                st.error(f"Rebalance failed: {e}")

        st.markdown("### Tasks & Today's Plan")
        today_iso = iso(date.today())
        today_assigns = goal.get("assignments", {}).get(today_iso, [])
        if not today_assigns:
            st.info("No tasks scheduled for today for this goal.")
        else:
            # show tasks for today with ability to mark hours done
            for a in today_assigns:
                # find task object
                t = next((x for x in goal["tasks"] if x["id"] == a["task_id"]), None)
                if not t:
                    continue
                col1, col2, col3 = st.columns([6,2,2])
                with col1:
                    st.markdown(f"**{t['title']}**  \nEst: {a['hours']} h — Done: {t.get('hours_done',0.0)}/{t['estimated_hours']} h — Status: {t.get('status','planned')}")
                    if t.get("description"):
                        st.write(t["description"])
                with col2:
                    add_done = st.number_input(f"Hours done for {t['id']}", min_value=0.0, max_value=float(a['hours']), step=0.25, key=f"{t['id']}_done")
                with col3:
                    if st.button("Save", key=f"save_{t['id']}"):
                        # update task progress in storage
                        data = load_data()
                        # find goal & task in storage
                        for gi, gg in enumerate(data["goals"]):
                            if gg["id"] == goal["id"]:
                                for ti, tt in enumerate(gg["tasks"]):
                                    if tt["id"] == t["id"]:
                                        new_done = min(tt["estimated_hours"], tt.get("hours_done", 0.0) + float(add_done))
                                        data["goals"][gi]["tasks"][ti]["hours_done"] = new_done
                                        data["goals"][gi]["tasks"][ti]["status"] = "done" if new_done >= tt["estimated_hours"] else "in_progress"
                                        break
                                break
                        save_data(data)
                        # trigger reschedule from tomorrow for this specific goal
                        data = load_data()
                        goal_ref = next((g for g in data["goals"] if g["id"] == goal["id"]), None)
                        try:
                            reschedule_from_tomorrow(goal_ref, daily_hours_input)
                            save_data(data)  # reschedule_from_tomorrow already saves, but ensure persist
                            st.success("Progress saved and schedule rescheduled from tomorrow.")
                            # refresh local goal var
                            data = load_data()
                            goals = data["goals"]
                            goal = next((g for g in goals if g["id"] == goal["id"]), goal)
                        except Exception as e:
                            st.error(f"Reschedule error: {e}")

        st.markdown("### Next 7 days summary")
        # show summary for next 7 days across this goal
        today = date.today()
        for i in range(0, 7):
            d = today + timedelta(days=i)
            d_iso = iso(d)
            assigns = goal.get("assignments", {}).get(d_iso, [])
            total_h = sum(a["hours"] for a in assigns)
            st.write(f"{d_iso}: {len(assigns)} tasks — {total_h:.2f} h")

# Footer
st.markdown("---")
st.write("Local JSON storage: `data/tasks.json` — you can back this file up if needed.")
st.write("Built with Groq LLM autoplan + local scheduler. Adjust task estimates if needed.")
