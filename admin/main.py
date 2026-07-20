from flask_admin.contrib import sqla
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.menu import MenuLink
from flask import redirect, url_for, flash
from flask_login import current_user
from markupsafe import Markup
from wtforms import validators
from flask_admin.theme import Bootstrap4Theme
from flask_admin.form import FileUploadField
from flask import Blueprint, current_app
import os

from admin.custom_fields import CropperImageField

from admin import db
from models import (
    User,
    FaceShape,
    ScanResult,
    Haircut,
    HairType,
    HaircutRecommendation,
    UserRecommendationHistory,
    AdminUser,
    AdminRole,
)


# Base class for authenticated admin views
class AuthenticatedModelView(sqla.ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_active

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_auth.login"))


# Base class for superadmin-only views
class SuperAdminModelView(sqla.ModelView):
    def is_accessible(self):
        return (
            current_user.is_authenticated
            and current_user.is_active
            and current_user.role == AdminRole.superadmin
        )

    def inaccessible_callback(self, name, **kwargs):
        flash("You do not have access to this page.", "danger")
        return redirect(url_for("admin.index"))


# Custom AdminIndexView with auth check
class AuthenticatedAdminIndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not current_user.is_authenticated:
            return redirect(url_for("admin_auth.login"))
        return super().index()


# Customized User model admin (app users)
class UserAdmin(AuthenticatedModelView):
    can_set_page_size = True
    page_size = 20
    column_list = ["id","username", "email", "created_at"]
    form_columns = ["username", "email", "password"]
    column_searchable_list = ["username", "email"]
    form_args = {
        "password": {
            "label": "Password",
            "validators": [validators.DataRequired()],
        }
    }


# Customized FaceShape model admin
class FaceShapeAdmin(AuthenticatedModelView):
    column_list = ["shape_name", "description"]
    form_columns = ["shape_name", "description"]


# Customized HairType model admin
class HairTypeAdmin(AuthenticatedModelView):
    column_list = ["type_name", "description"]
    form_columns = ["type_name", "description"]


# Customized ScanResult model admin
class ScanResultAdmin(AuthenticatedModelView):
    column_list = ["id", "user", "face_shape", "hair_type", "image_path", "scan_date"]
    form_columns = ["user", "face_shape", "hair_type", "image_path"]
    column_searchable_list = ["user.username", "face_shape.shape_name", "hair_type.type_name"]

    # Formatter untuk face_shape
    def _format_face_shape(self, context, model, name):
        return model.face_shape.shape_name if model.face_shape else "N/A"

    def _format_hair_type(self, context, model, name):
        return model.hair_type.type_name if model.hair_type else "N/A"

    # Formatter untuk user
    def _format_user(self, context, model, name):
        return model.user.username if model.user else "N/A"

   
    column_formatters = {
        "face_shape": _format_face_shape,
        "user": _format_user,
        "hair_type": _format_hair_type,
    }

    def __repr__(self):
        return f"<ScanResultAdmin(id={self.id})>"

# Customized HaircutRecommendation model admin
class HaircutRecommendationAdmin(AuthenticatedModelView):
    column_list = ["face_shape", "hair_type", "haircut", "id"]
    form_columns = ["face_shape", "hair_type", "haircut"]
    column_searchable_list = ["face_shape.shape_name", "hair_type.type_name"]

    def _format_haircut(view, context, model, name):
        return model.haircut.haircut_name if model.haircut else "N/A"

    def _format_face_shape(view, context, model, name):
        return model.face_shape.shape_name if model.face_shape else "N/A"

    def _format_hair_type(view, context, model, name):
        return model.hair_type.type_name if model.hair_type else "N/A"

    column_formatters = {
        "haircut": _format_haircut,
        "face_shape": _format_face_shape,
        "hair_type": _format_hair_type,
    }


# Customized UserRecommendationHistory model admin
class UserRecommendationHistoryAdmin(AuthenticatedModelView):
    column_list = ["user", "haircut_recommendation", "scan_result"]
    form_columns = ["user", "haircut_recommendation", "scan_result"]
    column_searchable_list = ["user.username", "haircut_recommendation.id"]

    def _format_user(view, context, model, name):
        return model.user.username if model.user else "N/A"

    def _format_haircut_recommendation(view, context, model, name):
        if model.haircut_recommendation and model.haircut_recommendation.haircut:
            return model.haircut_recommendation.haircut.haircut_name
        return "N/A"

    def _format_scan_result(view, context, model, name):
        return str(model.scan_result.id) if model.scan_result else "N/A"
    
    column_formatters = {
        "user": _format_user,
        "haircut_recommendation": _format_haircut_recommendation,
        "scan_result": _format_scan_result,
    }


def haircut_namegen(obj, filename):
    import werkzeug.utils
    import os
    import uuid
    ext = os.path.splitext(filename)[1] if filename else '.jpg'
    
    if hasattr(obj, 'haircut_name') and obj.haircut_name:
        # Use the inputted haircut name (converted to lowercase safe format)
        safe_name = werkzeug.utils.secure_filename(obj.haircut_name.lower())
        return f"{safe_name}{ext}"
    else:
        return f"haircut_{uuid.uuid4().hex[:8]}{ext}"


# Customized Haircut model admin
class HaircutAdmin(AuthenticatedModelView):
    column_list = ["haircut_name", "description", "image_path"]
    form_columns = ["haircut_name", "description", "image_path"]
    column_searchable_list = ["haircut_name", "description"]

    # 📂 Folder tujuan upload
    file_path = os.path.join(os.path.dirname(__file__), "..")

    # 📤 Upload field
    form_extra_fields = {
        'image_path': CropperImageField(
            'Image',
            base_path=file_path,
            relative_path='static/uploads/',
            namegen=haircut_namegen
        )
    }

    # 🖼️ Format kolom gambar
    def _format_image(self, context, model, name):
        if model.image_path:
            # Remove 'static/uploads/' if present
            filename = model.image_path.replace('static/uploads/', '')
            image_url = url_for('static', filename=f'uploads/{filename}')
            return Markup(f'<img src="{image_url}" style="max-height: 100px;">')
        return ""

    column_formatters = {
        "image_path": _format_image
    }

    def after_model_change(self, form, model, is_created):
        """Compress uploaded haircut images after save."""
        if model.image_path:
            from utils.image_compress import compress_existing_file
            full_path = os.path.join(self.file_path, model.image_path)
            if os.path.exists(full_path):
                new_path = compress_existing_file(full_path)
                # Update the DB path if extension changed
                new_relative = os.path.relpath(new_path, self.file_path)
                if new_relative != model.image_path:
                    model.image_path = new_relative
                    self.session.commit()

    def __repr__(self):
        return f"<HaircutAdmin(haircut_name={self.haircut_name})>"


# Admin User management (superadmin only)
class AdminUserAdmin(SuperAdminModelView):
    column_list = ["username", "email", "role", "is_active", "created_at"]
    form_columns = ["username", "email", "role", "is_active"]
    column_searchable_list = ["username", "email"]
    can_create = False  # Use register page instead
    column_labels = {
        "username": "Username",
        "email": "Email",
        "role": "Role",
        "is_active": "Active",
        "created_at": "Created At",
    }


# Create Admin instance with authenticated index view
admin_site = Admin(
    name="Admin Panel",
    theme=Bootstrap4Theme(swatch="default"),
    index_view=AuthenticatedAdminIndexView(),
)

# Add views for each model
admin_site.add_view(FaceShapeAdmin(FaceShape, db.session))
admin_site.add_view(HairTypeAdmin(HairType, db.session))
admin_site.add_view(HaircutAdmin(Haircut, db.session))
admin_site.add_view(HaircutRecommendationAdmin(HaircutRecommendation, db.session))
admin_site.add_view(UserAdmin(User, db.session, name="App Users", endpoint="app_users"))
admin_site.add_view(ScanResultAdmin(ScanResult, db.session))
admin_site.add_view(
    UserRecommendationHistoryAdmin(UserRecommendationHistory, db.session)
)
admin_site.add_view(AdminUserAdmin(AdminUser, db.session, name="Admin Users", endpoint="admin_users"))


# Custom MenuLinks with auth visibility
class LogoutMenuLink(MenuLink):
    def is_accessible(self):
        return current_user.is_authenticated


admin_site.add_link(LogoutMenuLink(name="🚪 Logout", url="/admin/logout"))

admin_bp = Blueprint("admin_bp", __name__)


@admin_bp.route("/")
def index():
    return redirect(
        url_for("admin.index")
    )
