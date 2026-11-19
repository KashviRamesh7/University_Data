# University Student Performance Analytics

## Project overview
A Flask web app where you enter student records (ID, university, score), view them in a table and
generate a **university-wise performance summary** (total students, average score, highest score).
The dashboard shows summary cards, a table and a Chart.js bar chart of average scores.

## Original problem statement
You receive student records from multiple universities through an API. Write a function that generates
a summary of student performance for each university: total number of students, average score and
highest score.

Example input -> output:
```json
{
    "CHRIST": {"totalStudents": 3, "averageScore": 83.33, "highestScore": 95},
    "ABC":    {"totalStudents": 2, "averageScore": 75.00, "highestScore": 90}
}
```

## Technologies used
Python 3.10+, Flask, HTML5, CSS3, JavaScript (Fetch API), JSON, Chart.js (CDN, chart only).

## University-wise grouping
`generate_university_summary()` in `app.py` loops over the records once and uses a dictionary keyed
by university name (whitespace trimmed). Each entry keeps a running student count, score total and
highest score, so students from different universities are never mixed.

## Average and highest score
- `averageScore = total score / number of students`, rounded with `round(..., 2)` (`250 / 3 = 83.33`; `75.0` is the number shown as 75.00).
- `highestScore` is compared per university: a record replaces it only when its score is greater.
- Invalid records are skipped and an empty list returns `{}`. All calculations are done in Python.

## Folder structure
```text
University_Performance_Analytics/
├── app.py
├── requirements.txt
├── README.md
├── templates/index.html
├── static/style.css
├── static/script.js
├── data/university_data.json   (created/updated automatically)
└── tests/test_app.py
```

## API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Main page |
| POST | `/api/add-student` | Validate and store one record (400 invalid, 409 duplicate ID) |
| GET | `/api/students` | All stored records |
| DELETE | `/api/students/<student_id>` | Remove one record (404 if not found) |
| DELETE | `/api/students` | Remove all records |
| POST | `/api/generate-summary` | Body: JSON array of records. Returns the university summary |
| POST | `/api/fetch-from-api` | Body `{"url": "..."}` (required). Calls the API, validates the records and **replaces** all stored records with them |
| POST | `/api/overall-stats` | Same body. Returns totals for the dashboard cards |

Validation: `studentId` positive whole number, `university` non-empty text, `score` number from 0 to 100.

## Install and run (Windows PowerShell)
```powershell
cd University_Performance_Analytics
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open: http://127.0.0.1:5000/  (the chart needs internet access to load Chart.js from a CDN)

## Tests
```powershell
python -m unittest discover tests -v
```

## Receiving records from an API
The assignment says records arrive *through an API*. Use **Receive Student Records from API**:
1. Paste the API URL (it must return a JSON array, or `{"students": [...]}`, of
   `{studentId, university, score}` records) and click **Fetch Student Records**.
2. The page asks the backend (`POST /api/fetch-from-api`), which makes a real HTTP request to the URL.
3. The backend validates every record (invalid ones and repeated IDs are skipped) and
   **replaces all current records** with the fetched ones. There is no built-in default data.
   If the API fails or has no valid records, your existing data is kept.
4. The new records are saved in `data/university_data.json`. Click **Generate University Summary**.

Example URL: a public `students.json` file on GitHub, opened with the **Raw** button
(`https://raw.githubusercontent.com/<user>/<repo>/main/students.json`). A normal GitHub file link
(`github.com/<user>/<repo>/blob/main/students.json`) is converted to the raw link automatically.

## Original example
The example from the assignment is verified by the unit tests (`test_original_example`).

## Stored data (JSON file)
Every time a student is added or removed, the backend rewrites `data/university_data.json` with the
records, the university-wise summary and the overall stats (all calculated in Python). Records are
reloaded from this file when the app restarts.
```json
{
  "updatedAt": "2026-11-19T10:15:00+00:00",
  "students": [{"studentId": 1, "university": "CHRIST", "score": 85}],
  "summary": {"CHRIST": {"totalStudents": 1, "averageScore": 85, "highestScore": 85}},
  "overall": {"totalUniversities": 1, "totalStudents": 1, "overallAverage": 85, "highestScore": 85}
}
```
The website shows this file in the **Stored University Data (JSON file)** section (Refresh button).
Extra endpoint: `GET /api/stored-data`.
