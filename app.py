"""University Student Performance Analytics - Flask backend.

All grouping and statistics are calculated here in Python.
"""
import json
import math
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse
from datetime import datetime, timezone
from threading import Lock

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.json.sort_keys = False          # keep universities in first-seen order

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "university_data.json")   # JSON storage file

_students = []                      # working copy in memory, saved to DATA_FILE on every change
_lock = Lock()


# ------------------------------------------------------------- validation
def validate_student(record):
    """Return an error message for an invalid record, or None if it is valid."""
    if not isinstance(record, dict):
        return "Each student record must be an object."
    for field in ("studentId", "university", "score"):
        if field not in record:
            return f"Missing field: {field}."
    sid, uni, score = record["studentId"], record["university"], record["score"]
    if isinstance(sid, bool) or not isinstance(sid, int) or sid <= 0:
        return "studentId must be a positive whole number."
    if not isinstance(uni, str) or not uni.strip():
        return "university must be non-empty text."
    if isinstance(score, bool) or not isinstance(score, (int, float)) \
            or math.isnan(score) or math.isinf(score):
        return "score must be a valid number."
    if not 0 <= score <= 100:
        return "score must be between 0 and 100."
    return None


# --------------------------------------------------------------- core logic
def generate_university_summary(students):
    """Generates university-wise student performance statistics.

    1. Group the records by university name (dictionary keyed by name).
    2. For each group keep: student count, running score total, highest score.
    3. average = total score / number of students, rounded to 2 decimals.
    Invalid records are skipped; empty input returns {}.
    """
    groups = {}
    for record in students or []:
        if validate_student(record) is not None:
            continue
        name = record["university"].strip()
        g = groups.setdefault(name, {"count": 0, "total": 0, "highest": None})
        g["count"] += 1
        g["total"] += record["score"]
        if g["highest"] is None or record["score"] > g["highest"]:
            g["highest"] = record["score"]      # highest tracked per university
    return {
        name: {
            "totalStudents": g["count"],
            "averageScore": round(g["total"] / g["count"], 2),
            "highestScore": g["highest"],
        }
        for name, g in groups.items()
    }


def overall_stats(students):
    """Dashboard cards: totals over all valid records, calculated in Python."""
    valid = [s for s in students or [] if validate_student(s) is None]
    if not valid:
        return {"totalUniversities": 0, "totalStudents": 0,
                "overallAverage": 0, "highestScore": 0}
    scores = [s["score"] for s in valid]
    return {
        "totalUniversities": len({s["university"].strip() for s in valid}),
        "totalStudents": len(valid),
        "overallAverage": round(sum(scores) / len(scores), 2),
        "highestScore": max(scores),
    }


def error(message, status=400):
    return jsonify({"success": False, "error": message}), status


# ------------------------------------------------------- JSON file storage
def _load_data():
    """Read the JSON file; return {} if it is missing or unreadable."""
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _build_document():
    """The JSON document: records + university summary + overall stats (calculated in Python)."""
    return {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "students": list(_students),
        "summary": generate_university_summary(_students),
        "overall": overall_stats(_students),
    }


def _save_data():
    """Write the document to the JSON file (temp file + replace). Call inside the lock."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_build_document(), f, indent=2)
    os.replace(tmp, DATA_FILE)


# On start-up reload previously stored records (valid, unique IDs only).
_seen_ids = set()
for _rec in _load_data().get("students", []):
    if validate_student(_rec) is None and _rec["studentId"] not in _seen_ids:
        _seen_ids.add(_rec["studentId"])
        _students.append(_rec)


# --------------------------------------- receiving records from an API
MAX_API_BYTES = 1_000_000


class ApiFetchError(Exception):
    """The remote API could not be reached or returned unusable data."""


def to_raw_github_url(url):
    """Turn a normal GitHub file page link (github.com/user/repo/blob/branch/file)
    into the raw-file link that returns the file content itself."""
    parsed = urlparse(url)
    if parsed.netloc.lower() in ("github.com", "www.github.com"):
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 5 and parts[2] == "blob":
            user, repo, _, branch, *path = parts
            return f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{'/'.join(path)}"
    return url


def fetch_records(url):
    """Call the API at `url` and return its list of student records.

    The URL must be http(s) and return a JSON array (or {"students": [...]})."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Please paste an API URL.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("API URL must start with http:// or https://")
    url = to_raw_github_url(url)      # GitHub file page -> raw file
    try:
        request_obj = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request_obj, timeout=8) as resp:
            raw = resp.read(MAX_API_BYTES + 1)
    except (urllib.error.URLError, OSError) as exc:      # includes timeouts and HTTP errors
        raise ApiFetchError(f"Could not reach the API: {exc}")
    if len(raw) > MAX_API_BYTES:
        raise ApiFetchError("API response is too large.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiFetchError("API did not return valid JSON.")
    if isinstance(data, dict):
        data = data.get("students")
    if not isinstance(data, list):
        raise ApiFetchError("The API response is not a JSON array of student records (for a GitHub file, use its Raw link).")
    return data


# ------------------------------------------------------------------- routes
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/add-student")
def add_student():
    data = request.get_json(silent=True)
    problem = validate_student(data)
    if problem:
        return error(problem)
    record = {"studentId": data["studentId"], "university": data["university"].strip(),
              "score": data["score"]}
    with _lock:
        if any(s["studentId"] == record["studentId"] for s in _students):
            return error(f"Student ID {record['studentId']} already exists.", 409)
        _students.append(record)
        _save_data()
    return jsonify({"success": True, "message": "Student added.", "student": record}), 201


@app.get("/api/students")
def list_students():
    with _lock:
        return jsonify(list(_students))


@app.delete("/api/students")
def clear_students():
    with _lock:
        _students.clear()
        _save_data()
    return jsonify({"success": True})


@app.delete("/api/students/<int:student_id>")
def delete_student(student_id):
    with _lock:
        for s in _students:
            if s["studentId"] == student_id:
                _students.remove(s)
                _save_data()
                return jsonify({"success": True, "message": "Student removed."})
    return error("Student not found.", 404)


def _read_records():
    """Accept a JSON list (or {"students": [...]}) and validate every record."""
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        data = data.get("students")
    if not isinstance(data, list):
        return None, error("Body must be a JSON array of student records.")
    for i, rec in enumerate(data, start=1):
        problem = validate_student(rec)
        if problem:
            return None, error(f"Record {i}: {problem}")
    return data, None


@app.post("/api/generate-summary")
def generate_summary():
    records, err = _read_records()
    if err:
        return err
    return jsonify(generate_university_summary(records))


@app.post("/api/overall-stats")
def get_overall_stats():
    records, err = _read_records()
    if err:
        return err
    return jsonify(overall_stats(records))


@app.post("/api/fetch-from-api")
def fetch_from_api():
    """Receive records from an API, validate each one and REPLACE all stored records with them."""
    body = request.get_json(silent=True)
    url = body.get("url") if isinstance(body, dict) else None
    if url is not None and not isinstance(url, str):
        return error("url must be text.")
    try:
        records = fetch_records(url)
    except ValueError as exc:
        return error(str(exc))
    except ApiFetchError as exc:
        return error(str(exc), 502)

    # Build the new list first: old data is replaced only if something valid arrives.
    fresh, seen, duplicates, invalid = [], set(), 0, []
    for number, rec in enumerate(records, start=1):
        problem = validate_student(rec)
        if problem:
            invalid.append({"record": number, "error": problem})
        elif rec["studentId"] in seen:
            duplicates += 1                           # repeated ID inside the API data
        else:
            seen.add(rec["studentId"])
            fresh.append({"studentId": rec["studentId"],
                          "university": rec["university"].strip(),
                          "score": rec["score"]})
    if not fresh:
        return error("The API returned no valid student records. Existing data was kept.")
    with _lock:
        removed = len(_students)
        _students[:] = fresh                          # old / default data is removed
        _save_data()
    return jsonify({"success": True, "received": len(records), "added": len(fresh),
                    "removed": removed, "duplicates": duplicates,
                    "invalidCount": len(invalid), "invalid": invalid[:10]})


@app.get("/api/stored-data")
def stored_data():
    """Content of data/university_data.json (rebuilt from memory if the file is missing)."""
    with _lock:
        return jsonify(_load_data() or _build_document())


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
