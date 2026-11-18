# Vigil

**Interactive Cybersecurity Awareness and Learning Platform**

Vigil is a web-based cybersecurity awareness and learning platform designed to help users understand, practise and improve their cybersecurity knowledge through guided learning, scenario-based assessments and interactive simulations.

## Technology Stack

### Frontend
- React
- Vite
- JavaScript
- Tailwind CSS v4

### Backend
- Python
- Django
- Django REST Framework

### Database
- PostgreSQL
- Django ORM

### Development and Collaboration
- Git
- GitHub
- Postman
- Pytest
- pytest-django
- Vitest
- React Testing Library

## Core Features

- Guided cybersecurity learning modules
- Initial scenario-based knowledge assessment
- Module-specific quizzes
- Interactive cybersecurity simulations
- Password strength checker
- Personal learning progress reports
- Administrative dashboard and content management

## Project Structure

```text
Vigil/
├── frontend/
├── backend/
├── docs/
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

Install the following before setting up the project:

- Git
- Node.js (LTS recommended)
- npm (included with Node.js)
- Python 3
- PostgreSQL

### 1. Clone the Repository

```bash
git clone https://github.com/it-antara7592/Vigil.git
```

### 2. Navigate to the Project

```bash
cd Vigil
```

## Frontend Setup

### 3. Navigate to the Frontend

```bash
cd frontend
```

### 4. Install Dependencies

```bash
npm install
```

This installs the dependencies defined in the frontend's `package.json`.

### 5. Start the Frontend Development Server

```bash
npm run dev
```

Vite will provide a local development URL, usually:

```text
http://localhost:5173/
```

Open the URL in your browser to access the frontend.

### Frontend Build

To verify that the frontend builds successfully:

```bash
npm run build
```

## Backend Setup

### 6. Navigate to the Backend

Open a new terminal at the project root and run:

```powershell
cd backend
```

### 7. Create a Python Virtual Environment

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

The virtual environment keeps the backend's Python dependencies separate from other Python projects on your computer.

### 8. Install Backend Dependencies

```powershell
pip install -r requirements.txt
```

### 9. Configure Environment Variables

Create your local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Open `backend/.env` and replace the placeholder database password with your own PostgreSQL password.

The environment file contains the following configuration:

```env
DB_NAME=vigil_db
DB_USER=postgres
DB_PASSWORD=your_postgresql_password
DB_HOST=localhost
DB_PORT=5432
```

**Important:** Never commit your `.env` file or share your database password. The `.env` file is excluded through `.gitignore`.

### 10. Create the PostgreSQL Database

Make sure PostgreSQL is installed and running.

Using pgAdmin, create a database named:

```text
vigil_db
```

Set its owner to `postgres`, or update the database configuration in `.env` if you use a different database user.

### 11. Apply Database Migrations

From the `backend` directory, run:

```powershell
python manage.py migrate
```

This creates the database tables required by Django and its installed applications.

### 12. Start the Backend Development Server

```powershell
python manage.py runserver
```

The Django development server will usually be available at:

```text
http://127.0.0.1:8000/
```

### Backend Checks

To check the Django project configuration:

```powershell
python manage.py check
```

To run backend tests:

```powershell
python manage.py test
```

## Running Both Servers

The frontend and backend run independently during development.

Open two separate terminals:

| Application | Command | Local URL |
|---|---|---|
| Frontend | `npm run dev` | `http://localhost:5173/` |
| Backend | `python manage.py runserver` | `http://127.0.0.1:8000/` |

Make sure the Python virtual environment is activated in the backend terminal before running Django commands.

## Account Management

The backend currently includes the foundation for:

- Email and password registration and login.
- Session-based authentication.
- Learner and administrator account roles.
- Account deletion requests with a recovery grace period.
- Automatic cancellation of pending deletion after a successful login within the grace period.
- Administrator replacement and approval workflow.
- Reusable security audit event recording.

Administrator accounts are provisioned through a restricted management process rather than public registration.

## Learning Access Approach

- **Open learning:** Core courses and foundational lessons are accessible to everyone.
- **Registered learning:** Selected advanced lessons and case studies require registration.
- **Limited activities:** Quizzes and interactive simulations have access limits.
- **Personal progress:** Registered users can save their learning history and view personal progress reports.

## Project Status

Vigil is currently in initial development.

The frontend and backend foundations, PostgreSQL integration and initial account-management workflows have been established. Learning, assessment, simulation and progress features are part of the ongoing development.

## Safety and Privacy

Vigil uses fictional training scenarios and sample data. It is designed for cybersecurity awareness and safe educational practice.

User privacy and data protection are important considerations throughout the development of Vigil.