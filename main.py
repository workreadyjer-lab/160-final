from flask import Flask
from flask import render_template, request, redirect, session, url_for
from sqlalchemy import create_engine, text
import random

app = Flask(__name__)
app.config["SECRET_KEY"] = "s3cr3tk3y"

con_str = "mysql://root:cset155@localhost/examdb"
engine = create_engine(con_str, echo = True)
conn = engine.connect()

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/register_account", methods=['GET', 'POST'])
def register_account():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")  # In production, hash this!
        role = request.form.get("role")
        
        try:
            # Insert into database
            query = text("""
                INSERT INTO accounts (name, email, password, role)
                VALUES (:name, :email, :password, :role)
            """)
            conn.execute(query, {
                "name": name,
                "email": email,
                "password": password,
                "role": role
            })
            conn.commit()
            return redirect(url_for("accounts"))
        except Exception as e:
            # Handle duplicate email or other errors
            return render_template("register.html", error=str(e))
    
    return render_template("register.html")

@app.route("/accounts")
def accounts():
    role_filter = request.args.get('role', 'all')

    if role_filter == 'all':
        query = text("select id, name, email, role from accounts")
        rows = conn.execute(query).fetchall()
    else:
        query = text("SELECT id, name, email, role FROM accounts WHERE role = :role")
        rows = conn.execute(query, {"role": role_filter}).fetchall()

# Create rows to list of dicts for template
    rows = [dict(row._mapping) for row in rows]

    return render_template("accounts.html", rows=rows, role_filter=role_filter)


@app.route("/tests")
def tests():
    query = text("""
    select t.test_id, t.name, a.name as teacher_name from tests t join accounts a on t.teacher_id = a.id
    """)
    rows = [dict(row._mapping) for row in conn.execute(query).fetchall()]
    return render_template("tests.html", rows=rows)

def tests_summary():
    pass

@app.route("/student_results")
def student_results():
    pass
if __name__ == "__main__":
    app.run(debug=True, port=5000)
