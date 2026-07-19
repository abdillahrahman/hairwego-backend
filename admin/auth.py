from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import AdminUser, AdminRole

admin_auth_bp = Blueprint(
    "admin_auth",
    __name__,
    template_folder="templates",
)


@admin_auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, go to admin
    if current_user.is_authenticated:
        return redirect(url_for("admin.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("admin/login.html")

        admin_user = AdminUser.query.filter_by(username=username).first()

        if admin_user and admin_user.check_password(password):
            if not admin_user.is_active:
                flash("Your account has been deactivated. Please contact the superadmin.", "danger")
                return render_template("admin/login.html")

            login_user(admin_user)
            flash(f"Welcome, {admin_user.username}!", "success")

            # Redirect to next page or admin index
            next_page = request.args.get("next")
            return redirect(next_page or url_for("admin.index"))
        else:
            flash("Incorrect username or password.", "danger")

    return render_template("admin/login.html")


@admin_auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("admin_auth.login"))


@admin_auth_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    # Only superadmin can register new admin users
    if current_user.role != AdminRole.superadmin:
        flash("Only superadmin can create new admin accounts.", "danger")
        return redirect(url_for("admin.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "admin")

        # Validation
        errors = []
        if not username:
            errors.append("Username is required.")
        if not email:
            errors.append("Email is required.")
        if not password:
            errors.append("Password is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm_password:
            errors.append("Password and confirm password do not match.")

        # Check if username/email already exists
        if AdminUser.query.filter_by(username=username).first():
            errors.append("Username is already taken.")
        if AdminUser.query.filter_by(email=email).first():
            errors.append("Email is already in use.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("admin/register.html")

        # Determine role
        admin_role = AdminRole.superadmin if role == "superadmin" else AdminRole.admin

        # Create new admin user
        new_admin = AdminUser(
            username=username,
            email=email,
            password_hash=AdminUser.hash_password(password),
            role=admin_role,
            is_active=True,
        )

        db.session.add(new_admin)
        db.session.commit()

        flash(f"Admin '{username}' created successfully with role {admin_role.value}.", "success")
        return redirect(url_for("admin_users.index_view"))

    return render_template("admin/register.html")


@admin_auth_bp.route("/setup", methods=["GET", "POST"])
def initial_setup():
    """
    Initial setup page - only accessible when no admin users exist.
    Creates the first superadmin account.
    """
    # If admin users already exist, redirect to login
    if AdminUser.query.first():
        return redirect(url_for("admin_auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        errors = []
        if not username:
            errors.append("Username is required.")
        if not email:
            errors.append("Email is required.")
        if not password:
            errors.append("Password is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm_password:
            errors.append("Password and confirm password do not match.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("admin/setup.html")

        # Create the first superadmin
        superadmin = AdminUser(
            username=username,
            email=email,
            password_hash=AdminUser.hash_password(password),
            role=AdminRole.superadmin,
            is_active=True,
        )

        db.session.add(superadmin)
        db.session.commit()

        login_user(superadmin)
        flash(f"Superadmin '{username}' created successfully! Welcome.", "success")
        return redirect(url_for("admin.index"))

    return render_template("admin/setup.html")
