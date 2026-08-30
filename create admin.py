from app import app, db
from models import User


def create_admin():
    print("\n========== CREATE ADMIN ==========\n")
    name = input("Enter admin name: ").strip() or "System Admin"
    email = input("Enter admin email: ").strip().lower()
    password = input("Enter admin password: ")
    confirm = input("Confirm admin password: ")

    if not email or not password:
        print("❌ Email and password are required.")
        return
    if password != confirm:
        print("❌ Passwords do not match.")
        return
    if User.query.filter_by(email=email).first():
        print(f"❌ User with email {email} already exists.")
        return

    admin = User(name=name, email=email, role="admin", is_verified=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"\n✅ Admin created successfully: {email}")


def delete_admin():
    print("\n========== DELETE ADMIN ==========\n")
    email = input("Enter admin email to delete: ").strip().lower()
    admin = User.query.filter_by(email=email, role="admin").first()
    if not admin:
        print(f"❌ No admin found with email: {email}")
        return
    print(f"Admin: {admin.name} <{admin.email}>")
    confirm = input("Are you sure? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Delete cancelled.")
        return
    db.session.delete(admin)
    db.session.commit()
    print("✅ Admin deleted successfully.")


if __name__ == "__main__":
    with app.app_context():
        print("\n================================")
        print("       CIVICTRACK ADMIN")
        print("================================")
        print("1. Create Admin")
        print("2. Delete Admin")
        print("3. Exit")
        choice = input("\nEnter your choice (1/2/3): ").strip()
        if choice == "1":
            create_admin()
        elif choice == "2":
            delete_admin()
        else:
            print("Exiting...")
