import sqlite3
import os

DB_PATH = "database/attendance.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs("database", exist_ok=True)

    with get_db() as conn:
        cur = conn.cursor()

        cur.executescript("""
            -- Professors log in with email + a one-time code (no passwords).
            CREATE TABLE IF NOT EXISTS teachers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT UNIQUE NOT NULL,
                name       TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            -- Subjects / classes (Data Science & AI, Cyber Security, ...).
            -- Shared across all professors; anyone can add more from the dashboard.
            CREATE TABLE IF NOT EXISTS subjects (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT UNIQUE NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (created_by) REFERENCES teachers(id)
            );

            -- Students are enrolled under exactly one subject.
            CREATE TABLE IF NOT EXISTS students (
                student_id TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                major      TEXT,
                subject_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (subject_id) REFERENCES subjects(id)
            );

            -- One QR attendance session, scoped to a subject.
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                id         TEXT PRIMARY KEY,
                subject_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at   TEXT,
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(id)
            );

            -- Full history of every student check-in, kept forever per subject/session.
            CREATE TABLE IF NOT EXISTS attendance_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL,
                student_id  TEXT NOT NULL,
                device_id   TEXT,
                timestamp   TEXT NOT NULL,
                UNIQUE(session_id, student_id),
                UNIQUE(session_id, device_id),
                FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            );

            -- Phone/device registry: one phone binds permanently to one student,
            -- so a single phone cannot be used to check in for multiple students.
            CREATE TABLE IF NOT EXISTS devices (
                device_id   TEXT PRIMARY KEY,
                student_id  TEXT NOT NULL,
                first_seen  TEXT NOT NULL,
                FOREIGN KEY (student_id) REFERENCES students(student_id)
            );
        """)

        # Seed a couple of demo professors (login is by email code, no password).
        demo_teachers = [
            ("professor1@camtech.edu.kh", "Professor Dara"),
            ("professor2@camtech.edu.kh", "Professor Sophea"),
        ]
        cur.executemany(
            "INSERT OR IGNORE INTO teachers (email, name) VALUES (?, ?)",
            demo_teachers,
        )

        # Seed starter subjects — more can be added from the dashboard.
        starter_subjects = ["Data Science & AI", "Cyber Security"]
        cur.executemany(
            "INSERT OR IGNORE INTO subjects (name) VALUES (?)",
            [(s,) for s in starter_subjects],
        )
        conn.commit()

        # Seed a few sample students under the first subject, if empty.
        dsa_id = cur.execute(
            "SELECT id FROM subjects WHERE name = ?", ("Data Science & AI",)
        ).fetchone()["id"]
        sample_students = [
            ("6026010074", "Pich Soksovann", "Data Science & AI", dsa_id),
            ("6026010075", "Student 75", "Data Science & AI", dsa_id),
            ("6026010087", "Student 87", "Data Science & AI", dsa_id),
        ]
        cur.executemany(
            """INSERT OR IGNORE INTO students (student_id, name, major, subject_id)
               VALUES (?, ?, ?, ?)""",
            sample_students,
        )
        conn.commit()
