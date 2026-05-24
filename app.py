"""
CivicPulse - Smart Civic Complaint Management System
Python/Flask Backend API
"""

import os
import uuid
import json
import random
import string
import warnings
from datetime import datetime, timezone, timedelta
from functools import wraps

import redis
import fakeredis
from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ── Configuration ───────────────────────────────────────────────────
_secret_key = os.environ.get('SECRET_KEY')
_jwt_secret  = os.environ.get('JWT_SECRET')

if not _secret_key:
    warnings.warn("SECRET_KEY env var not set — using insecure default. Do NOT use in production.", stacklevel=1)
    _secret_key = 'civic-pulse-secret-2024'

if not _jwt_secret:
    warnings.warn("JWT_SECRET env var not set — using insecure default. Do NOT use in production.", stacklevel=1)
    _jwt_secret = 'jwt-civic-secret-2024'

app.config['SECRET_KEY']                  = _secret_key
app.config['SQLALCHEMY_DATABASE_URI']     = os.environ.get('DATABASE_URL', 'sqlite:///civicpulse.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY']              = _jwt_secret
app.config['JWT_ACCESS_TOKEN_EXPIRES']    = timedelta(hours=24)
app.config['UPLOAD_FOLDER']              = 'uploads'
app.config['MAX_CONTENT_LENGTH']         = 16 * 1024 * 1024  # 16 MB max upload

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

CORS(app)
db  = SQLAlchemy(app)
jwt = JWTManager(app)

# ── Valkey Initialization ──────────────────────────────────────────
valkey_client = None
try:
    valkey_client = redis.Redis(
        host='localhost', port=6379, db=0,
        decode_responses=True, socket_connect_timeout=1
    )
    valkey_client.ping()
    print("Success: Connected to Valkey Server on localhost:6379")
except redis.exceptions.RedisError:
    print("Warning: Valkey server not found. Falling back to in-memory fake Valkey client.")
    valkey_client = fakeredis.FakeRedis(decode_responses=True)


def invalidate_stats_cache():
    try:
        valkey_client.delete("cache:admin_stats")
        app.logger.info("Invalidated admin stats cache in Valkey")
    except Exception as e:
        app.logger.warning(f"Valkey cache invalidation error: {e}")


os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ── Helpers ─────────────────────────────────────────────────────────
def _utcnow() -> datetime:
    """Timezone-aware UTC datetime (replaces deprecated datetime.utcnow)."""
    return datetime.now(timezone.utc)


# ── Models ──────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(200), unique=True, nullable=False)
    password   = db.Column(db.String(256), nullable=False)
    phone      = db.Column(db.String(20))
    role       = db.Column(db.String(20), default='citizen')  # citizen | admin
    district   = db.Column(db.String(100))
    state      = db.Column(db.String(100))
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    complaints = db.relationship('Complaint', backref='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'email': self.email,
            'phone': self.phone, 'role': self.role,
            'district': self.district, 'state': self.state,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
        }


class Department(db.Model):
    __tablename__ = 'departments'
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50))
    district = db.Column(db.String(100))
    state    = db.Column(db.String(100))
    head     = db.Column(db.String(120))
    email    = db.Column(db.String(200))
    phone    = db.Column(db.String(20))

    def to_dict(self):
        return {k: getattr(self, k) for k in
                ('id', 'name', 'category', 'district', 'state', 'head', 'email', 'phone')}


class Officer(db.Model):
    __tablename__ = 'officers'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    department    = db.relationship('Department', backref='officers')
    email         = db.Column(db.String(200))
    phone         = db.Column(db.String(20))
    district      = db.Column(db.String(100))
    is_active     = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name,
            'department': self.department.name if self.department else None,
            'department_id': self.department_id,
            'email': self.email, 'phone': self.phone,
            'district': self.district, 'is_active': self.is_active,
        }


class Complaint(db.Model):
    __tablename__ = 'complaints'
    id                  = db.Column(db.String(20), primary_key=True)   # CMP-XXXXXX
    title               = db.Column(db.String(250), nullable=False)
    description         = db.Column(db.Text, nullable=False)
    category            = db.Column(db.String(50), nullable=False)
    state               = db.Column(db.String(100), nullable=False)
    district            = db.Column(db.String(100), nullable=False)
    area                = db.Column(db.String(150))
    latitude            = db.Column(db.Float)
    longitude           = db.Column(db.Float)
    status              = db.Column(db.String(30), default='Pending')  # Pending | In Progress | Resolved
    priority            = db.Column(db.String(20), default='medium')   # low | medium | high | urgent
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_dept       = db.Column(db.String(150))
    assigned_officer_id = db.Column(db.Integer, db.ForeignKey('officers.id'), nullable=True)
    assigned_officer    = db.relationship('Officer', backref='complaints')
    images              = db.Column(db.Text)   # JSON list of filenames
    created_at          = db.Column(db.DateTime, default=_utcnow)
    updated_at          = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)
    remarks             = db.relationship('Remark', backref='complaint', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'category': self.category, 'state': self.state, 'district': self.district,
            'area': self.area, 'latitude': self.latitude, 'longitude': self.longitude,
            'status': self.status, 'priority': self.priority,
            'user_id': self.user_id,
            'user_name': self.user.name if self.user else None,
            'assigned_dept': self.assigned_dept,
            'assigned_officer': self.assigned_officer.to_dict() if self.assigned_officer else None,
            'images': json.loads(self.images) if self.images else [],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'remarks': [r.to_dict() for r in self.remarks],
        }


class Remark(db.Model):
    __tablename__ = 'remarks'
    id           = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(20), db.ForeignKey('complaints.id'))
    text         = db.Column(db.Text, nullable=False)
    author_id    = db.Column(db.Integer, db.ForeignKey('users.id'))
    author       = db.relationship('User')
    created_at   = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'text': self.text,
            'author': self.author.name if self.author else 'Unknown',
            'created_at': self.created_at.isoformat(),
        }


# ── Helpers ─────────────────────────────────────────────────────────
CATEGORY_DEPT_MAP = {
    'roads':       'PWD Department',
    'sanitation':  'GHMC / Municipal Corp',
    'water':       'Water Board',
    'electricity': 'Electricity Dept',
    'drainage':    'Drainage Department',
    'parks':       'Parks & Recreation',
    'noise':       'Pollution Control Board',
    'other':       'Municipal Corporation',
}

URGENT_KEYWORDS = [
    'accident', 'dangerous', 'emergency', 'severe', 'critical',
    'fire', 'flood', 'collapse', 'injury', 'urgent', 'immediate',
]

# Roles that citizens are NOT allowed to self-assign
_PROTECTED_ROLES = {'admin'}


def generate_complaint_id():
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'CMP-{suffix}'


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_uid() -> int:
    """Parse JWT identity to int, raising 401 on failure."""
    raw = get_jwt_identity()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        uid = _get_uid()
        if uid is None:
            return jsonify({'error': 'Invalid token identity'}), 401
        user = db.session.get(User, uid)
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return fn(*args, **kwargs)
    return wrapper


def valkey_rate_limit(limit=5, period=60):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not valkey_client:
                return fn(*args, **kwargs)

            ip       = request.remote_addr
            endpoint = request.path
            key      = f"rate_limit:{ip}:{endpoint}"

            try:
                current = valkey_client.get(key)
                if current and int(current) >= limit:
                    return jsonify({'error': 'Too many requests. Please try again later.'}), 429

                pipe = valkey_client.pipeline()
                pipe.incr(key)
                if not current:
                    pipe.expire(key, period)
                pipe.execute()
            except Exception as e:
                app.logger.warning(f"Valkey rate limiter error: {e}")

            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ── Auth Routes ──────────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
@valkey_rate_limit(limit=5, period=60)
def register():
    data = request.get_json()
    required = ['name', 'email', 'password']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400

    # Prevent role escalation: citizens cannot self-assign protected roles
    requested_role = data.get('role', 'citizen')
    if requested_role in _PROTECTED_ROLES:
        return jsonify({'error': 'Cannot self-assign that role'}), 403

    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 409

    user = User(
        name=data['name'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        phone=data.get('phone', ''),
        role=requested_role,
        district=data.get('district', ''),
        state=data.get('state', ''),
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({'token': token, 'user': user.to_dict()}), 201


@app.route('/api/auth/login', methods=['POST'])
@valkey_rate_limit(limit=5, period=60)
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()

    if not user or not check_password_hash(user.password, data.get('password', '')):
        return jsonify({'error': 'Invalid email or password'}), 401

    if not user.is_active:
        return jsonify({'error': 'Account deactivated. Contact support.'}), 403

    token = create_access_token(identity=str(user.id))
    return jsonify({'token': token, 'user': user.to_dict()})


@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    uid = _get_uid()
    if uid is None:
        return jsonify({'error': 'Invalid token'}), 401
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(user.to_dict())


# ── Complaint Routes ─────────────────────────────────────────────────
@app.route('/api/complaints', methods=['GET'])
@jwt_required()
def get_complaints():
    uid = _get_uid()
    if uid is None:
        return jsonify({'error': 'Invalid token'}), 401
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    query = Complaint.query
    if user.role == 'citizen':
        query = query.filter_by(user_id=uid)

    status   = request.args.get('status')
    category = request.args.get('category')
    district = request.args.get('district')
    priority = request.args.get('priority')
    search   = request.args.get('search', '')
    page_num = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    if status:   query = query.filter_by(status=status)
    if category: query = query.filter_by(category=category)
    if district: query = query.filter_by(district=district)
    if priority: query = query.filter_by(priority=priority)
    if search:
        like  = f'%{search}%'
        query = query.filter(
            db.or_(
                Complaint.title.ilike(like),
                Complaint.id.ilike(like),
                Complaint.description.ilike(like),
            )
        )

    query = query.order_by(Complaint.created_at.desc())
    pag   = query.paginate(page=page_num, per_page=per_page, error_out=False)

    return jsonify({
        'complaints': [c.to_dict() for c in pag.items],
        'total': pag.total, 'pages': pag.pages, 'page': page_num,
    })


@app.route('/api/complaints/<cid>', methods=['GET'])
@jwt_required()
def get_complaint(cid):
    uid = _get_uid()
    if uid is None:
        return jsonify({'error': 'Invalid token'}), 401
    c = db.session.get(Complaint, cid)
    if not c:
        return jsonify({'error': 'Complaint not found'}), 404
    user = db.session.get(User, uid)
    if user and user.role == 'citizen' and c.user_id != uid:
        return jsonify({'error': 'Access denied'}), 403
    return jsonify(c.to_dict())


@app.route('/api/complaints', methods=['POST'])
@jwt_required()
def create_complaint():
    uid = _get_uid()
    if uid is None:
        return jsonify({'error': 'Invalid token'}), 401
    data = request.get_json()

    required = ['title', 'description', 'category', 'state', 'district']
    if not all(k in data for k in required):
        return jsonify({'error': 'Missing required fields'}), 400

    dept = CATEGORY_DEPT_MAP.get(data['category'], 'Municipal Corporation')

    desc_lower    = data['description'].lower()
    auto_priority = data.get('priority', 'medium')
    if any(kw in desc_lower for kw in URGENT_KEYWORDS):
        auto_priority = 'urgent'

    # Generate a unique complaint ID
    cid = generate_complaint_id()
    while db.session.get(Complaint, cid):
        cid = generate_complaint_id()

    complaint = Complaint(
        id=cid,
        title=data['title'],
        description=data['description'],
        category=data['category'],
        state=data['state'],
        district=data['district'],
        area=data.get('area', ''),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        priority=auto_priority,
        user_id=uid,
        assigned_dept=dept,
        images='[]',
    )
    db.session.add(complaint)
    db.session.commit()
    invalidate_stats_cache()
    return jsonify(complaint.to_dict()), 201


@app.route('/api/complaints/<cid>', methods=['PATCH'])
@jwt_required()
def update_complaint(cid):
    uid = _get_uid()
    if uid is None:
        return jsonify({'error': 'Invalid token'}), 401
    user = db.session.get(User, uid)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    c = db.session.get(Complaint, cid)
    if not c:
        return jsonify({'error': 'Complaint not found'}), 404

    if user.role == 'citizen' and c.user_id != uid:
        return jsonify({'error': 'Access denied'}), 403

    data         = request.get_json()
    admin_fields = ['status', 'assigned_officer_id', 'priority']

    if user.role == 'admin':
        for f in admin_fields:
            if f in data:
                setattr(c, f, data[f])
        if 'remark' in data and data['remark'].strip():
            r = Remark(complaint_id=cid, text=data['remark'].strip(), author_id=uid)
            db.session.add(r)

    # Citizens can only update description/area while still Pending
    if user.role == 'citizen' and c.status == 'Pending':
        if 'description' in data: c.description = data['description']
        if 'area'        in data: c.area        = data['area']

    c.updated_at = _utcnow()
    db.session.commit()
    invalidate_stats_cache()
    return jsonify(c.to_dict())


@app.route('/api/complaints/<cid>/images', methods=['POST'])
@jwt_required()
def upload_image(cid):
    uid = _get_uid()
    if uid is None:
        return jsonify({'error': 'Invalid token'}), 401

    c = db.session.get(Complaint, cid)
    if not c:
        return jsonify({'error': 'Complaint not found'}), 404
    if c.user_id != uid:
        return jsonify({'error': 'Access denied'}), 403

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    path     = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)

    images = json.loads(c.images or '[]')
    images.append(filename)
    c.images = json.dumps(images)
    db.session.commit()

    return jsonify({'filename': filename, 'images': images}), 201


@app.route('/api/complaints/<cid>', methods=['DELETE'])
@admin_required
def delete_complaint(cid):
    c = db.session.get(Complaint, cid)
    if not c:
        return jsonify({'error': 'Complaint not found'}), 404
    db.session.delete(c)
    db.session.commit()
    invalidate_stats_cache()
    return jsonify({'message': 'Complaint deleted'})


# ── Admin Routes ─────────────────────────────────────────────────────
@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats():
    cache_key = "cache:admin_stats"

    try:
        cached = valkey_client.get(cache_key)
        if cached:
            app.logger.info("Serving admin stats from Valkey cache")
            return jsonify(json.loads(cached))
    except Exception as e:
        app.logger.warning(f"Valkey cache read error: {e}")

    total    = Complaint.query.count()
    pending  = Complaint.query.filter_by(status='Pending').count()
    progress = Complaint.query.filter_by(status='In Progress').count()
    resolved = Complaint.query.filter_by(status='Resolved').count()
    urgent   = Complaint.query.filter_by(priority='urgent').filter(
                   Complaint.status != 'Resolved').count()
    citizens = User.query.filter_by(role='citizen').count()

    # Single-pass breakdown over all complaints
    cat_counts  = {}
    dist_counts = {}
    for c in Complaint.query.with_entities(Complaint.category, Complaint.district).all():
        cat_counts[c.category]   = cat_counts.get(c.category, 0) + 1
        dist_counts[c.district]  = dist_counts.get(c.district, 0) + 1

    stats_data = {
        'total': total, 'pending': pending, 'in_progress': progress,
        'resolved': resolved, 'urgent': urgent, 'citizens': citizens,
        'resolution_rate': round(resolved / total * 100, 1) if total else 0,
        'category_breakdown': cat_counts,
        'district_breakdown': dist_counts,
    }

    try:
        valkey_client.setex(cache_key, 60, json.dumps(stats_data))
        app.logger.info("Saved fresh admin stats to Valkey cache")
    except Exception as e:
        app.logger.warning(f"Valkey cache write error: {e}")

    return jsonify(stats_data)


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users])


@app.route('/api/admin/users/<int:uid>', methods=['GET'])
@admin_required
def get_user(uid):
    u = db.session.get(User, uid)
    if not u:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(u.to_dict())


@app.route('/api/admin/users/<int:uid>/toggle', methods=['PATCH'])
@admin_required
def toggle_user(uid):
    u = db.session.get(User, uid)
    if not u:
        return jsonify({'error': 'User not found'}), 404
    u.is_active = not u.is_active
    db.session.commit()
    return jsonify(u.to_dict())


# ── Officers Routes ──────────────────────────────────────────────────
@app.route('/api/officers', methods=['GET'])
@jwt_required()
def list_officers():
    officers = Officer.query.filter_by(is_active=True).all()
    return jsonify([o.to_dict() for o in officers])


@app.route('/api/officers', methods=['POST'])
@admin_required
def create_officer():
    data = request.get_json()
    o = Officer(
        name=data['name'],
        department_id=data.get('department_id'),
        email=data.get('email'),
        phone=data.get('phone'),
        district=data.get('district'),
    )
    db.session.add(o)
    db.session.commit()
    return jsonify(o.to_dict()), 201


# ── Departments Routes ───────────────────────────────────────────────
@app.route('/api/departments', methods=['GET'])
@jwt_required()
def list_departments():
    depts = Department.query.all()
    return jsonify([d.to_dict() for d in depts])


# ── Analytics Routes ─────────────────────────────────────────────────
@app.route('/api/analytics/monthly', methods=['GET'])
@admin_required
def monthly_analytics():
    from sqlalchemy import extract, func
    results = db.session.query(
        extract('year', Complaint.created_at).label('year'),
        extract('month', Complaint.created_at).label('month'),
        func.count(Complaint.id).label('total'),
        func.sum(db.case((Complaint.status == 'Resolved', 1), else_=0)).label('resolved'),
    ).group_by('year', 'month').order_by('year', 'month').all()

    return jsonify([{
        'year': int(r.year), 'month': int(r.month),
        'total': r.total, 'resolved': int(r.resolved or 0)
    } for r in results])


# ── Locations API ────────────────────────────────────────────────────
STATES_DATA = {
    "Telangana": {
        "districts": ["Hyderabad", "Rangareddy", "Medchal", "Nalgonda", "Warangal", "Khammam"],
        "areas": {
            "Hyderabad": ["Banjara Hills", "Jubilee Hills", "Hitech City", "Gachibowli", "Kukatpally", "LB Nagar"],
            "Rangareddy": ["Shamshabad", "Rajendranagar", "Nanakramguda"],
        }
    },
    "Maharashtra": {
        "districts": ["Mumbai", "Pune", "Nagpur", "Nashik", "Aurangabad"],
        "areas": {"Mumbai": ["Andheri", "Bandra", "Dadar", "Kurla", "Borivali"]}
    },
}

@app.route('/api/locations/states', methods=['GET'])
def get_states():
    return jsonify(list(STATES_DATA.keys()))

@app.route('/api/locations/districts/<state>', methods=['GET'])
def get_districts(state):
    return jsonify(STATES_DATA.get(state, {}).get('districts', []))

@app.route('/api/locations/areas/<state>/<district>', methods=['GET'])
def get_areas(state, district):
    return jsonify(STATES_DATA.get(state, {}).get('areas', {}).get(district, []))


# ── Serve Uploaded Images ────────────────────────────────────────────
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ── Health Check ─────────────────────────────────────────────────────
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'CivicPulse API', 'version': '1.0.0'})


# ── Error Handlers ───────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500


# ── Seed Data ────────────────────────────────────────────────────────
def seed_db():
    if User.query.count() == 0:
        admin = User(
            name='Admin Officer', email='admin@civic.gov',
            password=generate_password_hash('admin123'),
            role='admin', district='Hyderabad', state='Telangana'
        )
        citizen = User(
            name='Ravi Shankar', email='ravi@gmail.com',
            password=generate_password_hash('ravi123'),
            role='citizen', district='Hyderabad', state='Telangana'
        )
        db.session.add_all([admin, citizen])
        db.session.commit()

    if Department.query.count() == 0:
        depts = [
            Department(name='PWD Department', category='roads',       district='Hyderabad', state='Telangana'),
            Department(name='GHMC',           category='sanitation',  district='Hyderabad', state='Telangana'),
            Department(name='HMWSSB',         category='water',       district='Hyderabad', state='Telangana'),
            Department(name='TSSPDCL',        category='electricity', district='Hyderabad', state='Telangana'),
        ]
        db.session.add_all(depts)
        db.session.commit()

    if Officer.query.count() == 0:
        officers = [
            Officer(name='Rajesh Kumar',  department_id=1, district='Hyderabad', email='rajesh@pwd.gov',       phone='9100000001'),
            Officer(name='Sunita Sharma', department_id=2, district='Hyderabad', email='sunita@ghmc.gov',      phone='9100000002'),
            Officer(name='Pradeep Nair',  department_id=3, district='Hyderabad', email='pradeep@hmwssb.gov',   phone='9100000003'),
            Officer(name='Anita Rao',     department_id=4, district='Hyderabad', email='anita@tsspdcl.gov',    phone='9100000004'),
        ]
        db.session.add_all(officers)
        db.session.commit()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_db()
        print("Success: CivicPulse DB initialized with seed data")
    app.run(debug=True, port=5000)
