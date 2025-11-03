import requests
import pandas as pd
from bs4 import BeautifulSoup
import re

def parse_sheet_input(sheet_url: str):
    """
    Supports:
    - Google Sheets / CSV links
    - Striver A2Z sheet (TakeUForward)
    - Any website-based table
    """

    tasks = []

    # --- CASE 1: Striver A2Z Sheet (auto-detect by URL) ---
    if "takeuforward" in sheet_url.lower() or "a2z" in sheet_url.lower():
        print("Detected Striver A2Z Sheet – fetching structured data from GitHub...")
        try:
            # Striver A2Z has a maintained CSV version on GitHub
            csv_url = "https://raw.githubusercontent.com/striver79/DSA-Sheet/master/A2Z%20DSA%20Course/Striver%20A2Z%20DSA%20Sheet.csv"
            df = pd.read_csv(csv_url)
            for _, row in df.iterrows():
                title = str(row.get("Problem Name") or row.get("Title") or row.get("Problem") or "").strip()
                if not title:
                    continue
                topic = str(row.get("Topic") or "").strip()
                link = str(row.get("Link") or row.get("Problem Link") or "").strip()
                tasks.append({
                    "title": title,
                    "description": topic,
                    "estimated_hours": 1.5,
                    "priority": 5,
                    "link": link
                })
            if tasks:
                return tasks
        except Exception as e:
            print("Error fetching Striver A2Z CSV:", e)
            return []

    # --- CASE 2: Google Sheet / direct CSV ---
    if "docs.google.com" in sheet_url or sheet_url.endswith(".csv"):
        try:
            df = pd.read_csv(sheet_url)
            for _, row in df.iterrows():
                title = str(row.get("Title") or row.get("Problem") or row.get("Task") or "").strip()
                if not title:
                    continue
                desc = str(row.get("Description") or row.get("Topic") or "").strip()
                tasks.append({
                    "title": title,
                    "description": desc,
                    "estimated_hours": 2.0,
                    "priority": 5
                })
            if tasks:
                return tasks
        except Exception as e:
            print("CSV/Sheet parsing failed:", e)

    # --- CASE 3: Website table (basic fallback) ---
    try:
        res = requests.get(sheet_url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.find_all("tr")

        for tr in rows:
            cols = tr.find_all(["td", "th"])
            if len(cols) < 1:
                continue
            title = cols[0].get_text(strip=True)
            link_tag = cols[0].find("a")
            link = link_tag["href"] if link_tag else ""
            desc = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            if title:
                tasks.append({
                    "title": title,
                    "description": desc,
                    "estimated_hours": 2.0,
                    "priority": 5,
                    "link": link
                })
    except Exception as e:
        print("Website parsing failed:", e)

    return tasks
