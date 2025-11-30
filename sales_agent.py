import os, json
from datetime import datetime, timedelta,timezone
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
import re
import io
import pdfplumber
import google.generativeai as genai
from dotenv import load_dotenv



rfp_urls = [
    "file:///C:/Users/DELL/vs_code/rfp_ai/rfp_samples/rfp1.html",
    "file:///C:/Users/DELL/vs_code/rfp_ai/rfp_samples/rfp2.html"
]
 
load_dotenv()
GEN_KEY = os.getenv("GEMINI_API_KEY")
if not GEN_KEY:
    raise ValueError("GEMINI_API_KEY missing")
genai.configure(api_key=GEN_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# lightweight functions (pdf/html -> text)
def fetch_to_text(url: str) -> str:
    if url.startswith("file://"):
        path = url.replace("file://", "")
        with open(path, "rb") as f: 
            b = f.read()
        # check PDF signature
        if b[:4] == b"%PDF":
            return extract_pdf_text(b)
        else:
            return b.decode(errors="ignore")
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    ct = r.headers.get("Content-Type","")
    if "pdf" in ct or url.lower().endswith(".pdf"):
        return extract_pdf_text(r.content)
    # html
    return extract_html_text(r.text)

def extract_html_text(html: str) -> str:
    s = BeautifulSoup(html, "html.parser")
    for tag in s(["script","style","noscript"]):
        tag.decompose()
    return s.get_text("\n",strip=True)

def extract_pdf_text(b: bytes) -> str:
    try:
        text=[]
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            for p in pdf.pages:
                txt = p.extract_text()
                if txt:
                    text.append(txt)
        return "\n".join(text)
    except Exception as e:
        return ""

# regex helpers (date/time/submission)
DATE_TIME_PATTERNS = [
    r"(?:last\s+date.*?submission|submission\s+deadline|due\s+date).*?(\d{1,2}/\d{1,2}/\d{4})\s*(?:at\s*([0-9]{3,4}\s*hrs|\d{1,2}:\d{2}\s*(?:AM|PM)?))?",
    r"no\s+later\s+than\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})(?:\s+at\s+([0-9]{1,2}:\d{2}\s*(?:AM|PM)?|[0-9]{3,4}\s*hrs))?"
]

def try_parse_date(raw):
    from dateutil import parser
    try:
        dt = parser.parse(raw, dayfirst=False, fuzzy=True)
        return dt
    except:
        return None

def extract_due_and_time(text: str):
    for p in DATE_TIME_PATTERNS:
        m = re.search(p, text, re.IGNORECASE|re.DOTALL)
        if m:
            raw_date = m.group(1)
            raw_time = m.group(2) if m.lastindex>=2 else None
            dt = try_parse_date(raw_date)
            return dt.date().isoformat() if dt else None, raw_time
    return None, None

def extract_submission_method_location(text: str):
    textl = text.lower()
    method = None
    if "cpp portal" in textl or "cppp" in textl or "eprocure" in textl:
        method = "CPP Portal"
    elif "email" in textl:
        method = "Email"
    elif "tender box" in textl or "physical copies" in textl or "dropped at" in textl:
        method = "Physical"
    else:
        method = "Not specified"
    # location snippet after keywords
    loc = None
    m = re.search(r"(?:tender box|dropped at|delivered to|mailed to|submit to)[:\s\-]*\n?(.{1,300})", text, re.IGNORECASE|re.DOTALL)
    if m:
        loc = m.group(1).split("\n\n")[0].strip()
    return method, loc

# LLM summarizer (Gemini)
def summarize_with_gemini(text: str) -> str:
    prompt = f"""
Extract RFP structured fields and short summary. Return JSON only with keys:
title, issuing_authority, submission_due_date, submission_time, submission_method, submission_location, scope_summary, items (list of descriptions).
RFP TEXT:
{text}
"""
    resp = model.generate_content(model="gemini-2.0-flash", contents=prompt)
    # resp.text is plain; try parse JSON
    try:
        return resp.text
    except:
        return resp.text

# Node entrypoint (LangGraph will call this)
def run_sales_node(urls: list):
    results=[]
    cutoff = (datetime.now(timezone.utc).date() + timedelta(days=90)).isoformat()
    for url in urls:
        try:
            raw = fetch_to_text(url)
        except Exception as e:
            continue
        due_date, due_time = extract_due_and_time(raw)
        method, location = extract_submission_method_location(raw)
        # Use LLM for structured extract if keys missing
        # For speed you can skip LLM if due_date found
        summary_text = None
        if not due_date:
            structured_json_str = summarize_with_gemini(raw)
            # try parse JSON
            try:
                j = json.loads(structured_json_str)
                due_date = j.get("submission_due_date") or due_date
                due_time = j.get("submission_time") or due_time
                method = method or j.get("submission_method")
                location = location or j.get("submission_location")
                summary_text = j.get("scope_summary")
                items = j.get("items",[])
            except Exception:
                summary_text = raw[:400]
                items = []
        else:
            summary_text = raw[:400]
            # naive item extraction: lines with 'km' or 'sqmm' or 'core'
            items=[]
            for line in raw.splitlines():
                if re.search(r"\b(km|sqmm|core|Core|Cores|pair)\b", line, re.IGNORECASE):
                    items.append({"description":line.strip()})
        # filter by due_date
        if not due_date:
            continue
        try:
            if due_date > cutoff: 
                continue
        except: 
            pass
        results.append({
            "rfp_id": os.path.basename(url),
            "url": url,
            "due_date": due_date,
            "due_time": due_time,
            "submission_method": method,
            "submission_location": location,
            "scope_summary": summary_text,
            "items": items,
            "raw_text_snippet": raw[:1000]
        })
    # pick earliest
    if not results: return None
    results_sorted = sorted(results, key=lambda r: r["due_date"])
    return results_sorted[0]









# import requests
# from bs4 import BeautifulSoup
# from datetime import datetime,timedelta

# rfp_urls = [
#     "file:///C:/Users/DELL/vs_code/rfp_ai/rfp_samples/rfp1.html",
#     "file:///C:/Users/DELL/vs_code/rfp_ai/rfp_samples/rfp2.html"
# ]

# def load_rfp(file_url):
#     # convert file:/// to normal url
#     path = file_url.replace("file:///","")

#     with open(path,"r",encoding='utf-8') as f:
#         return f.read()




# def get_rfps_due_soon():
#     selected_rfps = []
#     today = datetime.today()
#     cutoff = today + timedelta(days = 90) #next 3 months

#     for url in rfp_urls:
#         html = load_rfp(url)
#         soup = BeautifulSoup(html,"html.parser")

#         rfp_id = soup.find("h1").text.strip()

#           # Extract due date paragraph
#         due_tag = soup.find("p", string=lambda x: x and "Submission Due Date" in x)

#         if not due_tag:
#             print(f"Warning: No due date found in {url}")
#             continue

#         due_text = due_tag.text.replace("Submission Due Date:", "").strip()

#         # Parse the date
#         try:
#             due_date = datetime.strptime(due_text, "%Y-%m-%d")
#         except ValueError:
#             print(f"Invalid date format in {url}: {due_text}")
#             continue

#         #filter by due date
#         if due_date <=cutoff:
#             selected_rfps.append({
#                 "rfp_id":rfp_id,
#                 "due_date":due_date.strftime("%Y-%m-%d"),
#                 "url":url
#             })

#     return selected_rfps

# def summarize_rfps(selected_rfps):
#     summaries = []

#     for rfp in selected_rfps:
#         html = load_rfp(rfp['url'])
#         soup = BeautifulSoup(html, 'html.parser')
        
#         #extract title
#         title = soup.find('h1').text.strip() if soup.find("h1") else "Unkown RFP"

#         #extract full description 
#         paragraphs = soup.find_all('p')
#         description = "No description found"

#         if len(paragraphs) > 1:
#             description = paragraphs[1].text.strip()

#         summaries.append({
#             "rfp_title":title,
#             "due_date":rfp["due_date"],
#             "url":rfp["url"],
#             "summary":description
#         })
#     return summaries

# # //chose rfp with the earliest due datetime
# def choose_rfp_to_process(summaries):
#     #sort by due date(earliest first)
#     sorted_list = sorted(
#         summaries,
#         key=lambda x: datetime.strptime(x["due_date"],"%Y-%m-%d")
#     )

#     #choose the earliest due RFP
#     return sorted_list[0] if sorted_list else None

# def run_sales_agent():
#     #step 1 - filter RFPs by date
#     selected_rfps = get_rfps_due_soon()

#     #step 2 - summarize them
#     summaries = summarize_rfps(selected_rfps)

#     #step 3 - choose one
#     chosen = choose_rfp_to_process(summaries)

#     return chosen