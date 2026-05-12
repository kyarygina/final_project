from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import re
from werkzeug.utils import secure_filename
import random
import requests
from flask import jsonify
from datetime import date, datetime
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "change_this_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif"}

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)


class FootballField(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    photo = db.Column(db.String(255), nullable=True)
    field_type = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    price = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(50), nullable=False)


class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_date = db.Column(db.String(20), nullable=False)

    votes = db.relationship("Vote", backref="poll", cascade="all, delete-orphan")


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)

    answer = db.Column(db.String(20), nullable=False)

    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("user_id", "poll_id", name="unique_user_poll_vote"),
    )


class TeamResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    poll_id = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)

    team_a = db.Column(db.Text, nullable=False)
    team_b = db.Column(db.Text, nullable=False)

    poll = db.relationship("Poll")


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


def is_valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9!@#$%^&*_\-+=?.]+", username))


def is_valid_password(password):
    return bool(re.fullmatch(r"[A-Za-z0-9!@#$%^&*_\-+=?.]+", password))


def is_valid_name(name):
    return bool(re.fullmatch(r"[A-Za-zА-Яа-яЁё]+", name))


def login_required():
    if not session.get("user_id"):
        flash("Для доступа к этой странице необходимо войти в аккаунт.")
        return False
    return True


def format_short_date(date_string):
    date_obj = datetime.strptime(date_string, "%Y-%m-%d")
    return date_obj.strftime("%d.%m")


def get_weather_icon(weather_code):
    if weather_code in [0, 1]:
        return "☀️"
    if weather_code in [2, 3, 45, 48]:
        return "☁️"
    if weather_code in [51, 53, 55, 61, 63, 65, 80, 81, 82]:
        return "🌧️"
    if weather_code in [71, 73, 75, 77, 85, 86]:
        return "❄️"
    return "🌤️"


def get_weather_for_date(selected_date):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": 51.5331,
        "longitude": 46.0342,
        "hourly": "temperature_2m,weather_code",
        "timezone": "Europe/Saratov",
        "forecast_days": 16
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()
    hourly = data["hourly"]

    target_time = f"{selected_date}T18:00"

    if target_time not in hourly["time"]:
        return {
            "date": format_short_date(selected_date),
            "temp_evening": "нет данных",
            "icon": "❔",
            "description": "Прогноз недоступен"
        }

    index = hourly["time"].index(target_time)
    weather_code = hourly["weather_code"][index]

    return {
        "date": format_short_date(selected_date),
        "temp_evening": hourly["temperature_2m"][index],
        "icon": get_weather_icon(weather_code),
        "description": "Прогноз на вечер"
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]

        if not is_valid_username(username):
            flash("Логин может содержать только латинские буквы, цифры и спецсимволы.")
            return redirect(url_for("register"))

        if not is_valid_password(password):
            flash("Пароль может содержать только латинские буквы, цифры и спецсимволы.")
            return redirect(url_for("register"))

        if not is_valid_name(first_name) or not is_valid_name(last_name):
            flash("Имя и фамилия могут содержать только кириллицу или латиницу.")
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            flash("Пользователь с таким логином уже существует.")
            return redirect(url_for("register"))

        new_user = User(
            username=username,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Регистрация прошла успешно. Теперь войдите в аккаунт.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard"))

        flash("Неверный логин или пароль.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/fields/add", methods=["GET", "POST"])
def add_field():
    if not session.get("user_id"):
        flash("Для добавления площадки необходимо войти в аккаунт.")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        field_type = request.form["field_type"]
        address = request.form["address"]
        price = request.form["price"]
        phone = request.form["phone"]

        photo_file = request.files.get("photo")
        photo_filename = None

        if photo_file and photo_file.filename:
            if allowed_file(photo_file.filename):
                photo_filename = secure_filename(photo_file.filename)
                photo_path = os.path.join(app.config["UPLOAD_FOLDER"], photo_filename)
                photo_file.save(photo_path)
            else:
                flash("Можно загружать только изображения: png, jpg, jpeg, gif.")
                return redirect(url_for("add_field"))

        new_field = FootballField(
            name=name,
            photo=photo_filename,
            field_type=field_type,
            address=address,
            price=price,
            phone=phone
        )

        db.session.add(new_field)
        db.session.commit()

        flash("Площадка успешно добавлена.")
        return redirect(url_for("dashboard"))

    return render_template("field_form.html", field=None)


@app.route("/fields/edit/<int:field_id>", methods=["POST"])
def edit_field(field_id):
    if not login_required():
        return redirect(url_for("login"))

    field = FootballField.query.get_or_404(field_id)

    field.name = request.form["name"]
    field.field_type = request.form["field_type"]
    field.address = request.form["address"]
    field.price = request.form["price"]
    field.phone = request.form["phone"]

    photo_file = request.files.get("photo")

    if photo_file and photo_file.filename:
        if allowed_file(photo_file.filename):
            photo_filename = secure_filename(photo_file.filename)
            photo_path = os.path.join(app.config["UPLOAD_FOLDER"], photo_filename)
            photo_file.save(photo_path)
            field.photo = photo_filename
        else:
            flash("Можно загружать только изображения: png, jpg, jpeg, gif.")
            return redirect(url_for("dashboard"))

    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    # Площадки
    fields = FootballField.query.all()

    # Текущая дата
    today = date.today().isoformat()

    # Активное голосование (одно)
    active_poll = Poll.query.order_by(Poll.id.desc()).first()

    # Дата для погоды
    weather_date = active_poll.match_date if active_poll else today

    # Погода
    try:
        weather = get_weather_for_date(weather_date)
    except Exception:
        weather = {
            "date": format_short_date(weather_date),
            "temp_evening": "нет данных",
            "icon": "❔"
        }

    # Голоса
    votes_playing = []
    votes_not_playing = []

    # Результат команд
    team_result = None

    if active_poll:
        votes_playing = Vote.query.filter_by(
            poll_id=active_poll.id,
            answer="playing"
        ).all()

        votes_not_playing = Vote.query.filter_by(
            poll_id=active_poll.id,
            answer="not_playing"
        ).all()

        team_result = TeamResult.query.filter_by(
            poll_id=active_poll.id
        ).order_by(TeamResult.id.desc()).first()

    return render_template(
        "dashboard.html",
        fields=fields,
        today=today,
        weather=weather,
        active_poll=active_poll,
        votes_playing=votes_playing,
        votes_not_playing=votes_not_playing,
        team_result=team_result
    )


@app.route("/api/create-active-poll", methods=["POST"])
def api_create_active_poll():
    if not login_required():
        return jsonify({"error": "unauthorized"}), 401

    selected_date = request.json["date"]

    selected_date = request.json["date"]

    if selected_date < date.today().isoformat():
        return jsonify({"error": "Нельзя выбрать прошедшую дату."})

    existing_poll = Poll.query.order_by(Poll.id.desc()).first()

    if existing_poll:
        return jsonify({"error": "Голосование уже создано."})

    poll = Poll(match_date=selected_date)

    db.session.add(poll)
    db.session.commit()

    return jsonify({"success": True})


@app.route("/api/vote-active", methods=["POST"])
def api_vote_active():
    if not login_required():
        return jsonify({"error": "unauthorized"}), 401

    answer = request.json["answer"]
    user_id = session["user_id"]

    poll = Poll.query.order_by(Poll.id.desc()).first()

    if not poll:
        return jsonify({"error": "Голосование не создано."})

    vote = Vote.query.filter_by(
        user_id=user_id,
        poll_id=poll.id
    ).first()

    if vote:
        vote.answer = answer
    else:
        vote = Vote(
            user_id=user_id,
            poll_id=poll.id,
            answer=answer
        )
        db.session.add(vote)

    TeamResult.query.filter_by(poll_id=poll.id).delete()

    db.session.commit()

    return jsonify({"success": True})


@app.route("/api/split-active-teams", methods=["POST"])
def api_split_active_teams():
    if not login_required():
        return jsonify({"error": "unauthorized"}), 401

    poll = Poll.query.order_by(Poll.id.desc()).first()

    if not poll:
        return jsonify({"error": "Голосование не создано."})

    votes = Vote.query.filter_by(
        poll_id=poll.id,
        answer="playing"
    ).all()

    players = [
        f"{vote.user.last_name} {vote.user.first_name}"
        for vote in votes
    ]

    if len(players) < 2:
        return jsonify({"error": "Для распределения нужно минимум 2 игрока."})

    random.shuffle(players)

    middle = len(players) // 2

    team_a = players[:middle]
    team_b = players[middle:]

    TeamResult.query.filter_by(poll_id=poll.id).delete()

    result = TeamResult(
        poll_id=poll.id,
        team_a=", ".join(team_a),
        team_b=", ".join(team_b)
    )

    db.session.add(result)
    db.session.commit()

    return jsonify({
        "success": True,
        "team_a": team_a,
        "team_b": team_b
    })


@app.route("/api/finish-active-poll", methods=["POST"])
def api_finish_active_poll():
    if not login_required():
        return jsonify({"error": "unauthorized"}), 401

    poll = Poll.query.order_by(Poll.id.desc()).first()

    if poll:
        TeamResult.query.filter_by(poll_id=poll.id).delete()
        Vote.query.filter_by(poll_id=poll.id).delete()
        db.session.delete(poll)
        db.session.commit()

    return jsonify({"success": True})


@app.route("/fields/delete/<int:field_id>", methods=["POST"])
def delete_field(field_id):
    if not login_required():
        return redirect(url_for("login"))

    field = FootballField.query.get_or_404(field_id)

    db.session.delete(field)
    db.session.commit()

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(debug=True)
