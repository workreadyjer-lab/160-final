import os
import sqlite3
from datetime import datetime

from flask import Flask, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "exam.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "exam-secret-change-me"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS exam_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('teacher', 'student'))
        );

        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            teacher_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES exam_accounts(id)
        );

        CREATE TABLE IF NOT EXISTS test_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            position INTEGER NOT NULL,
            FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(test_id, student_id),
            FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES exam_accounts(id)
        );

        CREATE TABLE IF NOT EXISTS submission_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            answer_text TEXT,
            FOREIGN KEY (submission_id) REFERENCES test_submissions(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES test_questions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_grades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            grader_teacher_id INTEGER NOT NULL,
            total_marks REAL NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(test_id, student_id),
            FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES exam_accounts(id),
            FOREIGN KEY (grader_teacher_id) REFERENCES exam_accounts(id)
        );
        """
    )
    db.commit()


@app.before_request
def bootstrap():
    init_db()


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register_account():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]

        if role not in ("teacher", "student"):
            flash("Invalid role.", "danger")
            return redirect(url_for("register_account"))

        db = get_db()
        try:
            db.execute(
                "INSERT INTO exam_accounts (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (name, email, generate_password_hash(password), role),
            )
            db.commit()
            flash("Account created successfully.", "success")
            return redirect(url_for("accounts"))
        except sqlite3.IntegrityError:
            flash("Email already exists.", "danger")

    return render_template("register.html")


@app.route("/accounts")
def accounts():
    role_filter = request.args.get("role", "all")
    db = get_db()
    if role_filter in ("teacher", "student"):
        rows = db.execute(
            "SELECT * FROM exam_accounts WHERE role = ? ORDER BY id DESC", (role_filter,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM exam_accounts ORDER BY id DESC").fetchall()
        role_filter = "all"

    return render_template("accounts.html", rows=rows, role_filter=role_filter)


@app.route("/tests")
def tests():
    rows = get_db().execute(
        """
        SELECT t.*, a.name AS teacher_name
        FROM tests t
        JOIN exam_accounts a ON a.id = t.teacher_id
        ORDER BY t.id DESC
        """
    ).fetchall()
    return render_template("tests.html", rows=rows)


@app.route("/tests/new", methods=["GET", "POST"])
def create_test():
    db = get_db()
    teachers = db.execute(
        "SELECT id, name FROM exam_accounts WHERE role = 'teacher' ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        name = request.form["name"].strip()
        description = request.form.get("description", "").strip()
        teacher_id = request.form.get("teacher_id")
        raw_questions = request.form.get("questions", "")
        questions = [line.strip() for line in raw_questions.splitlines() if line.strip()]

        if not questions:
            flash("Add at least one question.", "danger")
            return render_template("test_form.html", teachers=teachers, test=None)

        cur = db.execute(
            "INSERT INTO tests (name, description, teacher_id, created_at) VALUES (?, ?, ?, ?)",
            (name, description, teacher_id, now_iso()),
        )
        test_id = cur.lastrowid
        for idx, question in enumerate(questions, start=1):
            db.execute(
                "INSERT INTO test_questions (test_id, question_text, position) VALUES (?, ?, ?)",
                (test_id, question, idx),
            )
        db.commit()
        flash("Test created.", "success")
        return redirect(url_for("tests"))

    return render_template("test_form.html", teachers=teachers, test=None)


@app.route("/tests/<int:test_id>/edit", methods=["GET", "POST"])
def edit_test(test_id):
    db = get_db()
    test = db.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("tests"))

    teachers = db.execute(
        "SELECT id, name FROM exam_accounts WHERE role = 'teacher' ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        name = request.form["name"].strip()
        description = request.form.get("description", "").strip()
        teacher_id = request.form.get("teacher_id")
        raw_questions = request.form.get("questions", "")
        questions = [line.strip() for line in raw_questions.splitlines() if line.strip()]

        if not questions:
            flash("Add at least one question.", "danger")
            return render_template("test_form.html", teachers=teachers, test=test)

        db.execute(
            "UPDATE tests SET name = ?, description = ?, teacher_id = ? WHERE id = ?",
            (name, description, teacher_id, test_id),
        )
        db.execute("DELETE FROM test_questions WHERE test_id = ?", (test_id,))
        for idx, question in enumerate(questions, start=1):
            db.execute(
                "INSERT INTO test_questions (test_id, question_text, position) VALUES (?, ?, ?)",
                (test_id, question, idx),
            )
        db.commit()
        flash("Test updated.", "success")
        return redirect(url_for("tests"))

    old_questions = db.execute(
        "SELECT question_text FROM test_questions WHERE test_id = ? ORDER BY position",
        (test_id,),
    ).fetchall()
    test = dict(test)
    test["questions_multiline"] = "\n".join([q["question_text"] for q in old_questions])
    return render_template("test_form.html", teachers=teachers, test=test)


@app.post("/tests/<int:test_id>/delete")
def delete_test(test_id):
    db = get_db()
    db.execute("DELETE FROM tests WHERE id = ?", (test_id,))
    db.commit()
    flash("Test deleted.", "success")
    return redirect(url_for("tests"))


@app.route("/tests/<int:test_id>/take", methods=["GET", "POST"])
def take_test(test_id):
    db = get_db()
    test = db.execute(
        """
        SELECT t.*, a.name AS teacher_name
        FROM tests t
        JOIN exam_accounts a ON a.id = t.teacher_id
        WHERE t.id = ?
        """,
        (test_id,),
    ).fetchone()
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("tests"))

    questions = db.execute(
        "SELECT * FROM test_questions WHERE test_id = ? ORDER BY position", (test_id,)
    ).fetchall()
    students = db.execute(
        "SELECT id, name FROM exam_accounts WHERE role = 'student' ORDER BY name"
    ).fetchall()

    if request.method == "POST":
        student_id = request.form.get("student_id")
        exists = db.execute(
            "SELECT id FROM test_submissions WHERE test_id = ? AND student_id = ?",
            (test_id, student_id),
        ).fetchone()
        if exists:
            flash("Student already took this test and cannot retake it.", "danger")
            return redirect(url_for("take_test", test_id=test_id))

        cur = db.execute(
            "INSERT INTO test_submissions (test_id, student_id, submitted_at) VALUES (?, ?, ?)",
            (test_id, student_id, now_iso()),
        )
        submission_id = cur.lastrowid
        for question in questions:
            answer = request.form.get(f"answer_{question['id']}", "").strip()
            db.execute(
                "INSERT INTO submission_answers (submission_id, question_id, answer_text) VALUES (?, ?, ?)",
                (submission_id, question["id"], answer),
            )
        db.commit()
        flash("Submission saved.", "success")
        return redirect(url_for("tests"))

    return render_template("take_test.html", test=test, questions=questions, students=students)


@app.route("/tests/<int:test_id>/responses")
def test_responses(test_id):
    db = get_db()
    test = db.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("tests"))

    submissions = db.execute(
        """
        SELECT s.id AS submission_id, s.student_id, s.submitted_at, st.name AS student_name
        FROM test_submissions s
        JOIN exam_accounts st ON st.id = s.student_id
        WHERE s.test_id = ?
        ORDER BY s.submitted_at DESC
        """,
        (test_id,),
    ).fetchall()

    answers_map = {}
    for sub in submissions:
        answers = db.execute(
            """
            SELECT q.question_text, a.answer_text
            FROM submission_answers a
            JOIN test_questions q ON q.id = a.question_id
            WHERE a.submission_id = ?
            ORDER BY q.position
            """,
            (sub["submission_id"],),
        ).fetchall()
        answers_map[sub["submission_id"]] = answers

    grades = db.execute("SELECT * FROM test_grades WHERE test_id = ?", (test_id,)).fetchall()
    grade_by_student = {g_row["student_id"]: g_row for g_row in grades}
    teachers = db.execute(
        "SELECT id, name FROM exam_accounts WHERE role = 'teacher' ORDER BY name"
    ).fetchall()

    return render_template(
        "responses.html",
        test=test,
        submissions=submissions,
        answers_map=answers_map,
        teachers=teachers,
        grade_by_student=grade_by_student,
    )


@app.post("/tests/<int:test_id>/grade/<int:student_id>")
def grade_student(test_id, student_id):
    db = get_db()
    teacher_id = request.form.get("teacher_id")
    marks = request.form.get("marks", "0").strip()
    try:
        total_marks = float(marks)
    except ValueError:
        flash("Marks must be numeric.", "danger")
        return redirect(url_for("test_responses", test_id=test_id))

    existing = db.execute(
        "SELECT id FROM test_grades WHERE test_id = ? AND student_id = ?",
        (test_id, student_id),
    ).fetchone()

    if existing:
        db.execute(
            """
            UPDATE test_grades
            SET grader_teacher_id = ?, total_marks = ?, updated_at = ?
            WHERE test_id = ? AND student_id = ?
            """,
            (teacher_id, total_marks, now_iso(), test_id, student_id),
        )
        flash("Grade updated.", "success")
    else:
        db.execute(
            """
            INSERT INTO test_grades (test_id, student_id, grader_teacher_id, total_marks, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (test_id, student_id, teacher_id, total_marks, now_iso()),
        )
        flash("Grade saved.", "success")

    db.commit()
    return redirect(url_for("test_responses", test_id=test_id))


@app.route("/tests/summary")
def tests_summary():
    rows = get_db().execute(
        """
        SELECT t.id, t.name, a.name AS teacher_name, COUNT(s.id) AS taken_count
        FROM tests t
        JOIN exam_accounts a ON a.id = t.teacher_id
        LEFT JOIN test_submissions s ON s.test_id = t.id
        GROUP BY t.id, t.name, a.name
        ORDER BY t.id DESC
        """
    ).fetchall()
    return render_template("summary.html", rows=rows)


@app.route("/tests/<int:test_id>/results")
def test_results(test_id):
    db = get_db()
    test = db.execute("SELECT * FROM tests WHERE id = ?", (test_id,)).fetchone()
    if not test:
        flash("Test not found.", "danger")
        return redirect(url_for("tests_summary"))

    rows = db.execute(
        """
        SELECT st.name AS student_name,
               COALESCE(g.total_marks, 0) AS marks,
               gt.name AS graded_by
        FROM test_submissions s
        JOIN exam_accounts st ON st.id = s.student_id
        LEFT JOIN test_grades g ON g.test_id = s.test_id AND g.student_id = s.student_id
        LEFT JOIN exam_accounts gt ON gt.id = g.grader_teacher_id
        WHERE s.test_id = ?
        ORDER BY st.name
        """,
        (test_id,),
    ).fetchall()
    return render_template("test_results.html", test=test, rows=rows)


@app.route("/students/<int:student_id>/results")
def student_results(student_id):
    db = get_db()
    student = db.execute(
        "SELECT * FROM exam_accounts WHERE id = ? AND role = 'student'", (student_id,)
    ).fetchone()
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("accounts"))

    rows = db.execute(
        """
        SELECT t.name AS test_name, COALESCE(g.total_marks, 0) AS marks
        FROM test_submissions s
        JOIN tests t ON t.id = s.test_id
        LEFT JOIN test_grades g ON g.test_id = s.test_id AND g.student_id = s.student_id
        WHERE s.student_id = ?
        ORDER BY s.submitted_at DESC
        """,
        (student_id,),
    ).fetchall()
    return render_template("student_results.html", student=student, rows=rows)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
