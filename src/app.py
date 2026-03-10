import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Mergington High School API",
              description="API for viewing and signing up for extracurricular activities")

# Mount the static files directory
current_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=os.path.join(Path(__file__).parent,
          "static")), name="static")

DEFAULT_ACTIVITIES = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}

_default_db_path = current_dir / "data" / "activities.db"
DB_PATH = Path(os.environ["ACTIVITIES_DB_PATH"]) if "ACTIVITIES_DB_PATH" in os.environ else _default_db_path


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activities (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                schedule TEXT NOT NULL,
                max_participants INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_registrations (
                activity_name TEXT NOT NULL,
                email TEXT NOT NULL,
                PRIMARY KEY (activity_name, email),
                FOREIGN KEY (activity_name) REFERENCES activities(name) ON DELETE CASCADE
            );
            """
        )

        activity_count = connection.execute(
            "SELECT COUNT(*) AS count FROM activities"
        ).fetchone()["count"]

        if activity_count:
            return

        for name, details in DEFAULT_ACTIVITIES.items():
            connection.execute(
                """
                INSERT INTO activities (name, description, schedule, max_participants)
                VALUES (?, ?, ?, ?)
                """,
                (
                    name,
                    details["description"],
                    details["schedule"],
                    details["max_participants"],
                ),
            )

            connection.executemany(
                """
                INSERT INTO activity_registrations (activity_name, email)
                VALUES (?, ?)
                """,
                [(name, email) for email in details["participants"]],
            )


def fetch_activities():
    with get_connection() as connection:
        activity_rows = connection.execute(
            """
            SELECT name, description, schedule, max_participants
            FROM activities
            ORDER BY name
            """
        ).fetchall()

        registration_rows = connection.execute(
            """
            SELECT activity_name, email
            FROM activity_registrations
            ORDER BY activity_name, email
            """
        ).fetchall()

    participants_by_activity = {}
    for row in registration_rows:
        participants_by_activity.setdefault(row["activity_name"], []).append(row["email"])

    return {
        row["name"]: {
            "description": row["description"],
            "schedule": row["schedule"],
            "max_participants": row["max_participants"],
            "participants": participants_by_activity.get(row["name"], []),
        }
        for row in activity_rows
    }


def ensure_activity_exists(connection, activity_name: str):
    activity = connection.execute(
        """
        SELECT name, max_participants
        FROM activities
        WHERE name = ?
        """,
        (activity_name,),
    ).fetchone()

    if activity is None:
        raise HTTPException(status_code=404, detail="Activity not found")

    return activity


initialize_database()


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/activities")
def get_activities():
    return fetch_activities()


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    """Sign up a student for an activity"""
    with get_connection() as connection:
        activity = ensure_activity_exists(connection, activity_name)

        current_participant_count = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM activity_registrations
            WHERE activity_name = ?
            """,
            (activity_name,),
        ).fetchone()["count"]

        if current_participant_count >= activity["max_participants"]:
            raise HTTPException(status_code=400, detail="Activity is full")

        existing_registration = connection.execute(
            """
            SELECT 1
            FROM activity_registrations
            WHERE activity_name = ? AND email = ?
            """,
            (activity_name, email),
        ).fetchone()

        if existing_registration:
            raise HTTPException(
                status_code=400,
                detail="Student is already signed up"
            )

        connection.execute(
            """
            INSERT INTO activity_registrations (activity_name, email)
            VALUES (?, ?)
            """,
            (activity_name, email),
        )

    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(activity_name: str, email: str):
    """Unregister a student from an activity"""
    with get_connection() as connection:
        ensure_activity_exists(connection, activity_name)

        deleted_rows = connection.execute(
            """
            DELETE FROM activity_registrations
            WHERE activity_name = ? AND email = ?
            """,
            (activity_name, email),
        ).rowcount

        if not deleted_rows:
            raise HTTPException(
                status_code=400,
                detail="Student is not signed up for this activity"
            )

    return {"message": f"Unregistered {email} from {activity_name}"}
