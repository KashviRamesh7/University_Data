// Front-end: collects records, talks to Flask, and renders what the backend calculates.
const $ = id => document.getElementById(id);
let students = [];
let summaryShown = false;
let chart = null;

async function api(path, options = {}) {
  const res = await fetch(path, {headers: {"Content-Type": "application/json"}, ...options});
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
  return data;
}

let toastTimer;
function toast(msg, type) {
  const t = $("toast");
  t.textContent = msg; t.className = "toast show " + type;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2500);
}

function cell(text) { const td = document.createElement("td"); td.textContent = text; return td; }

// ---------------------------------------------------------- student records
async function loadStudents() {
  students = await api("/api/students");
  const body = $("studentRows"); body.innerHTML = "";
  students.forEach(s => {
    const tr = document.createElement("tr");
    tr.append(cell(s.studentId), cell(s.university), cell(s.score));
    const td = document.createElement("td");
    const btn = document.createElement("button");
    btn.className = "btn danger small"; btn.textContent = "Remove";
    btn.addEventListener("click", () => removeStudent(s.studentId));
    td.appendChild(btn); tr.appendChild(td); body.appendChild(tr);
  });
  $("emptyMsg").classList.toggle("hidden", students.length > 0);
  $("summaryBtn").disabled = students.length === 0;
  $("clearBtn").disabled = students.length === 0;
  await loadStored();
}

function setFormMsg(text, type, badFields = []) {
  const m = $("formMsg"); m.textContent = text; m.className = "form-msg " + type;
  ["studentId", "university", "score"].forEach(id => $(id).classList.toggle("bad", badFields.includes(id)));
}

// Client-side checks give instant feedback; the backend validates again.
function validateForm() {
  const idRaw = $("studentId").value.trim(), uni = $("university").value.trim(), scoreRaw = $("score").value.trim();
  if (!idRaw && !uni && !scoreRaw) return {error: "All fields are required.", bad: ["studentId", "university", "score"]};
  if (!idRaw) return {error: "Student ID is required.", bad: ["studentId"]};
  const id = Number(idRaw);
  if (!Number.isInteger(id) || id <= 0) return {error: "Student ID must be a positive whole number.", bad: ["studentId"]};
  if (!uni) return {error: "University name cannot be empty.", bad: ["university"]};
  if (!scoreRaw) return {error: "Score is required.", bad: ["score"]};
  const score = Number(scoreRaw);
  if (!Number.isFinite(score)) return {error: "Score must be a valid number.", bad: ["score"]};
  if (score < 0 || score > 100) return {error: "Score must be between 0 and 100.", bad: ["score"]};
  if (students.some(s => s.studentId === id)) return {error: "Student ID " + id + " already exists.", bad: ["studentId"]};
  return {record: {studentId: id, university: uni, score}};
}

async function addStudent(e) {
  e.preventDefault();
  const v = validateForm();
  if (v.error) { setFormMsg(v.error, "err", v.bad); return; }
  try {
    await api("/api/add-student", {method: "POST", body: JSON.stringify(v.record)});
    setFormMsg("Student " + v.record.studentId + " added.", "ok");
    $("studentForm").reset();
    await loadStudents();
    await refreshSummary();
  } catch (err) { setFormMsg(err.message, "err"); }
}

async function removeStudent(id) {
  try {
    await api("/api/students/" + id, {method: "DELETE"});
    toast("Student " + id + " removed.", "ok");
    await loadStudents();
    await refreshSummary();
  } catch (err) { toast(err.message, "err"); }
}

async function clearAll() {
  try {
    await api("/api/students", {method: "DELETE"});
    await loadStudents(); await refreshSummary();
    toast("All records cleared.", "ok");
  } catch (err) { toast(err.message, "err"); }
}

// ------------------------------------------------------------------ dashboard
async function generateSummary() {
  summaryShown = true;
  await refreshSummary(true);
}

// Re-computes the dashboard from the current records (only once it has been generated).
async function refreshSummary(announce = false) {
  if (!summaryShown) return;
  if (students.length === 0) { $("dashboard").classList.add("hidden"); summaryShown = false; return; }
  try {
    const body = JSON.stringify(students);
    const summary = await api("/api/generate-summary", {method: "POST", body});
    const overall = await api("/api/overall-stats", {method: "POST", body});
    renderDashboard(summary, overall);
    if (announce) toast("Summary generated.", "ok");
  } catch (err) { toast(err.message, "err"); }
}

function renderDashboard(summary, overall) {
  $("cards").innerHTML = "";
  [["Total universities", overall.totalUniversities], ["Total students", overall.totalStudents],
   ["Overall average score", overall.overallAverage], ["Highest score", overall.highestScore]].forEach(([k, v]) => {
    const d = document.createElement("div"); d.className = "stat";
    const s = document.createElement("strong"); s.textContent = v;
    d.append(s, k); $("cards").appendChild(d);
  });
  const body = $("summaryRows"); body.innerHTML = "";
  Object.entries(summary).forEach(([name, st]) => {
    const tr = document.createElement("tr");
    tr.append(cell(name), cell(st.totalStudents), cell(st.averageScore.toFixed(2)), cell(st.highestScore));
    body.appendChild(tr);
  });
  $("summaryJson").textContent = JSON.stringify(summary, null, 2);
  $("dashboard").classList.remove("hidden");
  drawChart(summary);
}

function drawChart(summary) {
  if (typeof Chart === "undefined") { $("chartNote").classList.remove("hidden"); return; }
  if (chart) chart.destroy();
  chart = new Chart($("chart"), {
    type: "bar",
    data: {
      labels: Object.keys(summary),
      datasets: [{label: "Average score",
        data: Object.values(summary).map(s => s.averageScore),
        backgroundColor: "rgba(124,77,255,.75)", borderColor: "#3b4fe0", borderWidth: 1, borderRadius: 8}]
    },
    options: {responsive: true, maintainAspectRatio: false,
      scales: {y: {beginAtZero: true, max: 100, title: {display: true, text: "Average score"}}}}
  });
}

// Asks the backend to call the API and store the valid records it returns.
async function fetchFromApi() {
  const msg = $("fetchMsg"), btn = $("fetchBtn");
  if (!$("apiUrl").value.trim()) { msg.className = "form-msg err"; msg.textContent = "Please paste an API URL."; return; }
  btn.disabled = true;
  msg.className = "form-msg"; msg.textContent = "Fetching records…";
  try {
    const r = await api("/api/fetch-from-api", {method: "POST", body: JSON.stringify({url: $("apiUrl").value.trim()})});
    let text = "Received " + r.received + " record(s): " + r.added + " loaded" +
               (r.removed ? " (" + r.removed + " previous record(s) replaced)" : "") + ", " +
               r.duplicates + " duplicate ID(s) skipped, " + r.invalidCount + " invalid skipped.";
    if (r.invalidCount > 0) text += " First problem – record " + r.invalid[0].record + ": " + r.invalid[0].error;
    msg.className = "form-msg ok"; msg.textContent = text;
    await loadStudents();
    await refreshSummary();
  } catch (err) {
    msg.className = "form-msg err"; msg.textContent = err.message;
  } finally { btn.disabled = false; }
}

// Shows the content of data/university_data.json (read by the backend).
async function loadStored() {
  try {
    const data = await api("/api/stored-data");
    $("storedJson").textContent = JSON.stringify(data, null, 2);
  } catch (err) { toast(err.message, "err"); }
}

async function init() {
  $("studentForm").addEventListener("submit", addStudent);
  $("summaryBtn").addEventListener("click", generateSummary);
  $("clearBtn").addEventListener("click", clearAll);
  $("refreshStoredBtn").addEventListener("click", loadStored);
  $("fetchBtn").addEventListener("click", fetchFromApi);
  try { await loadStudents(); } catch (err) { toast(err.message, "err"); }
}
init();
