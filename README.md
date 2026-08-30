# 🏛️ CivicTrack / WorkersHub - AI-Powered Civic Grievance Redressal System

<h1>Deployeed url : "https://localissuetracker-9ebb.onrender.com/"</h1>

A full-stack, production-grade Civic Issue Reporting & Municipal Task Management Platform built with **Flask**, **SQLite**, **Scikit-Learn NLP**, and modern **SaaS UI/UX**.

---

## 🌟 Key Features

1. **AI-Powered Assistance**:
   - **Category Auto-Suggestion**: Multi-class NLP classifier (TF-IDF + Naive Bayes) predicting issue categories dynamically as citizens type.
   - **Smart Urgency & Priority Estimator**: Automated hazard risk keyword scoring for assigning Low, Medium, High, or Urgent priority.
   - **Duplicate Detection**: Real-time TF-IDF Cosine Similarity engine that surfaces existing complaints in the same locality to prevent redundant filings and cluster citizen upvotes.
   - **AI Action Triage**: Auto-summarizes complaints for municipal engineers and field workers.

2. **Pan-India Location Hierarchy**:
   - Integrated database with **State &rarr; District &rarr; City/Town** cascading dropdowns.
   - GPS Geotagging & interactive Leaflet.js Pin-Drop map.

3. **Multi-Role Governance**:
   - **Citizens**: Report geotagged issues, track status via visual step progress bar, view before/after resolution photos, and upvote local problems.
   - **Municipal Authorities & Zonal Officers**: Command center with KPI metrics, case dispatching, status transitions, and resolution proof verification.
   - **Field Workers**: Task assignment view, update status notes, and upload proof of work.

4. **Modern SaaS UI/UX**:
   - Global search in navbar and homepage.
   - Split-screen authentication pages with 1-click Demo credentials.
   - Public Interactive Map vs Card Grid view toggle.
   - Comprehensive audit timeline history for every issue.

---

## 🚀 Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Initialize Database & Seed Demo Data
```bash
flask init-db
flask seed-demo
```

### 3. Run Application
```bash
python app.py
```
Open your browser and visit: **http://127.0.0.1:5000**

---

## 👥 Demo Login Credentials

| Role | Email | Password |
| :--- | :--- | :--- |
| **Zonal Officer (Authority)** | `authority@civictrack.gov.in` | `authority123` |
| **Field Technician (Worker)** | `worker@civictrack.gov.in` | `worker123` |
| **Citizen** | `citizen@civictrack.in` | `citizen123` |


## Updated jurisdiction and workflow rules
- Login is unified; role is detected from the account.
- Only authorities require admin verification. Workers and citizens are active immediately.
- Authorities can see and modify only cases whose State + District + City/Town exactly matches their jurisdiction. Admins bypass this restriction.
- Workers see only their assignments and can accept/decline/cancel work; workers cannot change case status.
- Staff assignment is one member per submission; repeat Add Member to add more workers/authorities.
- Report Issue is citizen-only. GPS can reverse-geocode the selected location to auto-fill the place hierarchy.
- Only citizens can upvote.
- Admins can edit, cancel, or permanently delete applications.
