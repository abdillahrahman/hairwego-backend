import enum

import arrow
from sqlalchemy import cast
from sqlalchemy import sql
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy_utils import ArrowType
from sqlalchemy_utils import ChoiceType
from sqlalchemy_utils import ColorType
from sqlalchemy_utils import CurrencyType
from sqlalchemy_utils import EmailType
from sqlalchemy_utils import IPAddressType
from sqlalchemy_utils import TimezoneType
from sqlalchemy_utils import URLType

from admin import db


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), nullable=False, unique=True)         
    full_name = db.Column(db.String(32), nullable=False)                    
    email = db.Column(EmailType, nullable=False, unique=True)
    password = db.Column(db.String(225), nullable=False)                    
    created_at = db.Column(ArrowType, default=arrow.utcnow)

    def __repr__(self):
        return f"<User(username={self.username}, email={self.email}, full_name={self.full_name})>"

class FaceShape(db.Model):
    __tablename__ = 'face_shape'

    id = db.Column(db.Integer, primary_key=True)
    shape_name = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text, nullable=True)

    def __str__(self):
        return self.shape_name.title() if self.shape_name else "N/A"

    def __repr__(self):
        return f"<FaceShape(shape_name={self.shape_name})>"

class HairType(db.Model):
    __tablename__ = 'hair_type'

    id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text, nullable=True)

    def __str__(self):
        return self.type_name.title() if self.type_name else "N/A"

    def __repr__(self):
        return f"<HairType(type_name={self.type_name})>"

def jakarta_now():
    return arrow.utcnow().to('Asia/Jakarta')

class ScanResult(db.Model):
    __tablename__ = 'scan_result'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    image_path = db.Column(db.String(64), nullable=False)                   
    image_path_cropped = db.Column(db.String(64), nullable=False)
    face_shape_id = db.Column(db.Integer, db.ForeignKey('face_shape.id'), nullable=False)
    hair_type_id = db.Column(db.Integer, db.ForeignKey('hair_type.id'), nullable=True)
    face_shape_probabilities = db.Column(db.JSON, nullable=True)
    hair_type_probabilities = db.Column(db.JSON, nullable=True)
    scan_date = db.Column(ArrowType, default=jakarta_now)

    user = db.relationship('User', backref=db.backref('scan_results', lazy=True))
    face_shape = db.relationship('FaceShape', backref=db.backref('scan_results', lazy=True))
    hair_type = db.relationship('HairType', backref=db.backref('scan_results', lazy=True))

    def __repr__(self):
        return f"<ScanResult(user_id={self.user_id}, face_shape_id={self.face_shape_id}, hair_type_id={self.hair_type_id})>"
    
class Haircut(db.Model):
    __tablename__ = 'haircut'

    id = db.Column(db.Integer, primary_key=True)
    haircut_name = db.Column(db.String(32), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(64), nullable=True)                        

    def __str__(self):
        return self.haircut_name if self.haircut_name else "N/A"

    def __repr__(self):
        return f"<Haircut(name={self.haircut_name})>"
    
class HaircutRecommendation(db.Model):
    __tablename__ = 'haircut_recommendation'
    __table_args__ = (
    db.UniqueConstraint('face_shape_id', 'hair_type_id', 'haircut_id'),
)

    id = db.Column(db.Integer, primary_key=True)
    face_shape_id = db.Column(db.Integer, db.ForeignKey('face_shape.id'), nullable=False)
    hair_type_id = db.Column(db.Integer, db.ForeignKey('hair_type.id'), nullable=False)
    haircut_id = db.Column(db.Integer, db.ForeignKey('haircut.id'), nullable=False)

    face_shape = db.relationship('FaceShape', backref=db.backref('haircut_recommendations', lazy=True))
    hair_type = db.relationship('HairType', backref=db.backref('haircut_recommendations', lazy=True))
    haircut = db.relationship('Haircut', backref=db.backref('recommendations', lazy=True))

    def __repr__(self):
        return f"<HaircutRecommendation(id={self.id}, face_shape={self.face_shape_id}, hair_type={self.hair_type_id}, haircut={self.haircut_id})>"


class UserRecommendationHistory(db.Model):
    __tablename__ = 'user_recommendation_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    haircut_recommendation_id = db.Column(db.Integer, db.ForeignKey('haircut_recommendation.id'), nullable=False)
    scan_result_id = db.Column(db.Integer, db.ForeignKey('scan_result.id'), nullable=False)
    created_at = db.Column(ArrowType, default=jakarta_now)

    user = db.relationship('User', backref=db.backref('recommendation_histories', lazy=True))
    haircut_recommendation = db.relationship('HaircutRecommendation', backref=db.backref('recommendation_histories', lazy=True))
    scan_result = db.relationship('ScanResult', backref=db.backref('recommendation_histories', lazy=True))

    def __repr__(self):
        return f"<UserRecommendationHistory(user_id={self.user_id}, haircut_recommendation_id={self.haircut_recommendation_id}, scan_result_id={self.scan_result_id})>"


class TryOnHistory(db.Model):
    __tablename__ = 'tryon_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scan_result_id = db.Column(db.Integer, db.ForeignKey('scan_result.id'), nullable=True)
    haircut_id = db.Column(db.Integer, db.ForeignKey('haircut.id'), nullable=False)
    result_image_path = db.Column(db.String(128), nullable=False)
    created_at = db.Column(ArrowType, default=jakarta_now)

    user = db.relationship('User', backref=db.backref('tryon_histories', lazy=True))
    scan_result = db.relationship('ScanResult', backref=db.backref('tryon_histories', lazy=True))
    haircut = db.relationship('Haircut', backref=db.backref('tryon_histories', lazy=True))

    def __repr__(self):
        return f"<TryOnHistory(user_id={self.user_id}, haircut_id={self.haircut_id})>"


class AdminRole(enum.Enum):
    superadmin = "superadmin"
    admin = "admin"


class AdminUser(db.Model):
    __tablename__ = 'admin_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), nullable=False, unique=True)
    email = db.Column(EmailType, nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(AdminRole), nullable=False, default=AdminRole.admin)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(ArrowType, default=arrow.utcnow)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    @staticmethod
    def hash_password(password):
        import bcrypt
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        import bcrypt
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def __repr__(self):
        return f"<AdminUser(username={self.username}, role={self.role.value})>"
