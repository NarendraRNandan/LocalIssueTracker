from datetime import datetime
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class Place(db.Model):
    __tablename__ = "places"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(100), nullable=False, index=True)
    district = db.Column(db.String(100), nullable=False, index=True)
    city_town = db.Column(db.String(120), nullable=False, index=True)

    __table_args__ = (
        db.UniqueConstraint("state", "district", "city_town", name="uq_place_hierarchy"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "state": self.state,
            "district": self.district,
            "city_town": self.city_town,
        }


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="citizen")  # citizen | authority | worker | admin
    phone = db.Column(db.String(20), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    district = db.Column(db.String(100), nullable=True)
    city_town = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(100), nullable=True)  # For authority/worker: e.g. Roads, Sanitation
    profile_photo = db.Column(db.String(255), nullable=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    reported_issues = db.relationship("Issue", backref="reporter", lazy="dynamic",
                                      foreign_keys="Issue.reporter_id")
    assigned_issues = db.relationship("Issue", backref="assignee", lazy="dynamic",
                                      foreign_keys="Issue.assigned_to_id")
    assignments = db.relationship("IssueAssignment", backref="user", lazy="dynamic",
                                  foreign_keys="IssueAssignment.user_id", cascade="all, delete-orphan")
    chat_messages = db.relationship("ChatMessage", backref="sender", lazy="dynamic",
                                    foreign_keys="ChatMessage.user_id", cascade="all, delete-orphan")
    upvotes = db.relationship("Upvote", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    notifications = db.relationship("Notification", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_authority(self):
        return self.role in ("authority", "admin")

    @property
    def is_staff(self):
        return self.role in ("authority", "admin", "worker")

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def can_access_worker_dashboard(self):
        return self.role == "worker" and self.is_verified


class Issue(db.Model):
    __tablename__ = "issues"

    id = db.Column(db.Integer, primary_key=True)
    case_code = db.Column(db.String(24), unique=True, nullable=False, index=True)  # e.g. LIT-000142
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(80), nullable=False, index=True)
    priority = db.Column(db.String(20), nullable=False, default="Medium")  # Low, Medium, High, Urgent

    # Location Hierarchy
    state = db.Column(db.String(100), nullable=False, index=True)
    district = db.Column(db.String(100), nullable=False, index=True)
    city_town = db.Column(db.String(120), nullable=False, index=True)
    locality_address = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    # Photos
    photo_filename = db.Column(db.String(255), nullable=True)
    resolution_photo_filename = db.Column(db.String(255), nullable=True)

    # Status & Engagement
    status = db.Column(db.String(30), nullable=False, default="Reported", index=True)
    upvote_count = db.Column(db.Integer, nullable=False, default=0)

    # AI Metadata
    ai_suggested_category = db.Column(db.String(80), nullable=True)
    ai_confidence = db.Column(db.Float, nullable=True)
    ai_urgency_score = db.Column(db.Float, nullable=True)
    ai_summary = db.Column(db.String(255), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    upvotes = db.relationship("Upvote", backref="issue", lazy="dynamic", cascade="all, delete-orphan")
    history = db.relationship("StatusHistory", backref="issue", lazy="dynamic",
                              cascade="all, delete-orphan", order_by="StatusHistory.created_at.asc()")
    comments = db.relationship("IssueComment", backref="issue", lazy="dynamic",
                              cascade="all, delete-orphan", order_by="IssueComment.created_at.asc()")
    assignments = db.relationship("IssueAssignment", backref="issue", lazy="dynamic",
                                  cascade="all, delete-orphan", order_by="IssueAssignment.assigned_at.asc()")
    chat_messages = db.relationship("ChatMessage", backref="issue", lazy="dynamic",
                                    cascade="all, delete-orphan", order_by="ChatMessage.created_at.asc()")

    @property
    def assigned_people(self):
        return [a.user for a in self.assignments if a.status != "declined"]

    def to_geojson_properties(self):
        return {
            "id": self.id,
            "case_code": self.case_code,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "state": self.state,
            "district": self.district,
            "city_town": self.city_town,
            "locality": self.locality_address or f"{self.city_town}, {self.district}",
            "upvotes": self.upvote_count,
            "photo_url": f"/static/uploads/{self.photo_filename}" if self.photo_filename else None,
            "resolution_photo_url": f"/static/uploads/{self.resolution_photo_filename}" if self.resolution_photo_filename else None,
            "created_at": self.created_at.strftime("%d %b %Y"),
            "time_ago": self.time_ago_str(),
            "ai_confidence": round(self.ai_confidence * 100) if self.ai_confidence else None,
        }

    def time_ago_str(self):
        diff = datetime.utcnow() - self.created_at
        if diff.days == 0:
            if diff.seconds < 3600:
                mins = max(1, diff.seconds // 60)
                return f"{mins}m ago"
            return f"{diff.seconds // 3600}h ago"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 30:
            return f"{diff.days}d ago"
        else:
            return self.created_at.strftime("%d %b %Y")


class Upvote(db.Model):
    __tablename__ = "upvotes"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("issue_id", "user_id", name="uq_issue_user_upvote"),
    )


class StatusHistory(db.Model):
    __tablename__ = "status_history"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.Text, nullable=True)
    proof_photo = db.Column(db.String(255), nullable=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    changed_by = db.relationship("User")


class IssueComment(db.Model):
    __tablename__ = "issue_comments"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship("User")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False, default="Status Update")
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    issue = db.relationship("Issue")


class IssueAssignment(db.Model):
    __tablename__ = "issue_assignments"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | accepted | declined | cancelled
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    responded_at = db.Column(db.DateTime, nullable=True)

    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])

    __table_args__ = (
        db.UniqueConstraint("issue_id", "user_id", name="uq_issue_assignment_user"),
    )


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


