# streamlit_app.py
import streamlit as st
from datetime import date, datetime, timedelta
import json
import os
import uuid
from typing import List, Dict, Any

# IMPORTANT: set_page_config must be the very first Streamlit command
st.set_page_config(page_title="AI Goal Planner", layout="wide", initial_sidebar_state="expanded")

# Import your existing modules (must be in same project)
from llm_utils import generate_plan_with_groq
from import_utils import parse_sheet_input
# from scheduler import schedule_tasks_greedy, reschedule_on_partial_completion   # kept inside file earlier
# (We keep scheduler functions in this file for prototype)

# ---------- Small UI CSS for a clean mobile-first aesthetic ----------
st.markdown(
    """
    <style>
    /* page background & fonts */
    html, body, [class*="css"]  {
        background: linear-gradient(180deg, #0b1220 0%, #071029 100%);
        color: #e6eef8;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }

    /* content card */
    .card {
        background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
        border: 1px solid rgba(255,255,255,0.04);
        padding: 16px;
        border-radius: 14px;
        box-shadow: 0 6px 18px rgba(2,6,23,0.6);
        margin-bottom: 12px;
    }

    .heading {
        font-size: 1.4rem;
        font-weight: 700;
        color: #8be9fd;
        margin-bottom: 6px;
    }

    .muted {
        color: #9fb3c8;
        font-size: 0.92rem;
    }

    /* small helper */
    .pill {
        background: rgba(139,233,253,0.08);
        color: #8be9fd;
        padding: 4px 8px;
        border-radius: 999px;
        font-size: 0.85rem;
    }

    /* responsive tweaks */
    @media (max-width: 768px) {
        .heading { font-size: 1.15rem; }
        .card { padding: 12px; border-radius: 12px; }
    }

    /* hide Streamlit default footer & header for cleaner demo */
    footer {visibility: hidden;}
    header {visibility: visible;}
    </style>
    """,
    unsafe_allow_html=True,
)

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

# ---------- Simple Greedy Scheduler (kept in-file for prototype) ----------
def schedule_tasks_greedy(tasks: List[Dict], start_date: date, capacity_per_day: float, deadline: date) -> Dict[date, List[Dict]]:
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

def schedule_goal_tasks(tasks: List[Dict], start_date: date, capacity_per_day: float, deadline: date) -> Dict[str, List[Dict]]:
    sched_input = [{"title": t["title"], "estimated_hours": t["estimated_hours"], "priority": t.get("priority", 5)} for t in tasks]
    cal = schedule_tasks_greedy(sched_input, start_date, capacity_per_day, deadline)
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
    # adapt remaining_tasks to scheduler's expected shape: convert "estimated_hours" -> tasks with "estimated_hours"
    # We'll reuse schedule_tasks_greedy by mapping items back to a list of dicts
    pseudo_tasks = [{"title": f"task_{r['task_idx']}", "estimated_hours": r["estimated_hours"], "priority": r["priority"]} for r in remaining_tasks]
    return schedule_tasks_greedy(pseudo_tasks, start_from, capacity_per_day, deadline)

def rebuild_assignments_dict_from_storage(goal: Dict) -> Dict[str, List[Dict]]:
    return goal.get("assignments", {})

def reschedule_from_tomorrow(goal: Dict, capacity_per_day: float):
    data = load_data()
    assignments_storage = goal.get("assignments", {})  # iso->list
    assignments_for_sched = {}
    for dstr, assigns in assignments_storage.items():
        try:
            dobj = parse_iso(dstr)
            assignments_for_sched[dobj] = [{"task_id": a["task_id"], "hours": a["hours"]} for a in assigns]
        except Exception:
            continue

    tasks_storage = goal.get("tasks", [])
    tasks_for_sched = []
    for t in tasks_storage:
        tasks_for_sched.append({
            "title": t["title"],
            "estimated_hours": t["estimated_hours"],
            "priority": t.get("priority", 5),
            "hours_done": t.get("hours_done", 0.0)
        })

    start_from = date.today() + timedelta(days=1)
    deadline = parse_iso(goal["deadline"])
    new_calendar = reschedule_on_partial_completion(assignments_for_sched, tasks_for_sched, capacity_per_day, start_from, deadline)
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
    goal["assignments"] = new_assignments
    data = load_data()
    for i, g in enumerate(data["goals"]):
        if g["id"] == goal["id"]:
            data["goals"][i] = goal
            break
    save_data(data)

# ---------- High-level operations (Autoplan + Import) ----------
def create_goal_autoplan(goal_text: str, duration_range: str, daily_hours: float, mode: str) -> Dict:
    days = months_range_to_days(duration_range)
    deadline_date = date.today() + timedelta(days=days)
    tasks_from_llm = generate_plan_with_groq(goal=goal_text, deadline=str(deadline_date), daily_hours=float(daily_hours), mode=mode)
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
    assignments = schedule_goal_tasks(goal_obj["tasks"], date.today(), daily_hours, parse_iso(goal_obj["deadline"]))
    goal_obj["assignments"] = assignments
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
st.markdown('<div class="heading">🧭 AI Goal Planner — Autoplan & Import (GROQ)</div>', unsafe_allow_html=True)
st.markdown('<div class="muted">Mobile-first demo UI — dark mode. Use sidebar to create or import. Toggle advanced features to hide unfinished items.</div>', unsafe_allow_html=True)
st.write("")  # small spacer

# Sidebar: create or import
with st.sidebar:
    st.markdown("## Create new plan")
    mode = st.radio("Mode", ["Autoplan (LLM)", "Import sheet (URL)"])
    # global toggles for demo
    show_advanced = st.checkbox("Show advanced features (for dev)", value=False)
    hide_unfinished = not show_advanced  # if checkbox unchecked, we hide advanced / unfinished

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

st.markdown("---")
st.markdown('<div class="heading">Manage goals</div>', unsafe_allow_html=True)

if not goals:
    st.info("No goals yet — create one from the sidebar.")
else:
    goal_map = {g["title"]: g for g in goals}
    selected_title = st.selectbox("Select goal", ["(choose)"] + [g["title"] for g in goals])
    if selected_title != "(choose)":
        goal = goal_map[selected_title]
        st.markdown(f'<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;"><div><strong style="font-size:1.05rem">{goal["title"]}</strong><div class="muted">Created: {goal.get("created_at","-")} — Deadline: {goal.get("deadline","-")}</div></div><div class="pill">{goal.get("mode","")}</div></div><div style="margin-top:10px;">{goal.get("description","")}</div></div>', unsafe_allow_html=True)

        # summary progress
        total_est = sum(t["estimated_hours"] for t in goal["tasks"])
        done_hours = sum(t.get("hours_done", 0.0) for t in goal["tasks"])
        progress_frac = min(1.0, done_hours / max(1.0, total_est))
        st.progress(progress_frac)
        st.markdown(f"<div class='muted'>Tasks: {len(goal['tasks'])} — Estimated total: {total_est:.1f} h — Done: {done_hours:.1f} h</div>", unsafe_allow_html=True)

        # Option to force rebalance from tomorrow (hide if unfinished components hidden)
        if show_advanced:
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
                t = next((x for x in goal["tasks"] if x["id"] == a["task_id"]), None)
                if not t:
                    continue
                st.markdown('<div class="card">', unsafe_allow_html=True)
                cols = st.columns([6,2,2])
                with cols[0]:
                    st.markdown(f"**{t['title']}**")
                    st.markdown(f"<div class='muted'>Est: {a['hours']} h — Done: {t.get('hours_done',0.0)}/{t['estimated_hours']} h — Status: {t.get('status','planned')}</div>", unsafe_allow_html=True)
                    if t.get("description"):
                        st.write(t["description"])
                with cols[1]:
                    add_done = st.number_input(f"Hours done for {t['id']}", min_value=0.0, max_value=float(a['hours']), step=0.25, key=f"{t['id']}_done")
                with cols[2]:
                    if st.button("Save", key=f"save_{t['id']}"):
                        data = load_data()
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
                        # reschedule from tomorrow (safe for demo)
                        data = load_data()
                        goal_ref = next((g for g in data["goals"] if g["id"] == goal["id"]), None)
                        try:
                            reschedule_from_tomorrow(goal_ref, daily_hours_input)
                            save_data(data)
                            st.success("Progress saved and schedule rescheduled from tomorrow.")
                            data = load_data()
                            goals = data["goals"]
                            goal = next((g for g in goals if g["id"] == goal["id"]), goal)
                        except Exception as e:
                            st.error(f"Reschedule error: {e}")
                st.markdown('</div>', unsafe_allow_html=True)

        # WhatsApp reminder mock (hide if unfinished)
        st.markdown("### Reminders")
        if hide_unfinished:
            st.info("Reminder integration is hidden for demo. (Enable 'Show advanced features' in sidebar to see the mock.)")
        else:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.write("Send reminder via WhatsApp (demo):")
            cols = st.columns([3,1])
            with cols[0]:
                phone = st.text_input("Phone (e.g. +911234567890)", key="phone_demo")
            with cols[1]:
                if st.button("Send", key="send_whatsapp_demo"):
                    # MOCK: For demo, we show a success; wire this to Twilio/WhatsApp Cloud API later.
                    if not phone or len(phone.strip()) < 6:
                        st.error("Enter a phone number for demo.")
                    else:
                        # real integration point:
                        # call your server endpoint here which uses Twilio or Meta WhatsApp Cloud API
                        st.success(f"Mock WhatsApp message 'Reminder' sent to {phone} (demo).")
            st.markdown('</div>', unsafe_allow_html=True)

        # st.markdown("### Next 7 days summary")
        # today = date.today()
        # for i in range(0, 7):
            # d = today + timedelta(days=i)
            # d_iso = iso(d)
            # assigns = goal.get("assignments", {}).get(d_iso, [])
            # total_h = sum(a["hours"] for a in assigns)
            # st.write(f"{d_iso}: {len(assigns)} tasks — {total_h:.2f} h")

# Footer / Info
# st.markdown("---")
# st.markdown("<div class='muted'>Local JSON storage: <code>data/tasks.json</code> — back up that file if you need to move the prototype.</div>", unsafe_allow_html=True)
# st.markdown("<div class='muted'>Next steps: (1) Hook WhatsApp to Twilio/Meta API on backend; (2) Create a React + Tailwind mobile-first UI for production; (3) Add feature flags to toggle broken/unimplemented UI pieces.</div>", unsafe_allow_html=True)
