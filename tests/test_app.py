"""Run with:  python -m unittest discover tests -v"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_module
from app import generate_university_summary as summarize, overall_stats

EXAMPLE = [
    {"studentId": 1, "university": "CHRIST", "score": 85},
    {"studentId": 2, "university": "CHRIST", "score": 70},
    {"studentId": 3, "university": "ABC", "score": 90},
    {"studentId": 4, "university": "ABC", "score": 60},
    {"studentId": 5, "university": "CHRIST", "score": 95},
]
EXPECTED = {
    "CHRIST": {"totalStudents": 3, "averageScore": 83.33, "highestScore": 95},
    "ABC": {"totalStudents": 2, "averageScore": 75.00, "highestScore": 90},
}


def s(i, uni, score):
    return {"studentId": i, "university": uni, "score": score}


class SummaryTests(unittest.TestCase):
    def test_original_example(self):
        self.assertEqual(summarize(EXAMPLE), EXPECTED)

    def test_multiple_students_one_university(self):
        self.assertEqual(summarize([s(1, "X", 50), s(2, "X", 70)]),
                         {"X": {"totalStudents": 2, "averageScore": 60, "highestScore": 70}})

    def test_multiple_universities_not_mixed(self):
        out = summarize([s(1, "A", 10), s(2, "B", 100), s(3, "A", 30)])
        self.assertEqual(out["A"], {"totalStudents": 2, "averageScore": 20, "highestScore": 30})
        self.assertEqual(out["B"], {"totalStudents": 1, "averageScore": 100, "highestScore": 100})

    def test_single_student_university(self):
        self.assertEqual(summarize([s(1, "Solo", 42.5)])["Solo"],
                         {"totalStudents": 1, "averageScore": 42.5, "highestScore": 42.5})

    def test_count_average_highest(self):
        r = summarize(EXAMPLE)["CHRIST"]
        self.assertEqual(r["totalStudents"], 3)
        self.assertAlmostEqual(r["averageScore"], 83.33)
        self.assertEqual(r["highestScore"], 95)

    def test_average_rounded_to_two_decimals(self):
        self.assertEqual(summarize([s(1, "R", 1), s(2, "R", 1), s(3, "R", 2)])["R"]["averageScore"], 1.33)
        self.assertEqual(summarize([s(1, "R", 2), s(2, "R", 2), s(3, "R", 1)])["R"]["averageScore"], 1.67)

    def test_empty_list(self):
        self.assertEqual(summarize([]), {})
        self.assertEqual(summarize(None), {})
        self.assertEqual(overall_stats([]), {"totalUniversities": 0, "totalStudents": 0,
                                             "overallAverage": 0, "highestScore": 0})

    def test_invalid_or_missing_fields_skipped(self):
        bad = [{"studentId": 1, "university": "A"}, {"university": "A", "score": 5},
               {"studentId": 2, "score": 5}, s("x", "A", 5), s(3, "", 5), s(4, "A", "high"),
               s(5, "A", True), s(0, "A", 5), "junk", None]
        self.assertEqual(summarize(bad), {})
        self.assertEqual(list(summarize(bad + [s(9, "A", 50)])), ["A"])

    def test_scores_outside_range_skipped(self):
        out = summarize([s(1, "A", -1), s(2, "A", 101), s(3, "A", 0), s(4, "A", 100)])
        self.assertEqual(out, {"A": {"totalStudents": 2, "averageScore": 50, "highestScore": 100}})

    def test_overall_stats(self):
        self.assertEqual(overall_stats(EXAMPLE), {"totalUniversities": 2, "totalStudents": 5,
                                                  "overallAverage": 80, "highestScore": 95})


class ApiTests(unittest.TestCase):
    def setUp(self):
        app_module.app.testing = True
        app_module.DATA_FILE = os.path.join(tempfile.mkdtemp(), "university_data.json")
        self.c = app_module.app.test_client()
        self.c.delete("/api/students")

    def test_pages(self):
        for path in ("/", "/static/script.js", "/static/style.css"):
            self.assertEqual(self.c.get(path).status_code, 200)

    def test_add_list_delete(self):
        self.assertEqual(self.c.post("/api/add-student", json=s(1, "CHRIST", 85)).status_code, 201)
        self.assertEqual(self.c.get("/api/students").get_json(), [s(1, "CHRIST", 85)])
        self.assertEqual(self.c.delete("/api/students/1").status_code, 200)
        self.assertEqual(self.c.delete("/api/students/1").status_code, 404)
        self.assertEqual(self.c.get("/api/students").get_json(), [])

    def test_duplicate_id_rejected(self):
        self.c.post("/api/add-student", json=s(1, "A", 50))
        self.assertEqual(self.c.post("/api/add-student", json=s(1, "B", 60)).status_code, 409)
        self.assertEqual(len(self.c.get("/api/students").get_json()), 1)

    def test_invalid_records_rejected(self):
        for p in [{}, {"studentId": 1}, s(1, "A", 101), s(1, "A", -1), s(1, "  ", 5),
                  s(1.5, "A", 5), s("1", "A", 5), s(1, "A", "x")]:
            self.assertEqual(self.c.post("/api/add-student", json=p).status_code, 400, p)
        self.assertEqual(self.c.post("/api/add-student", data="nope").status_code, 400)

    def test_generate_summary_original_example(self):
        r = self.c.post("/api/generate-summary", json=EXAMPLE)
        self.assertEqual(r.get_json(), EXPECTED)
        self.assertEqual(self.c.get("/api/students").get_json(), [])   # store untouched

    def test_generate_summary_errors_and_empty(self):
        self.assertEqual(self.c.post("/api/generate-summary", json=[]).get_json(), {})
        self.assertEqual(self.c.post("/api/generate-summary", json=[s(1, "A", 500)]).status_code, 400)
        self.assertEqual(self.c.post("/api/generate-summary", json={"a": 1}).status_code, 400)

    def test_stored_records_summary(self):
        for rec in EXAMPLE:
            self.c.post("/api/add-student", json=rec)
        stored = self.c.get("/api/students").get_json()
        self.assertEqual(self.c.post("/api/generate-summary", json=stored).get_json(), EXPECTED)
        self.assertEqual(self.c.post("/api/overall-stats", json=stored).get_json()["totalStudents"], 5)


class StorageTests(unittest.TestCase):
    """Records and the university summary are saved to / read from a JSON file."""

    def setUp(self):
        app_module.app.testing = True
        app_module.DATA_FILE = os.path.join(tempfile.mkdtemp(), "data", "university_data.json")
        self.c = app_module.app.test_client()
        self.c.delete("/api/students")

    def read_file(self):
        with open(app_module.DATA_FILE, encoding="utf-8") as f:
            return json.load(f)

    def test_records_and_summary_saved_in_json_file(self):
        for rec in EXAMPLE:
            self.c.post("/api/add-student", json=rec)
        saved = self.read_file()
        self.assertEqual(saved["students"], EXAMPLE)
        self.assertEqual(saved["summary"], EXPECTED)
        self.assertEqual(saved["overall"]["totalStudents"], 5)
        self.assertEqual(self.c.get("/api/stored-data").get_json(), saved)

    def test_delete_and_clear_update_the_file(self):
        for rec in EXAMPLE:
            self.c.post("/api/add-student", json=rec)
        self.c.delete("/api/students/5")
        self.assertEqual(len(self.read_file()["students"]), 4)
        self.assertEqual(self.read_file()["summary"]["CHRIST"]["totalStudents"], 2)
        self.c.delete("/api/students")
        self.assertEqual(self.read_file()["students"], [])
        self.assertEqual(self.read_file()["summary"], {})

    def test_rejected_record_is_not_stored(self):
        self.c.post("/api/add-student", json=s(1, "A", 50))
        self.c.post("/api/add-student", json=s(1, "B", 60))      # duplicate
        self.c.post("/api/add-student", json=s(2, "A", 500))     # invalid
        self.assertEqual(self.read_file()["students"], [s(1, "A", 50)])

    def test_load_data_reads_file_back(self):
        self.c.post("/api/add-student", json=s(7, "Z", 77))
        self.assertEqual(app_module._load_data()["students"], [s(7, "Z", 77)])

    def test_corrupt_or_missing_file(self):
        os.remove(app_module.DATA_FILE)
        self.assertEqual(app_module._load_data(), {})              # missing file
        os.makedirs(os.path.dirname(app_module.DATA_FILE), exist_ok=True)
        with open(app_module.DATA_FILE, "w") as f:
            f.write("not json")
        self.assertEqual(app_module._load_data(), {})
        self.assertIn("students", self.c.get("/api/stored-data").get_json())


class FakeResponse:
    """Stands in for urllib's response object."""
    def __init__(self, payload):
        self.payload = payload
    def read(self, n=-1):
        return self.payload
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


class FetchFromApiTests(unittest.TestCase):
    """Records are received from an API URL, validated, and replace the stored data."""
    URL = "https://example.com/students.json"

    def setUp(self):
        app_module.app.testing = True
        app_module.DATA_FILE = os.path.join(tempfile.mkdtemp(), "data", "university_data.json")
        self.c = app_module.app.test_client()
        self.c.delete("/api/students")

    def fetch(self, payload, url=URL):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        with mock.patch.object(app_module.urllib.request, "urlopen", return_value=FakeResponse(raw)):
            return self.c.post("/api/fetch-from-api", json={"url": url})

    def stored(self):
        return self.c.get("/api/students").get_json()

    def test_fetch_replaces_existing_data(self):
        self.c.post("/api/add-student", json=s(100, "OLD", 50))
        r = self.fetch(EXAMPLE).get_json()
        self.assertEqual((r["received"], r["added"], r["removed"]), (5, 5, 1))
        self.assertEqual(self.stored(), EXAMPLE)                 # old record is gone
        summary = self.c.post("/api/generate-summary", json=self.stored()).get_json()
        self.assertEqual(summary, EXPECTED)
        with open(app_module.DATA_FILE, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["students"], EXAMPLE)
        self.assertEqual(saved["summary"], EXPECTED)

    def test_second_fetch_replaces_first(self):
        self.fetch(EXAMPLE)
        self.fetch([s(7, "NEW", 77)])
        self.assertEqual(self.stored(), [s(7, "NEW", 77)])

    def test_github_file_page_link_is_converted_to_raw(self):
        page = "https://github.com/KashviRamesh7/Student-data/blob/main/student.json"
        raw = "https://raw.githubusercontent.com/KashviRamesh7/Student-data/main/student.json"
        self.assertEqual(app_module.to_raw_github_url(page), raw)
        self.assertEqual(app_module.to_raw_github_url(raw), raw)
        self.assertEqual(app_module.to_raw_github_url("https://example.com/a/b/blob/c/d.json"),
                         "https://example.com/a/b/blob/c/d.json")
        with mock.patch.object(app_module.urllib.request, "urlopen",
                               return_value=FakeResponse(json.dumps(EXAMPLE).encode())) as m:
            r = self.c.post("/api/fetch-from-api", json={"url": page})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(m.call_args[0][0].full_url, raw)
        self.assertEqual(self.stored(), EXAMPLE)

    def test_wrapped_students_key_is_accepted(self):
        self.fetch({"students": [s(1, "A", 50)]})
        self.assertEqual(self.stored(), [s(1, "A", 50)])

    def test_mixed_valid_invalid_and_repeated_ids(self):
        self.c.post("/api/add-student", json=s(9, "OLD", 9))
        r = self.fetch([s(1, "A", 50), s(1, "B", 60), s(2, "A", 500), {"studentId": 3}, s(4, " B ", 70)]).get_json()
        self.assertEqual((r["received"], r["added"], r["removed"], r["duplicates"], r["invalidCount"]),
                         (5, 2, 1, 1, 2))
        self.assertEqual(self.stored(), [s(1, "A", 50), s(4, "B", 70)])

    def test_no_valid_records_keeps_old_data(self):
        self.c.post("/api/add-student", json=s(9, "KEEP", 9))
        r = self.fetch([s(1, "A", 500), {"x": 1}])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.stored(), [s(9, "KEEP", 9)])

    def test_url_is_required_and_default_sample_is_gone(self):
        self.c.post("/api/add-student", json=s(9, "KEEP", 9))
        for body in ({}, {"url": ""}, {"url": "   "}):
            self.assertEqual(self.c.post("/api/fetch-from-api", json=body).status_code, 400)
        self.assertEqual(self.c.get("/api/university-feed").status_code, 404)
        self.assertEqual(self.stored(), [s(9, "KEEP", 9)])

    def test_bad_urls_and_bad_api_responses(self):
        for url in ["ftp://x.com/a", "file:///etc/passwd", "not a url", 5]:
            r = self.c.post("/api/fetch-from-api", json={"url": url})
            self.assertEqual(r.status_code, 400, url)
        for payload in (b"<html>", b'{"a": 1}', b'"text"'):
            self.assertEqual(self.fetch(payload, "http://x.test/a").status_code, 502, payload)

    def test_unreachable_api_returns_502_and_keeps_data(self):
        self.c.post("/api/add-student", json=s(9, "KEEP", 9))
        r = self.c.post("/api/fetch-from-api", json={"url": "http://127.0.0.1:9/students"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(self.stored(), [s(9, "KEEP", 9)])


if __name__ == "__main__":
    unittest.main()
