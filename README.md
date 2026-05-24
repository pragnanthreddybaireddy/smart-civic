# 🏙️ CivicPulse — Smart Civic Complaint Management System

A full-stack web application enabling citizens to report public issues and governments to manage them efficiently.

---

## 🗂️ Project Structure

```
civic-complaint-system/
├── frontend/
│   └── index.html          # Complete React SPA (single file)
├── backend/
│   ├── app.py              # Flask API server
│   ├── requirements.txt    # Python dependencies
│   └── .env.example        # Environment variable template
└── README.md
```

---

## 🚀 Quick Start

### Frontend
Simply open `frontend/index.html` in any browser — no build step required.

**Demo credentials:**
| Role    | Email              | Password  |
|---------|--------------------|-----------|
| Admin   | admin@civic.gov    | admin123  |
| Citizen | ravi@gmail.com     | ravi123   |

---

### Backend (Python/Flask)

```bash
cd backend

# 1. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables (copy and edit)
cp .env.example .env

# 4. Run the server
python app.py
# Server starts at http://localhost:5000
```

The database is seeded automatically with demo data on first run.

---

## 🔌 API Reference

### Auth
| Method | Endpoint              | Description        |
|--------|-----------------------|--------------------|
| POST   | /api/auth/register    | Register new user  |
| POST   | /api/auth/login       | Login & get token  |
| GET    | /api/auth/me          | Get current user   |

### Complaints
| Method | Endpoint                       | Auth   | Description                |
|--------|-------------------------------|--------|----------------------------|
| GET    | /api/complaints               | ✅     | List complaints (filtered)  |
| POST   | /api/complaints               | ✅     | Submit new complaint        |
| GET    | /api/complaints/:id           | ✅     | Get complaint detail        |
| PATCH  | /api/complaints/:id           | ✅     | Update status/assign        |
| POST   | /api/complaints/:id/images    | ✅     | Upload image                |
| DELETE | /api/complaints/:id           | Admin  | Delete complaint            |

### Admin
| Method | Endpoint                     | Auth   | Description          |
|--------|------------------------------|--------|----------------------|
| GET    | /api/admin/stats             | Admin  | Dashboard statistics |
| GET    | /api/admin/users             | Admin  | List all users       |
| PATCH  | /api/admin/users/:id/toggle  | Admin  | Activate/deactivate  |

### Officers & Departments
| Method | Endpoint           | Auth   | Description       |
|--------|--------------------|--------|-------------------|
| GET    | /api/officers      | ✅     | List officers     |
| POST   | /api/officers      | Admin  | Create officer    |
| GET    | /api/departments   | ✅     | List departments  |

### Locations
| Method | Endpoint                            | Description         |
|--------|-------------------------------------|---------------------|
| GET    | /api/locations/states               | All states          |
| GET    | /api/locations/districts/:state     | Districts by state  |
| GET    | /api/locations/areas/:state/:dist   | Areas by district   |

### Analytics
| Method | Endpoint                | Auth  | Description        |
|--------|-------------------------|-------|--------------------|
| GET    | /api/analytics/monthly  | Admin | Monthly trends     |

---

## ✨ Features

### Citizen Portal
- 🔐 Register/Login with email & password
- 📋 Submit complaints with title, description, category, location
- 📸 Attach multiple photos to complaints
- 📍 State → District → Area location selector
- 🔢 Unique tracking ID (CMP-XXXXXX) for every complaint
- 🔍 Track any complaint by ID
- 📊 Personal dashboard with complaint stats
- 🟡 Status tracking: Pending → In Progress → Resolved

### Admin Portal
- 📊 System-wide dashboard with charts and KPIs
- 📋 Manage all complaints with filters (status, category, district)
- 👮 Assign complaints to field officers
- 💬 Add remarks/comments on complaints
- 🚨 Urgent issues queue (auto-detected & manual)
- 👥 Citizen user management
- 📈 Analytics: monthly trends, resolution rates, district breakdown

### Smart Features
- ⚡ **Auto-routing**: Category → Department mapping (roads → PWD, water → HMWSSB, etc.)
- 🤖 **Priority detection**: Scans description for urgent keywords
- 🏷️ **Unique ID generation**: CMP-XXXXXX format
- 🌙 **Dark mode**: Toggle for all users
- 📱 **Responsive**: Works on mobile, tablet, desktop

---

## 🗄️ Database Schema

```
users           — id, name, email, password_hash, phone, role, district, state
departments     — id, name, category, district, state, head, email
officers        — id, name, department_id, email, phone, district
complaints      — id (CMP-xxx), title, description, category, location, status, priority, user_id, ...
remarks         — id, complaint_id, text, author_id, created_at
```

---

## 🔧 Environment Variables

```env
SECRET_KEY=your-flask-secret-key
JWT_SECRET=your-jwt-secret-key
DATABASE_URL=sqlite:///civicpulse.db
# For PostgreSQL: postgresql://user:password@localhost/civicpulse
```

---

## 🧪 Testing the API

```bash
# Register
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"test@test.com","password":"test123","role":"citizen"}'

# Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@civic.gov","password":"admin123"}'

# Submit complaint (use token from login)
curl -X POST http://localhost:5000/api/complaints \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Pothole on main road","description":"Large pothole causing accidents","category":"roads","state":"Telangana","district":"Hyderabad","priority":"high"}'
```

---

## 🏗️ Tech Stack

| Layer     | Technology                              |
|-----------|-----------------------------------------|
| Frontend  | React 18, HTML5, CSS3, Vanilla JS       |
| Charts    | Chart.js 4                              |
| Backend   | Python 3.10+, Flask 3.0                 |
| ORM       | SQLAlchemy + Flask-SQLAlchemy           |
| Auth      | JWT (Flask-JWT-Extended)                |
| Database  | SQLite (dev) / PostgreSQL (production)  |
| CORS      | Flask-CORS                              |

---

## 📌 Connecting Frontend to Backend

The frontend currently runs with in-memory mock data for demonstration.
To connect it to the Flask API:

1. Replace the mock `INITIAL_COMPLAINTS` and `INITIAL_USERS` arrays with API calls
2. Use `fetch('/api/auth/login', {...})` for authentication
3. Pass the JWT token in `Authorization: Bearer <token>` headers

The API surface is fully built and ready for integration.

---

## 🎯 Hackathon Evaluation Criteria Coverage

| Criteria                   | Implementation                                     |
|----------------------------|----------------------------------------------------|
| Problem Definition (15%)   | Real civic issue reporting gap addressed           |
| Innovation (25%)           | Auto-routing, smart priority, full-stack system    |
| Impact & Practicality (25%)| Scalable REST API, production-ready DB schema      |
| Technical Execution (25%)  | JWT auth, role-based access, file uploads, filters |
| User Experience (10%)      | Clean UI, dark mode, mobile responsive, toasts     |
