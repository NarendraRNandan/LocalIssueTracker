import csv
import os
import random
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import (LoginManager, current_user, login_required,
                         login_user, logout_user)
from sqlalchemy import text
from werkzeug.utils import secure_filename

from ai_engine import ai_engine
from config import Config
from models import (ChatMessage, Issue, IssueAssignment, IssueComment, Notification, Place,
                    StatusHistory, Upvote, User, db)

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db.init_app(app)


def ensure_database_schema():
    with app.app_context():
        inspector = db.inspect(db.engine)
        table_names = set(inspector.get_table_names())

        if "users" not in table_names:
            db.create_all()
            return

        db.create_all()

        columns = {column["name"] for column in inspector.get_columns("users")}
        migrations = [
            ("profile_photo", "ALTER TABLE users ADD COLUMN profile_photo VARCHAR(255)"),
            ("is_verified", "ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0"),
            ("department", "ALTER TABLE users ADD COLUMN department VARCHAR(100)"),
        ]

        for column_name, statement in migrations:
            if column_name not in columns:
                db.session.execute(text(statement))

        db.session.commit()


ensure_database_schema()

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access this feature."
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- Context Processors ---
@app.context_processor
def inject_global_data():
    unread_notifications_count = 0
    if current_user.is_authenticated:
        unread_notifications_count = Notification.query.filter_by(
            user_id=current_user.id, is_read=False
        ).count()
    return {
        "unread_notifications_count": unread_notifications_count,
        "CATEGORIES": Config.CATEGORIES,
        "STATUSES": Config.STATUSES,
        "PRIORITIES": Config.PRIORITIES,
        "current_year": datetime.utcnow().year,
    }


# --- Role Decorators ---
def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access is required for this area.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def authority_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ("authority", "admin"):
            flash("You need authority or admin credentials to access this dashboard.", "warning")
            return redirect(url_for("login", next=request.url))
        return view(*args, **kwargs)
    return wrapped


def worker_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "worker":
            flash("Worker access is required for this area.", "warning")
            return redirect(url_for("login", next=request.url))
        return view(*args, **kwargs)
    return wrapped


def same_location(user, issue):
    """Exact jurisdiction match for officials; admins bypass jurisdiction."""
    if user.is_admin:
        return True
    if not user.state or not user.district or not user.city_town:
        return False
    return (
        user.state.strip().casefold() == issue.state.strip().casefold()
        and user.district.strip().casefold() == issue.district.strip().casefold()
        and user.city_town.strip().casefold() == issue.city_town.strip().casefold()
    )


def staff_can_access_issue(user, issue):
    if user.is_admin:
        return True
    if user.role == "authority":
        return same_location(user, issue) and user.is_verified
    if user.role == "worker":
        return same_location(user, issue) and IssueAssignment.query.filter_by(
            issue_id=issue.id, user_id=user.id
        ).filter(IssueAssignment.status.in_(["pending", "accepted"])).first() is not None
    return False


def can_view_issue_for_user(user, issue):
    if user.is_admin:
        return True
    if user.role == "citizen":
        return issue.reporter_id == user.id
    return staff_can_access_issue(user, issue)


def eligible_staff_query():
    """Workers need no verification; authorities must be admin-verified."""
    return User.query.filter(
        User.role.in_(["worker", "authority"]),
        db.or_(User.role == "worker", db.and_(User.role == "authority", User.is_verified.is_(True)))
    )


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]
    )


def save_upload(file_storage):
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"{int(datetime.utcnow().timestamp())}_{random.randint(1000, 9999)}.{ext}")
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


def next_case_code():
    latest = Issue.query.order_by(Issue.id.desc()).first()
    if latest and latest.case_code.startswith("LIT-"):
        try:
            number = int(latest.case_code.split("-")[-1]) + 1
        except ValueError:
            number = Issue.query.count() + 1
    else:
        number = Issue.query.count() + 1
    return f"LIT-{number:06d}"


def notify(user_id, issue_id, title, message):
    notif = Notification(user_id=user_id, issue_id=issue_id, title=title, message=message)
    db.session.add(notif)


# =========================================================================
# PLACES & CASCADING API ENDPOINTS
# =========================================================================

@app.route("/api/places/states")
def api_places_states():
    states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]
    return jsonify({"states": states})


@app.route("/api/places/districts")
def api_places_districts():
    state = request.args.get("state", "").strip()
    if not state:
        return jsonify({"districts": []})
    districts = [
        r[0]
        for r in db.session.query(Place.district)
        .filter_by(state=state)
        .distinct()
        .order_by(Place.district)
        .all()
    ]
    return jsonify({"districts": districts})


@app.route("/api/places/cities")
def api_places_cities():
    state = request.args.get("state", "").strip()
    district = request.args.get("district", "").strip()
    query = db.session.query(Place.city_town)
    if state:
        query = query.filter_by(state=state)
    if district:
        query = query.filter_by(district=district)
    cities = [r[0] for r in query.distinct().order_by(Place.city_town).all()]
    return jsonify({"cities": cities})


# =========================================================================
# AI FEATURE ENDPOINTS
# =========================================================================

@app.route("/api/ai/suggest-category", methods=["POST"])
def api_ai_suggest_category():
    data = request.get_json(silent=True) or {}
    text = (data.get("title", "") + " " + data.get("description", "")).strip()

    if len(text) < 4:
        return jsonify({
            "category": "Roads & Potholes",
            "confidence": 0.5,
            "priority": "Medium",
            "urgency_score": 0.4,
            "reasons": []
        })

    cat_result = ai_engine.predict_category(text)
    prio_result = ai_engine.assess_priority_and_urgency(text, cat_result["category"])

    return jsonify({
        "category": cat_result["category"],
        "confidence": cat_result["confidence"],
        "all_probabilities": cat_result.get("all_probabilities", {}),
        "priority": prio_result["priority"],
        "urgency_score": prio_result["urgency_score"],
        "reasons": prio_result["reasons"],
    })


@app.route("/api/ai/check-duplicates", methods=["POST"])
def api_ai_check_duplicates():
    data = request.get_json(silent=True) or {}
    text = (data.get("title", "") + " " + data.get("description", "")).strip()
    state = data.get("state", "").strip()
    district = data.get("district", "").strip()
    city_town = data.get("city_town", "").strip()

    if len(text) < 8:
        return jsonify({"duplicates": []})

    # Search open issues (Reported / In Progress / Acknowledged)
    query = Issue.query.filter(Issue.status.in_(["Reported", "Acknowledged", "In Progress"]))
    if city_town:
        query = query.filter_by(city_town=city_town)
    elif district:
        query = query.filter_by(district=district)
    elif state:
        query = query.filter_by(state=state)

    existing_issues = query.order_by(Issue.created_at.desc()).limit(30).all()
    duplicates = ai_engine.find_duplicates(text, existing_issues, similarity_threshold=0.35)

    return jsonify({"duplicates": duplicates})


# =========================================================================
# PUBLIC / CITIZEN ROUTES
# =========================================================================

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    status = request.args.get("status", "").strip()
    state = request.args.get("state", "").strip()
    district = request.args.get("district", "").strip()
    city_town = request.args.get("city_town", "").strip()
    sort = request.args.get("sort", "newest")

    query = Issue.query.filter(Issue.status != "Resolved")

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            db.or_(
                Issue.case_code.ilike(search_pattern),
                Issue.title.ilike(search_pattern),
                Issue.description.ilike(search_pattern),
                Issue.locality_address.ilike(search_pattern),
                Issue.city_town.ilike(search_pattern),
            )
        )
    if category and category != "all":
        query = query.filter_by(category=category)
    if status and status != "all":
        query = query.filter_by(status=status)
    if state and state != "all":
        query = query.filter_by(state=state)
    if district and district != "all":
        query = query.filter_by(district=district)
    if city_town and city_town != "all":
        query = query.filter_by(city_town=city_town)

    if sort == "upvotes":
        query = query.order_by(Issue.upvote_count.desc(), Issue.created_at.desc())
    elif sort == "urgent":
        query = query.order_by(
            db.case(
                (Issue.priority == "Urgent", 1),
                (Issue.priority == "High", 2),
                (Issue.priority == "Medium", 3),
                else_=4
            ),
            Issue.created_at.desc()
        )
    else:
        query = query.order_by(Issue.created_at.desc())

    issues = query.limit(60).all()

    # Aggregate quick statistics for active public issues only
    active_issues = Issue.query.filter(Issue.status != "Resolved")
    stats = {
        "total": active_issues.count(),
        "reported": active_issues.filter_by(status="Reported").count(),
        "in_progress": active_issues.filter_by(status="In Progress").count(),
        "resolved": Issue.query.filter_by(status="Resolved").count(),
        "resolution_rate": round(
            (Issue.query.filter_by(status="Resolved").count() / max(1, active_issues.count())) * 100
        ),
    }

    # Fetch available states for initial dropdown
    all_states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]

    return render_template(
        "index.html",
        issues=issues,
        stats=stats,
        states=all_states,
        selected_q=q,
        selected_category=category,
        selected_status=status,
        selected_state=state,
        selected_district=district,
        selected_city=city_town,
        selected_sort=sort,
    )


@app.route("/api/issues")
def api_issues():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    status = request.args.get("status", "")
    state = request.args.get("state", "")
    district = request.args.get("district", "")
    city_town = request.args.get("city_town", "")

    query = Issue.query.filter(Issue.status != "Resolved")
    if q:
        query = query.filter(
            db.or_(
                Issue.case_code.ilike(f"%{q}%"),
                Issue.title.ilike(f"%{q}%"),
                Issue.description.ilike(f"%{q}%"),
                Issue.locality_address.ilike(f"%{q}%"),
                Issue.city_town.ilike(f"%{q}%"),
            )
        )
    if category and category != "all":
        query = query.filter_by(category=category)
    if status and status != "all":
        query = query.filter_by(status=status)
    if state and state != "all":
        query = query.filter_by(state=state)
    if district and district != "all":
        query = query.filter_by(district=district)
    if city_town and city_town != "all":
        query = query.filter_by(city_town=city_town)

    issues = query.order_by(Issue.created_at.desc()).limit(150).all()
    features = []
    for issue in issues:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [issue.longitude, issue.latitude]
            },
            "properties": issue.to_geojson_properties(),
        })

    return jsonify({"type": "FeatureCollection", "features": features})


# =========================================================================
# AUTHENTICATION (SPLIT SCREEN LOGIN & REGISTER)
# =========================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin: return redirect(url_for("admin_panel"))
        if current_user.role in ("authority", "worker"): return redirect(url_for("dashboard"))
        return redirect(url_for("index"))
    if request.method == "POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); remember=bool(request.form.get("remember"))
        user=User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            if user.role == "authority" and not user.is_verified:
                flash("This authority account is awaiting admin verification.","warning"); return render_template("login.html")
            login_user(user,remember=remember); flash(f"Welcome back, {user.name}!","success")
            next_url=request.args.get("next")
            if user.is_admin: return redirect(next_url or url_for("admin_panel"))
            if user.role in ("authority","worker"): return redirect(next_url or url_for("dashboard"))
            return redirect(next_url or url_for("index"))
        flash("Invalid email or password. Please try again.","error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    all_states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        role = request.form.get("role", "citizen")
        state = request.form.get("state") or None
        district = request.form.get("district") or None
        city_town = request.form.get("city_town") or None
        department = request.form.get("department") or None
        profile_photo = save_upload(request.files.get("profile_photo"))

        if not name or not email or not password:
            flash("Name, email and password are required.", "error")
            return render_template("register.html", states=all_states)

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_template("register.html", states=all_states)

        chosen_role = role if role in ("citizen", "authority", "worker") else "citizen"
        # Citizens and workers can use their accounts immediately.
        # Only authorities require admin verification.
        verified = chosen_role != "authority"

        user = User(
            name=name,
            email=email,
            phone=phone or None,
            role=chosen_role,
            state=state,
            district=district,
            city_town=city_town,
            department=department if chosen_role != "citizen" else None,
            profile_photo=profile_photo,
            is_verified=verified,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        if chosen_role in ("worker", "authority"):
            flash(f"{chosen_role.title()} account created successfully. Admin verification is required before official access.", "info")
            return redirect(url_for("login"))

        login_user(user)
        flash("Your account was successfully registered! Welcome to CivicTrack.", "success")
        if user.is_admin or user.role == "authority":
            return redirect(url_for("dashboard"))
        return redirect(url_for("index"))

    return render_template("register.html", states=all_states)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have signed out.", "info")
    return redirect(url_for("index"))


# =========================================================================
# REPORT ISSUE (WITH AI AUTO-SUGGEST & DUPLICATE DETECTION)
# =========================================================================

@app.route("/report", methods=["GET", "POST"])
@login_required
def report_issue():
    if current_user.role != "citizen":
        flash("Only citizens can submit civic reports.", "warning")
        return redirect(url_for("index"))

    all_states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category")
        priority = request.form.get("priority", "Medium")
        state = request.form.get("state")
        district = request.form.get("district")
        city_town = request.form.get("city_town")
        locality_address = request.form.get("locality_address", "").strip()
        lat_val = request.form.get("latitude")
        lng_val = request.form.get("longitude")

        if not (title and description and category and state and district and city_town):
            flash("Please fill in all mandatory fields including title, description, and location.", "error")
            return render_template("report.html", states=all_states)

        # Accept only a valid place from the official place hierarchy.
        place = Place.query.filter_by(state=state, district=district, city_town=city_town).first()
        if not place:
            flash("Please select a valid State → District → City/Town location.", "error")
            return render_template("report.html", states=all_states)

        # Fallback coordinates are centered on Mysuru instead of a hidden Bengaluru default.
        try:
            latitude = float(lat_val) if lat_val else 12.2958
            longitude = float(lng_val) if lng_val else 76.6394
        except ValueError:
            latitude, longitude = 12.2958, 76.6394

        photo_filename = save_upload(request.files.get("photo"))

        # AI assessment
        combined_text = f"{title} {description}"
        ai_cat = ai_engine.predict_category(combined_text)
        ai_prio = ai_engine.assess_priority_and_urgency(combined_text, category)
        ai_sum = ai_engine.generate_action_summary(title, description, category)

        issue = Issue(
            case_code=next_case_code(),
            reporter_id=current_user.id,
            title=title,
            description=description,
            category=category,
            priority=priority or ai_prio["priority"],
            state=state,
            district=district,
            city_town=city_town,
            locality_address=locality_address or None,
            latitude=latitude,
            longitude=longitude,
            photo_filename=photo_filename,
            status="Reported",
            ai_suggested_category=ai_cat["category"],
            ai_confidence=ai_cat["confidence"],
            ai_urgency_score=ai_prio["urgency_score"],
            ai_summary=ai_sum,
        )
        db.session.add(issue)
        db.session.flush()

        # Add initial StatusHistory
        history = StatusHistory(
            issue_id=issue.id,
            old_status=None,
            new_status="Reported",
            note="Issue logged by citizen via civic portal.",
            changed_by_id=current_user.id,
        )
        db.session.add(history)

        # Notify reporter
        notify(
            current_user.id,
            issue.id,
            "Issue Registered",
            f"Your report '{issue.title}' has been registered as {issue.case_code}."
        )

        db.session.commit()
        flash(f"Thank you! Your issue was recorded as Case {issue.case_code}. You can track live updates anytime.", "success")
        return redirect(url_for("issue_detail", issue_id=issue.id))

    return render_template("report.html", states=all_states)


# =========================================================================
# CITIZEN REPORTS & ISSUE DOSSIER
# =========================================================================

@app.route("/my-reports")
@login_required
def my_reports():
    q=request.args.get("q","").strip(); status=request.args.get("status","all")
    query=current_user.reported_issues.filter(Issue.status.notin_(["Resolved", "Rejected"]))
    if q: query=query.filter(db.or_(Issue.case_code.ilike(f"%{q}%"),Issue.title.ilike(f"%{q}%"),Issue.description.ilike(f"%{q}%")))
    if status!="all": query=query.filter_by(status=status)
    issues=query.order_by(Issue.updated_at.desc(),Issue.created_at.desc()).all()
    return render_template("my_reports.html",issues=issues,current_status=status,search_q=q)

@app.route("/issue/<int:issue_id>")
def issue_detail(issue_id):
    issue = Issue.query.get_or_404(issue_id)
    if current_user.is_authenticated and not can_view_issue_for_user(current_user, issue):
        abort(403)
    already_upvoted = False
    if current_user.is_authenticated:
        already_upvoted = (
            Upvote.query.filter_by(issue_id=issue.id, user_id=current_user.id).first() is not None
        )

    comments = issue.comments.order_by(IssueComment.created_at.asc()).all()

    # Fetch similar issues in the same area
    nearby_issues = (
        Issue.query.filter(
            Issue.id != issue.id,
            Issue.city_town == issue.city_town,
            Issue.status.notin_(["Resolved", "Rejected"])
        )
        .order_by(Issue.created_at.desc())
        .limit(4)
        .all()
    )

    assignments=issue.assignments.filter(IssueAssignment.status.notin_(["declined","cancelled"])).all()
    staff=[]
    can_manage_case=False
    if current_user.is_authenticated and current_user.is_admin:
        can_manage_case=True
        staff=eligible_staff_query().filter(User.state==issue.state,User.district==issue.district,User.city_town==issue.city_town).order_by(User.role,User.name).all()
    elif current_user.is_authenticated and current_user.role == "authority" and current_user.is_verified and same_location(current_user, issue):
        can_manage_case=True
        staff=eligible_staff_query().filter(User.state==issue.state,User.district==issue.district,User.city_town==issue.city_town).order_by(User.role,User.name).all()

    return render_template(
        "issue_detail.html",
        issue=issue,
        already_upvoted=already_upvoted,
        nearby_issues=nearby_issues,
        workers=staff,
        assignments=assignments,
        can_chat=can_chat_on_issue(issue) if current_user.is_authenticated else False,
        comments=comments,
        can_manage_case=can_manage_case,
    )


@app.route("/issue/<int:issue_id>/comment", methods=["POST"])
@login_required
def issue_comment(issue_id):
    issue = Issue.query.get_or_404(issue_id)
    if not can_view_issue_for_user(current_user, issue):
        abort(403)
    message = request.form.get("message", "").strip()
    if not message:
        flash("Please enter a message before sending it.", "warning")
        return redirect(request.referrer or url_for("issue_detail", issue_id=issue.id))

    comment = IssueComment(issue_id=issue.id, user_id=current_user.id, message=message)
    db.session.add(comment)

    if issue.reporter_id != current_user.id:
        notify(issue.reporter_id, issue.id, "New Comment", f"{current_user.name} commented on case {issue.case_code}.")
    if issue.assigned_to_id and issue.assigned_to_id != current_user.id:
        notify(issue.assigned_to_id, issue.id, "New Comment", f"{current_user.name} commented on case {issue.case_code}.")

    db.session.commit()
    flash("Message sent successfully.", "success")
    return redirect(request.referrer or url_for("issue_detail", issue_id=issue.id))


@app.route("/issue/<int:issue_id>/upvote", methods=["POST"])
@login_required
def upvote_issue(issue_id):
    issue=Issue.query.get_or_404(issue_id)
    if not current_user.is_authenticated or current_user.role != "citizen":
        flash("Only citizens can upvote civic cases.","warning"); return redirect(request.referrer or url_for("issue_detail",issue_id=issue.id))
    if issue.status=="Resolved":
        flash("Resolved cases can no longer be upvoted.","info"); return redirect(request.referrer or url_for("issue_detail",issue_id=issue.id))
    existing=Upvote.query.filter_by(issue_id=issue.id,user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        issue.upvote_count = max(0, issue.upvote_count - 1)
        db.session.commit()
        flash("Upvote removed.", "info")
    else:
        db.session.add(Upvote(issue_id=issue.id, user_id=current_user.id))
        issue.upvote_count += 1
        db.session.commit()
        flash("Thank you for upvoting! This helps municipal workers prioritize this issue.", "success")

    return redirect(request.referrer or url_for("issue_detail", issue_id=issue.id))


@app.route("/notifications")
@login_required
def notifications():
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return render_template("notifications.html", items=items)


# =========================================================================
# AUTHORITY & WORKER DASHBOARD
# =========================================================================

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin or current_user.role == "authority":
        return authority_dashboard()
    if current_user.role == "worker":
        return worker_dashboard()
    flash("This account type does not have access to the dashboard.", "warning")
    return redirect(url_for("index"))


@app.route("/dashboard/assignment/<int:assignment_id>/<action>", methods=["POST"])
@login_required
def worker_assignment_action(assignment_id, action):
    a=IssueAssignment.query.get_or_404(assignment_id)
    if a.user_id!=current_user.id or current_user.role!="worker": abort(403)
    if a.issue.status=="Resolved": flash("This case is already completed.","info"); return redirect(url_for("dashboard"))
    if action=="accept" and a.status=="pending":
        a.status="accepted"; a.responded_at=datetime.utcnow(); notify(a.issue.reporter_id,a.issue.id,"Worker Accepted Case",f"{current_user.name} accepted case {a.issue.case_code}."); flash("Work accepted. Coordinate through case chat.","success")
    elif action in ("decline","cancel") and a.status in ("pending","accepted"):
        a.status="declined" if action=="decline" else "cancelled"; a.responded_at=datetime.utcnow(); notify(a.issue.reporter_id,a.issue.id,"Assignment Updated",f"{current_user.name} {action}ed the assignment for {a.issue.case_code}."); flash(f"Assignment {action}ed.","info")
    else: flash("That assignment action is no longer available.","warning")
    db.session.commit(); return redirect(request.referrer or url_for("dashboard"))

@app.route("/dashboard/history")
@login_required
@authority_required
def authority_history():
    query = Issue.query.filter_by(status="Resolved")
    if not current_user.is_admin:
        if not current_user.is_verified or not current_user.state or not current_user.district or not current_user.city_town:
            abort(403)
        query = query.filter_by(state=current_user.state, district=current_user.district, city_town=current_user.city_town)
    issues=query.order_by(Issue.resolved_at.desc(),Issue.updated_at.desc()).all()
    return render_template("history.html",issues=issues,title="Authority Case History")

@app.route("/my-reports/history")
@login_required
def client_history():
    issues=current_user.reported_issues.filter_by(status="Resolved").order_by(Issue.resolved_at.desc(),Issue.updated_at.desc()).all()
    return render_template("history.html",issues=issues,title="My Completed Complaints",client_history=True)

def can_chat_on_issue(issue):
    if current_user.is_admin:
        return True
    if current_user.role == "citizen":
        return current_user.id == issue.reporter_id
    if current_user.role == "authority":
        return same_location(current_user, issue) and current_user.is_verified
    if current_user.role == "worker":
        return IssueAssignment.query.filter_by(issue_id=issue.id,user_id=current_user.id).filter(IssueAssignment.status.in_(["pending","accepted"])).first() is not None
    return False

@app.route("/issue/<int:issue_id>/chat", methods=["GET","POST"])
@login_required
def issue_chat(issue_id):
    issue=Issue.query.get_or_404(issue_id)
    if not can_chat_on_issue(issue): abort(403)
    if request.method=="POST":
        if issue.status=="Resolved": flash("Chat is closed because this case is completed.","info"); return redirect(url_for("issue_chat",issue_id=issue.id))
        message=request.form.get("message","").strip()
        if not message: flash("Enter a message before sending.","warning"); return redirect(url_for("issue_chat",issue_id=issue.id))
        db.session.add(ChatMessage(issue_id=issue.id,user_id=current_user.id,message=message))
        ids={issue.reporter_id}; ids.update(a.user_id for a in issue.assignments.filter(IssueAssignment.status.in_(["pending","accepted"])).all())
        for uid in ids:
            if uid!=current_user.id: notify(uid,issue.id,f"New message • {issue.case_code}",f"{current_user.name}: {message[:180]}")
        db.session.commit(); return redirect(url_for("issue_chat",issue_id=issue.id))
    messages=issue.chat_messages.order_by(ChatMessage.created_at.asc()).all(); people=[issue.reporter]+[a.user for a in issue.assignments.filter(IssueAssignment.status.in_(["pending","accepted"])).all()]; people=list({u.id:u for u in people}.values())
    return render_template("chat.html",issue=issue,messages=messages,participants=people,chat_open=issue.status!="Resolved")

@app.route("/notifications/read/<int:notification_id>")
@login_required
def notification_read(notification_id):
    item=Notification.query.filter_by(id=notification_id,user_id=current_user.id).first_or_404(); item.is_read=True; db.session.commit(); return redirect(url_for("issue_chat",issue_id=item.issue_id) if item.issue_id else url_for("notifications"))

@app.route("/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    Notification.query.filter_by(user_id=current_user.id,is_read=False).update({"is_read":True}); db.session.commit(); flash("All notifications marked as read.","success"); return redirect(url_for("notifications"))

@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    # Admin verification is intentionally limited to authorities.
    authorities = User.query.filter_by(role="authority").order_by(User.created_at.desc()).all()
    workers = User.query.filter_by(role="worker").order_by(User.created_at.desc()).all()
    active_issues = Issue.query.order_by(Issue.updated_at.asc()).all()
    states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]
    return render_template("admin_panel.html", authorities=authorities, workers=workers, active_issues=active_issues, states=states)


@app.route("/admin/verify-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def verify_user(user_id):
    user=User.query.get_or_404(user_id)
    if user.role != "authority":
        flash("Only authority accounts require admin verification.","warning")
        return redirect(url_for("admin_panel"))
    user.is_verified=not user.is_verified
    db.session.commit()
    status_text = "verified" if user.is_verified else "unverified"
    flash(f"Authority {user.name} is now {status_text}.","success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/issue/<int:issue_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_issue(issue_id):
    issue=Issue.query.get_or_404(issue_id)
    states=[r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]
    if request.method == "POST":
        title=request.form.get("title","").strip()
        description=request.form.get("description","").strip()
        category=request.form.get("category","").strip()
        priority=request.form.get("priority","").strip()
        state=request.form.get("state","").strip()
        district=request.form.get("district","").strip()
        city_town=request.form.get("city_town","").strip()
        locality=request.form.get("locality_address","").strip()
        place=Place.query.filter_by(state=state,district=district,city_town=city_town).first()
        if not all([title,description,category,priority,state,district,city_town]) or not place:
            flash("Enter valid issue details and a valid State → District → City/Town.","error")
            return render_template("edit_issue.html", issue=issue, states=states)
        old_location=(issue.state,issue.district,issue.city_town)
        issue.title=title; issue.description=description; issue.category=category; issue.priority=priority
        issue.state=state; issue.district=district; issue.city_town=city_town; issue.locality_address=locality or None
        issue.updated_at=datetime.utcnow()
        for assignment in issue.assignments.filter(IssueAssignment.status.in_(["pending","accepted"])).all():
            person=assignment.user
            if not (person.state and person.district and person.city_town and
                    person.state.casefold()==issue.state.casefold() and
                    person.district.casefold()==issue.district.casefold() and
                    person.city_town.casefold()==issue.city_town.casefold()):
                assignment.status="cancelled"
                assignment.responded_at=datetime.utcnow()
                notify(person.id, issue.id, "Assignment Cancelled", f"Your assignment for {issue.case_code} was cancelled because the administrator changed the case jurisdiction.")
        if issue.assigned_to_id:
            primary=User.query.get(issue.assigned_to_id)
            if primary and not (primary.state and primary.district and primary.city_town and primary.state.casefold()==issue.state.casefold() and primary.district.casefold()==issue.district.casefold() and primary.city_town.casefold()==issue.city_town.casefold()):
                issue.assigned_to_id=None
        db.session.commit()
        # Notify the client and currently assigned participants after admin changes.
        notify(issue.reporter_id, issue.id, "Case Updated by Admin", f"Admin updated {issue.case_code}. Please review the latest details.")
        for a in issue.assignments.filter(IssueAssignment.status.in_(["pending","accepted"])).all():
            if a.user_id != issue.reporter_id:
                notify(a.user_id, issue.id, "Case Updated by Admin", f"Admin updated {issue.case_code}. Location/details may have changed.")
        db.session.commit()
        flash(f"{issue.case_code} updated successfully by admin.","success")
        return redirect(url_for("issue_detail", issue_id=issue.id))
    return render_template("edit_issue.html", issue=issue, states=states)


@app.route("/admin/issue/<int:issue_id>/cancel", methods=["POST"])
@login_required
@admin_required
def admin_cancel_issue(issue_id):
    issue=Issue.query.get_or_404(issue_id)
    if issue.status == "Resolved":
        flash("A resolved case cannot be cancelled.","warning")
        return redirect(request.referrer or url_for("admin_panel"))
    old=issue.status
    issue.status="Rejected"
    issue.resolved_at=None
    db.session.add(StatusHistory(issue_id=issue.id,old_status=old,new_status="Rejected",note="Case cancelled by administrator.",changed_by_id=current_user.id))
    notify(issue.reporter_id, issue.id, "Case Cancelled", f"Your case {issue.case_code} was cancelled by the administrator.")
    db.session.commit()
    flash(f"{issue.case_code} was cancelled.","success")
    return redirect(request.referrer or url_for("admin_panel"))


@app.route("/admin/issue/<int:issue_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_issue(issue_id):
    issue=Issue.query.get_or_404(issue_id)
    code=issue.case_code
    db.session.delete(issue)
    db.session.commit()
    flash(f"{code} was permanently deleted by the administrator.","success")
    return redirect(url_for("admin_panel"))


@app.route("/dashboard/worker")
@login_required
@worker_required
def worker_dashboard():
    q=request.args.get("q","").strip(); status=request.args.get("assignment_status","all"); date_from=request.args.get("date_from","").strip(); date_to=request.args.get("date_to","").strip()
    query=IssueAssignment.query.filter_by(user_id=current_user.id).join(Issue).filter(Issue.status.notin_(["Resolved", "Rejected"]))
    if not current_user.state or not current_user.district or not current_user.city_town:
        assignments=[]
        stats={"total":0,"pending":0,"accepted":0,"completed":0}
        return render_template("dashboard.html",assignments=assignments,issues=[],stats=stats,workers=[],states=[],current_status=status,current_category="all",current_priority="all",current_state="",current_district="",current_city="",current_sort="queue",search_q=q,current_role="worker",date_from=date_from,date_to=date_to)
    query=query.filter(Issue.state==current_user.state,Issue.district==current_user.district,Issue.city_town==current_user.city_town)
    if status!="all": query=query.filter(IssueAssignment.status==status)
    if q:
        pat=f"%{q}%"; query=query.filter(db.or_(Issue.case_code.ilike(pat),Issue.title.ilike(pat),Issue.city_town.ilike(pat),Issue.locality_address.ilike(pat)))
    if date_from:
        try: query=query.filter(Issue.created_at>=datetime.strptime(date_from,"%Y-%m-%d"))
        except ValueError: pass
    if date_to:
        try: query=query.filter(Issue.created_at<datetime.strptime(date_to,"%Y-%m-%d")+timedelta(days=1))
        except ValueError: pass
    assignments=query.order_by(IssueAssignment.assigned_at.desc()).all()
    stats={"total":IssueAssignment.query.filter_by(user_id=current_user.id).count(),"pending":IssueAssignment.query.filter_by(user_id=current_user.id,status="pending").count(),"accepted":IssueAssignment.query.filter_by(user_id=current_user.id,status="accepted").count(),"completed":IssueAssignment.query.join(Issue).filter(IssueAssignment.user_id==current_user.id,Issue.status=="Resolved").count()}
    return render_template("dashboard.html",assignments=assignments,issues=[a.issue for a in assignments],stats=stats,workers=[],states=[],current_status=status,current_category="all",current_priority="all",current_state=current_user.state,current_district=current_user.district,current_city=current_user.city_town,current_sort="queue",search_q=q,current_role="worker",date_from=date_from,date_to=date_to)

@app.route("/dashboard/authority")
@login_required
@authority_required
def authority_dashboard():
    q=request.args.get("q","").strip(); status=request.args.get("status","all"); category=request.args.get("category","all"); priority=request.args.get("priority","all")
    date_from=request.args.get("date_from","").strip(); date_to=request.args.get("date_to","").strip(); sort=request.args.get("sort","queue")

    query=Issue.query if current_user.is_admin else Issue.query.filter(Issue.status.notin_(["Resolved", "Rejected"]))
    if not current_user.is_admin:
        if not current_user.is_verified or not current_user.state or not current_user.district or not current_user.city_town:
            abort(403)
        query=query.filter_by(state=current_user.state,district=current_user.district,city_town=current_user.city_town)
    else:
        state=request.args.get("state","all"); district=request.args.get("district","all"); city_town=request.args.get("city_town","all")
        if state!="all": query=query.filter_by(state=state)
        if district!="all": query=query.filter_by(district=district)
        if city_town!="all": query=query.filter_by(city_town=city_town)

    if q:
        pat=f"%{q}%"; query=query.filter(db.or_(Issue.case_code.ilike(pat),Issue.title.ilike(pat),Issue.description.ilike(pat),Issue.locality_address.ilike(pat),Issue.city_town.ilike(pat)))
    if status!="all": query=query.filter_by(status=status)
    if category!="all": query=query.filter_by(category=category)
    if priority!="all": query=query.filter_by(priority=priority)
    if date_from:
        try: query=query.filter(Issue.created_at>=datetime.strptime(date_from,"%Y-%m-%d"))
        except ValueError: pass
    if date_to:
        try: query=query.filter(Issue.created_at<datetime.strptime(date_to,"%Y-%m-%d")+timedelta(days=1))
        except ValueError: pass
    if sort=="priority": query=query.order_by(db.case((Issue.priority=="Urgent",1),(Issue.priority=="High",2),(Issue.priority=="Medium",3),else_=4),Issue.updated_at.asc())
    elif sort=="upvotes": query=query.order_by(Issue.upvote_count.desc(),Issue.updated_at.asc())
    else: query=query.order_by(Issue.updated_at.asc(),Issue.created_at.asc())
    issues=query.all()

    scoped_base=Issue.query if current_user.is_admin else Issue.query.filter_by(state=current_user.state,district=current_user.district,city_town=current_user.city_town)
    total_count=scoped_base.count(); reported_count=scoped_base.filter_by(status="Reported").count(); in_progress_count=scoped_base.filter_by(status="In Progress").count(); resolved_count=scoped_base.filter_by(status="Resolved").count(); urgent_count=scoped_base.filter(Issue.priority.in_(["High","Urgent"]),Issue.status!="Resolved").count()
    stats={"total":total_count,"reported":reported_count,"in_progress":in_progress_count,"resolved":resolved_count,"urgent":urgent_count,"resolution_rate":round(resolved_count/max(1,total_count)*100)}

    if current_user.is_admin:
        staff=eligible_staff_query().order_by(User.role,User.name).all()
        states=[r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]
        current_state=request.args.get("state","all"); current_district=request.args.get("district","all"); current_city=request.args.get("city_town","all")
    else:
        staff=eligible_staff_query().filter(User.state==current_user.state,User.district==current_user.district,User.city_town==current_user.city_town).order_by(User.role,User.name).all()
        states=[]; current_state=current_user.state; current_district=current_user.district; current_city=current_user.city_town

    return render_template("dashboard.html",issues=issues,stats=stats,states=states,workers=staff,current_status=status,current_category=category,current_priority=priority,current_state=current_state,current_district=current_district,current_city=current_city,current_sort=sort,search_q=q,current_role=current_user.role,date_from=date_from,date_to=date_to)

@app.route("/dashboard/issue/<int:issue_id>/update", methods=["POST"])
@login_required
def update_issue_status(issue_id):
    # Workers are NEVER allowed to change status
    if current_user.role == "worker":
        flash("Workers cannot change case status. Coordinate with the assigned authority.", "warning")
        return redirect(request.referrer or url_for("dashboard"))
    if not current_user.is_authenticated or current_user.role not in ("authority", "admin"):
        abort(403)
    issue=Issue.query.get_or_404(issue_id)
    if not current_user.is_admin and not (current_user.role == "authority" and current_user.is_verified and same_location(current_user, issue)):
        abort(403)
    new_status=request.form.get("status"); note=request.form.get("note","").strip()
    if new_status not in Config.STATUSES:
        flash("Invalid status specified.","error"); return redirect(request.referrer or url_for("dashboard"))
    old=issue.status; photo=save_upload(request.files.get("resolution_photo"))
    if photo: issue.resolution_photo_filename=photo
    issue.status=new_status; issue.resolved_at=datetime.utcnow() if new_status=="Resolved" else None
    db.session.add(StatusHistory(issue_id=issue.id,old_status=old,new_status=new_status,note=note or f"Status changed from {old} to {new_status} by {current_user.name}.",proof_photo=photo,changed_by_id=current_user.id))
    ids={issue.reporter_id}; ids.update(a.user_id for a in issue.assignments.filter(IssueAssignment.status.in_(["pending","accepted"])).all())
    for uid in ids:
        if uid!=current_user.id: notify(uid,issue.id,f"Case {issue.case_code} • {new_status}",f"{current_user.name} updated '{issue.title}' to {new_status}. {note}".strip())
    db.session.commit()
    flash(f"{issue.case_code} resolved and moved to history." if new_status=="Resolved" else f"{issue.case_code} updated to {new_status} and moved to the end of the queue.","success")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/dashboard/issue/<int:issue_id>/assign", methods=["POST"])
@authority_required
def assign_worker(issue_id):
    issue=Issue.query.get_or_404(issue_id)
    if not current_user.is_admin and not (current_user.role == "authority" and current_user.is_verified and same_location(current_user, issue)):
        abort(403)
    raw=request.form.get("user_id","").strip()
    if not raw.isdigit():
        flash("Select one worker or authority to add.","warning")
        return redirect(request.referrer or url_for("dashboard"))
    user=User.query.get(int(raw))
    if not user or user.role not in ("worker","authority"):
        flash("Only workers or authorities can be assigned.","warning")
        return redirect(request.referrer or url_for("dashboard"))
    if user.role == "authority" and not user.is_verified:
        flash("The selected authority is not admin-verified yet.","warning")
        return redirect(request.referrer or url_for("dashboard"))
    if not same_location(user, issue):
        flash("Only staff from the same State, District and City/Town can be assigned.","warning")
        return redirect(request.referrer or url_for("dashboard"))
    a=IssueAssignment.query.filter_by(issue_id=issue.id,user_id=user.id).first()
    if a and a.status in ("pending","accepted"):
        flash(f"{user.name} is already assigned to this case.","info")
        return redirect(request.referrer or url_for("dashboard"))
    if a:
        a.status="pending"; a.assigned_at=datetime.utcnow(); a.responded_at=None; a.assigned_by_id=current_user.id
    else:
        a=IssueAssignment(issue_id=issue.id,user_id=user.id,assigned_by_id=current_user.id,status="pending")
        db.session.add(a)
    if user.role == "worker" and not issue.assigned_to_id:
        issue.assigned_to_id=user.id
    notify(user.id,issue.id,"New Case Assignment",f"Case {issue.case_code} has been assigned to you by {current_user.name}.")
    if issue.status=="Reported":
        old=issue.status; issue.status="Acknowledged"; db.session.add(StatusHistory(issue_id=issue.id,old_status=old,new_status="Acknowledged",note=f"Case assigned to {user.name} ({user.role}).",changed_by_id=current_user.id))
    db.session.commit()
    flash(f"{user.name} added to {issue.case_code}.","success")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/dashboard/issue/<int:issue_id>/worker-update", methods=["POST"])
@login_required
def worker_update_issue_status(issue_id):
    flash("Workers cannot change case status. Coordinate with the assigned authority.","warning")
    return redirect(request.referrer or url_for("dashboard"))


# =========================================================================
# PROFILE EDIT (ALL ROLES — SELF EDIT)
# =========================================================================

@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def profile_edit():
    """Self-profile edit. Authority accounts are locked after admin verification — only admin can change them."""
    if current_user.role == "authority" and current_user.is_verified:
        flash("Your authority profile is admin-managed. Contact the administrator to update your details.", "info")
        return redirect(url_for("dashboard"))

    all_states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not name:
            flash("Name is required.", "error")
            return render_template("profile_edit.html", user=current_user, states=all_states)

        current_user.name = name
        current_user.phone = phone or None

        # Citizens may also update their location
        if current_user.role == "citizen":
            state = request.form.get("state") or None
            district = request.form.get("district") or None
            city_town = request.form.get("city_town") or None
            current_user.state = state
            current_user.district = district
            current_user.city_town = city_town

        # Profile photo
        photo = save_upload(request.files.get("profile_photo"))
        if photo:
            current_user.profile_photo = photo

        # Password change
        if new_password:
            if new_password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("profile_edit.html", user=current_user, states=all_states)
            if len(new_password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return render_template("profile_edit.html", user=current_user, states=all_states)
            current_user.set_password(new_password)

        db.session.commit()
        flash("Your profile has been updated successfully.", "success")
        if current_user.is_admin:
            return redirect(url_for("admin_panel"))
        if current_user.role in ("authority", "worker"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("index"))

    return render_template("profile_edit.html", user=current_user, states=all_states)


# =========================================================================
# ADMIN — EMPLOYEE MANAGEMENT (ADD / EDIT / DELETE / ACTIVITY)
# =========================================================================

@app.route("/admin/user/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_edit_user(user_id):
    """Admin edits any authority or worker's profile."""
    user = User.query.get_or_404(user_id)
    if user.role not in ("authority", "worker"):
        flash("Only authority and worker profiles can be edited from here.", "warning")
        return redirect(url_for("admin_panel"))

    all_states = [r[0] for r in db.session.query(Place.state).distinct().order_by(Place.state).all()]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        department = request.form.get("department", "").strip()
        state = request.form.get("state") or None
        district = request.form.get("district") or None
        city_town = request.form.get("city_town") or None
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not name:
            flash("Name is required.", "error")
            return render_template("admin_edit_user.html", user=user, states=all_states)

        user.name = name
        user.phone = phone or None
        user.department = department or None
        user.state = state
        user.district = district
        user.city_town = city_town

        # Profile photo
        photo = save_upload(request.files.get("profile_photo"))
        if photo:
            user.profile_photo = photo

        # Password reset by admin
        if new_password:
            if new_password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("admin_edit_user.html", user=user, states=all_states)
            if len(new_password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return render_template("admin_edit_user.html", user=user, states=all_states)
            user.set_password(new_password)

        # If location changed for an authority, cancel assignments that no longer match
        if user.role == "authority" and (state or district or city_town):
            for assignment in IssueAssignment.query.filter_by(user_id=user.id).filter(
                IssueAssignment.status.in_(["pending", "accepted"])
            ).all():
                issue = assignment.issue
                if not (
                    issue.state.casefold() == (state or "").casefold() and
                    issue.district.casefold() == (district or "").casefold() and
                    issue.city_town.casefold() == (city_town or "").casefold()
                ):
                    assignment.status = "cancelled"
                    assignment.responded_at = datetime.utcnow()
                    notify(user.id, issue.id, "Assignment Cancelled",
                           f"Your assignment for {issue.case_code} was cancelled because your jurisdiction was updated by admin.")

        db.session.commit()
        flash(f"{user.name}'s profile has been updated.", "success")
        return redirect(url_for("admin_panel"))

    return render_template("admin_edit_user.html", user=user, states=all_states)


@app.route("/admin/user/add", methods=["POST"])
@login_required
@admin_required
def admin_add_user():
    """Admin creates a new authority or worker account."""
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "worker")
    phone = request.form.get("phone", "").strip()
    department = request.form.get("department", "").strip()
    state = request.form.get("state") or None
    district = request.form.get("district") or None
    city_town = request.form.get("city_town") or None

    if not name or not email or not password:
        flash("Name, email and password are required.", "error")
        return redirect(url_for("admin_panel"))

    if role not in ("authority", "worker"):
        flash("Role must be authority or worker.", "error")
        return redirect(url_for("admin_panel"))

    if User.query.filter_by(email=email).first():
        flash("An account with that email already exists.", "error")
        return redirect(url_for("admin_panel"))

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin_panel"))

    profile_photo = save_upload(request.files.get("profile_photo"))

    # Admin-created accounts are auto-verified
    new_user = User(
        name=name,
        email=email,
        phone=phone or None,
        role=role,
        state=state,
        district=district,
        city_town=city_town,
        department=department or None,
        profile_photo=profile_photo,
        is_verified=True,  # Admin-created employees are automatically verified
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    flash(f"{role.title()} account for {name} created and verified successfully.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Admin permanently deletes an authority or worker account."""
    user = User.query.get_or_404(user_id)
    if user.role not in ("authority", "worker"):
        flash("Only authority and worker accounts can be deleted from here.", "warning")
        return redirect(url_for("admin_panel"))
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "warning")
        return redirect(url_for("admin_panel"))
    name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f"{name}'s account has been permanently deleted.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/user/<int:user_id>/activity")
@login_required
@admin_required
def admin_user_activity(user_id):
    """Admin views an employee's activity log: assignments and status changes."""
    user = User.query.get_or_404(user_id)
    if user.role not in ("authority", "worker"):
        flash("Activity log is only available for authority and worker accounts.", "warning")
        return redirect(url_for("admin_panel"))

    # Assignments this employee is involved in
    assignments = (
        IssueAssignment.query
        .filter_by(user_id=user.id)
        .order_by(IssueAssignment.assigned_at.desc())
        .limit(50)
        .all()
    )

    # Status changes this employee made
    status_changes = (
        StatusHistory.query
        .filter_by(changed_by_id=user.id)
        .order_by(StatusHistory.created_at.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "admin_user_activity.html",
        employee=user,
        assignments=assignments,
        status_changes=status_changes,
    )

# =========================================================================
# CLI COMMANDS (DB INIT & SEED DEMO DATA)
# =========================================================================

@app.cli.command("init-db")
def init_db():
    """Create database tables and load places dataset."""
    db.create_all()
    load_places_from_csv()
    print("Database initialized and places loaded successfully.")


@app.cli.command("load-places")
def cli_load_places():
    """Load places CSV into the places table."""
    load_places_from_csv()


def load_places_from_csv():
    csv_path = os.path.join(Config.BASE_DIR, "data", "places.csv")
    if not os.path.exists(csv_path):
        print(f"Places CSV not found at {csv_path}")
        return

    count = 0
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            st = row["state"].strip()
            dist = row["district"].strip()
            city = row["city_town"].strip()
            existing = Place.query.filter_by(state=st, district=dist, city_town=city).first()
            if not existing:
                db.session.add(Place(state=st, district=dist, city_town=city))
                count += 1
    db.session.commit()
    print(f"Loaded {count} places into database.")


@app.cli.command("seed-demo")
def seed_demo():
    """Populate database with demo accounts and rich issues for presentation."""
    seed_demo_data()


def seed_demo_data():
    db.create_all()
    load_places_from_csv()

    def upsert_user(email, **kwargs):
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(email=email)
            db.session.add(user)
        for key, value in kwargs.items():
            setattr(user, key, value)
        return user

    authority = upsert_user(
        "authority@civictrack.gov.in",
        name="Rajesh Sharma (Zonal Officer)",
        role="authority",
        state="Karnataka",
        district="Mysuru",
        city_town="Mysuru",
        department="Municipal Public Works",
        phone="+91 98450 12345",
        is_verified=True,
    )
    authority.set_password("authority123")

    worker = upsert_user(
        "worker@civictrack.gov.in",
        name="Suresh Kumar (Field Technician)",
        role="worker",
        state="Karnataka",
        district="Mysuru",
        city_town="Mysuru",
        department="Sanitation & Road Repair",
        phone="+91 98450 67890",
        is_verified=True,
    )
    worker.set_password("worker123")

    citizen = upsert_user(
        "citizen@civictrack.in",
        name="Priya Patel",
        role="citizen",
        state="Karnataka",
        district="Mysuru",
        city_town="Mysuru",
        phone="+91 97410 54321",
    )
    citizen.set_password("citizen123")

    citizen2 = upsert_user(
        "anand@example.com",
        name="Anand Varma",
        role="citizen",
        state="Karnataka",
        district="Bengaluru Urban",
        city_town="Indiranagar",
        phone="+91 96320 11223",
    )
    citizen2.set_password("citizen123")

    if Issue.query.first():
        db.session.commit()
        print("Demo accounts already seeded and issue data is present.")
        return

    db.session.commit()
    print("Demo accounts seeded. No predefined civic issues are created; real reports start the queue.")
    return

    # Sample Issues disabled: CivicTrack starts with real citizen reports.
    sample_issues = [
        {
            "title": "Hazardous open crater near Suburb Bus Stand",
            "desc": "Deep crater formed after monsoon rain. Two wheelers frequently swerving into oncoming traffic.",
            "category": "Roads & Potholes",
            "priority": "Urgent",
            "state": "Karnataka",
            "district": "Mysuru",
            "city": "Mysuru",
            "locality": "Near Suburb Bus Stand, Bengaluru-Nilgiri Road",
            "lat": 12.3051,
            "lng": 76.6552,
            "status": "In Progress",
            "upvotes": 34,
            "days_ago": 3,
        },
        {
            "title": "Overflowing commercial dumpster at Market Road",
            "desc": "Huge pile of rotting organic waste and plastic bags overflowing for 4 days. Severe stench and stray animals.",
            "category": "Waste & Garbage",
            "priority": "High",
            "state": "Karnataka",
            "district": "Mysuru",
            "city": "Mysuru",
            "locality": "Devaraja Market South Gate",
            "lat": 12.3090,
            "lng": 76.6510,
            "status": "Reported",
            "upvotes": 19,
            "days_ago": 1,
        },
        {
            "title": "Dark street due to non-functioning LED lights",
            "desc": "Entire stretch of 300 meters has non-working street lamps. Unsafe for evening commuters and college students.",
            "category": "Streetlights & Electricity",
            "priority": "Medium",
            "state": "Karnataka",
            "district": "Mysuru",
            "city": "Mysuru",
            "locality": "Kuvempunagar 4th Cross",
            "lat": 12.2890,
            "lng": 76.6340,
            "status": "Resolved",
            "upvotes": 42,
            "days_ago": 8,
        },
        {
            "title": "Major potable water pipeline burst flooding footpath",
            "desc": "High pressure clean drinking water gushing out from underground main pipe, wasting thousands of liters.",
            "category": "Water Supply & Drainage",
            "priority": "Urgent",
            "state": "Karnataka",
            "district": "Bengaluru Urban",
            "city": "Indiranagar",
            "locality": "100 Feet Road, Near Metro Station",
            "lat": 12.9784,
            "lng": 77.6408,
            "status": "In Progress",
            "upvotes": 28,
            "days_ago": 2,
        },
        {
            "title": "Traffic signal timer malfunctioning causing heavy gridlock",
            "desc": "Signal jumps straight from Red to Red without showing Green phase, causing massive jam during peak rush hour.",
            "category": "Public Safety & Traffic",
            "priority": "High",
            "state": "Karnataka",
            "district": "Bengaluru Urban",
            "city": "Koramangala",
            "locality": "Sony World Signal Junction",
            "lat": 12.9352,
            "lng": 77.6245,
            "status": "Reported",
            "upvotes": 15,
            "days_ago": 1,
        },
        {
            "title": "Uprooted tree branch obstructing dual carriageway",
            "desc": "Heavy branch snapped during thunderstorm and is blocking left vehicle lane near hospital entrance.",
            "category": "Parks & Trees",
            "priority": "High",
            "state": "Maharashtra",
            "district": "Mumbai City",
            "city": "Dadar",
            "locality": "Dadar TT Circle",
            "lat": 19.0178,
            "lng": 72.8478,
            "status": "Resolved",
            "upvotes": 25,
            "days_ago": 5,
        },
        {
            "title": "Broken pedestrian bridge stairs tile slabs",
            "desc": "Several concrete steps cracked and loose, elderly pedestrians slipping while climbing to railway footbridge.",
            "category": "Public Infrastructure",
            "priority": "Medium",
            "state": "Delhi",
            "district": "Central Delhi",
            "city": "Connaught Place",
            "locality": "Outer Circle, Block B",
            "lat": 28.6328,
            "lng": 77.2197,
            "status": "Reported",
            "upvotes": 11,
            "days_ago": 4,
        },
        {
            "title": "Open drainage manhole cover without safety red ribbon",
            "desc": "Cast iron cover removed for desilting and left open without barricade on pedestrian walkway.",
            "category": "Water Supply & Drainage",
            "priority": "Urgent",
            "state": "Telangana",
            "district": "Hyderabad",
            "city": "Madhapur",
            "locality": "Hitech City Main Road",
            "lat": 17.4483,
            "lng": 78.3808,
            "status": "In Progress",
            "upvotes": 53,
            "days_ago": 2,
        },
    ]

    for i, data in enumerate(sample_issues):
        ai_cat = ai_engine.predict_category(f"{data['title']} {data['desc']}")
        ai_prio = ai_engine.assess_priority_and_urgency(f"{data['title']} {data['desc']}", data["category"])
        ai_sum = ai_engine.generate_action_summary(data["title"], data["desc"], data["category"])

        created_dt = datetime.utcnow() - timedelta(days=data["days_ago"], hours=random.randint(1, 10))

        issue = Issue(
            case_code=f"LIT-{i+101:06d}",
            reporter_id=citizen.id if i % 2 == 0 else citizen2.id,
            assigned_to_id=worker.id if data["status"] in ["In Progress", "Resolved"] else None,
            title=data["title"],
            description=data["desc"],
            category=data["category"],
            priority=data["priority"],
            state=data["state"],
            district=data["district"],
            city_town=data["city"],
            locality_address=data["locality"],
            latitude=data["lat"],
            longitude=data["lng"],
            status=data["status"],
            upvote_count=data["upvotes"],
            ai_suggested_category=ai_cat["category"],
            ai_confidence=ai_cat["confidence"],
            ai_urgency_score=ai_prio["urgency_score"],
            ai_summary=ai_sum,
            created_at=created_dt,
            resolved_at=datetime.utcnow() - timedelta(days=1) if data["status"] == "Resolved" else None,
        )
        db.session.add(issue)
        db.session.flush()

        # Add history entries
        db.session.add(StatusHistory(
            issue_id=issue.id,
            old_status=None,
            new_status="Reported",
            note="Logged by citizen via CivicTrack portal.",
            changed_by_id=issue.reporter_id,
            created_at=created_dt,
        ))

        if data["status"] in ["In Progress", "Resolved"]:
            ack_dt = created_dt + timedelta(hours=6)
            db.session.add(StatusHistory(
                issue_id=issue.id,
                old_status="Reported",
                new_status="In Progress",
                note=f"Assigned to {worker.name} for site inspection and repair.",
                changed_by_id=authority.id,
                created_at=ack_dt,
            ))

        if data["status"] == "Resolved":
            res_dt = created_dt + timedelta(days=2)
            db.session.add(StatusHistory(
                issue_id=issue.id,
                old_status="In Progress",
                new_status="Resolved",
                note="Repair verified by field team. Work completed successfully.",
                changed_by_id=worker.id,
                created_at=res_dt,
            ))

    db.session.commit()
    print("Demo accounts & 8 realistic multi-city civic issues seeded successfully!")
    print("Authority Login: authority@civictrack.gov.in / authority123")
    print("Worker Login:    worker@civictrack.gov.in / worker123")
    print("Citizen Login:   citizen@civictrack.in / citizen123")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        load_places_from_csv()
    app.run(debug=True, port=5000)
