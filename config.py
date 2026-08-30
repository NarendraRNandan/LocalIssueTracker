import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get("SECRET_KEY", "civic-connect-super-secret-key-2026")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'civic_issue_tracker.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

    CATEGORIES = [
        "Roads & Potholes",
        "Waste & Garbage",
        "Streetlights & Electricity",
        "Water Supply & Drainage",
        "Public Safety & Traffic",
        "Parks & Trees",
        "Noise & Encroachment",
        "Public Infrastructure",
        "Other",
    ]

    STATUSES = [
        "Reported",
        "Acknowledged",
        "In Progress",
        "Resolved",
        "Rejected",
    ]

    PRIORITIES = [
        "Low",
        "Medium",
        "High",
        "Urgent",
    ]
