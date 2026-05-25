from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, date
import json
import os
import uuid

app = Flask(__name__)
app.secret_key = "wagon_repair_secret_2024"

# ─── In-memory "database" ───────────────────────────────────────────────────
DB = {
    "wagons": {},          # wagon_id -> wagon info
    "opzs_docs": {},       # doc_id -> ОПЗС document
    "kp_arrival": {},      # doc_id -> КП приход документ
    "kp_departure": {},    # doc_id -> КП выход документ
    "roller_docs": {},     # doc_id -> роликовый участок
    "nakatka_docs": {},    # doc_id -> настурный колесный лист
    "users": {
        "nachalnik": {"password": "1", "role": "nachalnik", "name": "Начальник цеха"},
        "master_auto": {"password": "1", "role": "master", "name": "Мастер (Автосцепка)", "uchastok": "avtosteepka"},
        "master_telega": {"password": "1", "role": "master", "name": "Мастер (Тележечный)", "uchastok": "tележечный"},
        "master_akp": {"password": "1", "role": "master", "name": "Мастер (АКП)", "uchastok": "akp"},
        "master_roller": {"password": "1", "role": "master_roller", "name": "Мастер (Роликовый)", "uchastok": "роликовый"},
        "defekt1": {"password": "1", "role": "defektoskopist", "name": "Дефектоскопист", "uchastok": "колесный"},
    }
}

# ─── Reference data ──────────────────────────────────────────────────────────
DETAILS_NUMBERED = [
    "Автосцепка СА-3", "Поглощающий аппарат", "Тяговый хомут",
    "Надрессорная балка", "Боковая рама", "Колёсная пара",
    "Шкворень", "Центральный пятник", "Подпятник"
]

DETAILS_UNNUMBERED = [
    "Клин тягового хомута", "Валик подъёмника", "Замок автосцепки",
    "Замкодержатель", "Предохранитель", "Подъёмник замка",
    "Маятниковый подвесник", "Центрирующая балочка", "Маятниковая подвеска",
    "Пружина поглощающего аппарата", "Прокладка поддерживающей планки"
]

DETAIL_TYPES = {
    "Автосцепка СА-3": {
        "types": ["Тип А (старый)", "Тип Б (новый)", "Тип В (усиленный)"],
        "parts_by_type": {
            "Тип А (старый)": ["Корпус СА-3 тип А", "Замок тип А", "Замкодержатель тип А", "Предохранитель тип А"],
            "Тип Б (новый)":  ["Корпус СА-3 тип Б", "Замок тип Б", "Замкодержатель тип Б", "Предохранитель тип Б"],
            "Тип В (усиленный)": ["Корпус СА-3 тип В", "Замок усил.", "Замкодержатель усил.", "Предохранитель усил."],
        }
    },
    "Поглощающий аппарат": {
        "types": ["Ш-1-ТМ", "Ш-2-В", "73ZW", "ПМК-110А"],
        "parts_by_type": {
            "Ш-1-ТМ":    ["Корпус Ш-1-ТМ", "Пружина внеш. Ш-1-ТМ", "Пружина внутр. Ш-1-ТМ", "Стяжной болт"],
            "Ш-2-В":     ["Корпус Ш-2-В", "Пружина Ш-2-В", "Фрикционные клинья", "Нажимной конус"],
            "73ZW":      ["Корпус 73ZW", "Эластомерный элемент", "Крышка 73ZW"],
            "ПМК-110А":  ["Корпус ПМК-110А", "Пружинный пакет", "Нажимная плита"],
        }
    },
}

AKP_DETAILS = {
    "Буксовый узел": {
        "types": ["Тип 1 (стандарт)", "Тип 2 (усиленный)"],
        "parts_by_type": {
            "Тип 1 (стандарт)": ["Подшипник 42726 Е2М", "Кольцо лабиринтное", "Крышка задняя", "Крышка передняя", "Болт М20", "Шайба пружинная"],
            "Тип 2 (усиленный)": ["Подшипник 42726 Е4М", "Кольцо лабиринтное усил.", "Крышка задняя усил.", "Крышка передняя усил.", "Болт М22", "Шайба"],
        }
    },
    "Роликовый подшипник": {
        "types": ["36-232726 Е2М", "36-232726 Е4М", "42726 Е2"],
        "parts_by_type": {
            "36-232726 Е2М": ["Внешнее кольцо", "Внутреннее кольцо", "Сепаратор", "Ролики"],
            "36-232726 Е4М": ["Внешнее кольцо усил.", "Внутреннее кольцо усил.", "Сепаратор мет.", "Ролики усил."],
            "42726 Е2":      ["Кольцо нар.", "Кольцо вн.", "Сепаратор пласт.", "Ролики цил."],
        }
    },
}

KP_TYPES = ["РУ1-950", "РУ1Ш-950", "РВ2Ш-957", "РВ3Ш-957"]
REPAIR_TYPES = ["ТР-1", "ТР-2", "СР", "КР", "КРП"]
ZAVODY = ["НКМЗ", "ВМЗ", "УКВЗ", "УЗТМ", "ФАНПАС", "СКТБ"]

# ─── Auth ─────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "")
    user = DB["users"].get(username)
    if user and user["password"] == password:
        session["user"] = username
        session["role"] = user["role"]
        session["name"] = user["name"]
        session["uchastok"] = user.get("uchastok", "")
        return jsonify({"ok": True, "role": user["role"]})
    return jsonify({"ok": False, "error": "Неверный логин или пароль"}), 401

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

def require_login(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

# ─── Dashboard ───────────────────────────────────────────────────────────────
@app.route("/dashboard")
@require_login
def dashboard():
    role = session["role"]
    return render_template("dashboard.html",
        user=session["name"], role=role,
        uchastok=session.get("uchastok", ""))

# ─── API: Reference data ──────────────────────────────────────────────────────
@app.route("/api/reference/details")
def ref_details():
    return jsonify({
        "numbered": DETAILS_NUMBERED,
        "unnumbered": DETAILS_UNNUMBERED,
        "detail_types": DETAIL_TYPES,
        "akp_details": AKP_DETAILS,
        "kp_types": KP_TYPES,
        "repair_types": REPAIR_TYPES,
        "zavody": ZAVODY,
    })

@app.route("/api/reference/akp_parts")
def akp_parts():
    detail = request.args.get("detail")
    det_type = request.args.get("type")
    if detail in AKP_DETAILS and det_type in AKP_DETAILS[detail]["parts_by_type"]:
        return jsonify({"parts": AKP_DETAILS[detail]["parts_by_type"][det_type]})
    return jsonify({"parts": []})

@app.route("/api/reference/detail_type_parts")
def detail_type_parts():
    detail = request.args.get("detail")
    det_type = request.args.get("type")
    if detail in DETAIL_TYPES and det_type in DETAIL_TYPES[detail]["parts_by_type"]:
        return jsonify({"parts": DETAIL_TYPES[detail]["parts_by_type"][det_type]})
    return jsonify({"parts": []})

# ─── API: Wagons (simulate backend incoming) ──────────────────────────────────
@app.route("/api/wagons", methods=["GET"])
@require_login
def get_wagons():
    return jsonify(list(DB["wagons"].values()))

@app.route("/api/wagons", methods=["POST"])
@require_login
def add_wagon():
    data = request.get_json()
    wagon_id = str(uuid.uuid4())[:8].upper()
    wagon = {
        "id": wagon_id,
        "number": data.get("number"),
        "incoming_number": data.get("incoming_number"),
        "date": data.get("date", str(date.today())),
        "status": "В ремонте",
        "created_at": datetime.now().isoformat(),
    }
    DB["wagons"][wagon_id] = wagon
    # Auto-create ОПЗС documents for Автосцепка and Тележечный
    for uchastok in ["avtotsepka", "tележечный"]:
        doc_id = str(uuid.uuid4())[:8].upper()
        DB["opzs_docs"][doc_id] = {
            "id": doc_id,
            "wagon_id": wagon_id,
            "wagon_number": wagon["number"],
            "incoming_number": wagon["incoming_number"],
            "date": wagon["date"],
            "uchastok": uchastok,
            "status": "Открыт",
            "defekt_numbered": [],
            "defekt_unnumbered": [],
            "defekt_types": [],
            "master_numbered": [],
            "master_unnumbered": [],
            "created_at": datetime.now().isoformat(),
        }
    return jsonify({"ok": True, "wagon": wagon})

# ─── API: ОПЗС Documents ─────────────────────────────────────────────────────
@app.route("/api/opzs", methods=["GET"])
@require_login
def get_opzs():
    uchastok = request.args.get("uchastok")
    docs = list(DB["opzs_docs"].values())
    if uchastok:
        docs = [d for d in docs if d["uchastok"] == uchastok]
    return jsonify(docs)

@app.route("/api/opzs", methods=["POST"])
@require_login
def create_opzs():
    # Manual creation (for AKP)
    data = request.get_json()
    doc_id = str(uuid.uuid4())[:8].upper()
    doc = {
        "id": doc_id,
        "wagon_id": data.get("wagon_id", ""),
        "wagon_number": data.get("wagon_number", ""),
        "incoming_number": data.get("incoming_number", ""),
        "date": data.get("date", str(date.today())),
        "uchastok": "akp",
        "status": "Открыт",
        "akp_rows": [],
        "created_at": datetime.now().isoformat(),
    }
    DB["opzs_docs"][doc_id] = doc
    return jsonify({"ok": True, "doc": doc})

@app.route("/api/opzs/<doc_id>", methods=["GET"])
@require_login
def get_opzs_doc(doc_id):
    doc = DB["opzs_docs"].get(doc_id)
    if not doc:
        return jsonify({"error": "Документ не найден"}), 404
    return jsonify(doc)

@app.route("/api/opzs/<doc_id>", methods=["PUT"])
@require_login
def update_opzs(doc_id):
    doc = DB["opzs_docs"].get(doc_id)
    if not doc:
        return jsonify({"error": "Не найден"}), 404
    data = request.get_json()
    doc.update(data)
    doc["updated_at"] = datetime.now().isoformat()
    doc["updated_by"] = session["name"]
    return jsonify({"ok": True, "doc": doc})

# ─── API: КП Приход ───────────────────────────────────────────────────────────
@app.route("/api/kp_arrival", methods=["GET"])
@require_login
def get_kp_arrival():
    return jsonify(list(DB["kp_arrival"].values()))

@app.route("/api/kp_arrival", methods=["POST"])
@require_login
def create_kp_arrival():
    data = request.get_json()
    doc_id = str(uuid.uuid4())[:8].upper()
    doc = {
        "id": doc_id,
        "date": data.get("date", str(date.today())),
        "shift": data.get("shift", "1"),
        "rows": data.get("rows", []),
        "created_by": session["name"],
        "created_at": datetime.now().isoformat(),
    }
    DB["kp_arrival"][doc_id] = doc
    return jsonify({"ok": True, "doc": doc})

@app.route("/api/kp_arrival/<doc_id>", methods=["GET"])
@require_login
def get_kp_arrival_doc(doc_id):
    doc = DB["kp_arrival"].get(doc_id)
    if not doc:
        return jsonify({"error": "Не найден"}), 404
    return jsonify(doc)

@app.route("/api/kp_arrival/<doc_id>", methods=["PUT"])
@require_login
def update_kp_arrival(doc_id):
    doc = DB["kp_arrival"].get(doc_id)
    if not doc:
        return jsonify({"error": "Не найден"}), 404
    data = request.get_json()
    doc.update(data)
    doc["updated_at"] = datetime.now().isoformat()
    return jsonify({"ok": True, "doc": doc})

# ─── API: КП Выход ────────────────────────────────────────────────────────────
@app.route("/api/kp_departure", methods=["GET"])
@require_login
def get_kp_departure():
    return jsonify(list(DB["kp_departure"].values()))

@app.route("/api/kp_departure", methods=["POST"])
@require_login
def create_kp_departure():
    data = request.get_json()
    doc_id = str(uuid.uuid4())[:8].upper()
    doc = {
        "id": doc_id,
        "date": data.get("date", str(date.today())),
        "shift": data.get("shift", "1"),
        "rows": data.get("rows", []),
        "created_by": session["name"],
        "created_at": datetime.now().isoformat(),
    }
    DB["kp_departure"][doc_id] = doc
    return jsonify({"ok": True, "doc": doc})

@app.route("/api/kp_departure/<doc_id>", methods=["GET", "PUT"])
@require_login
def kp_departure_doc(doc_id):
    doc = DB["kp_departure"].get(doc_id)
    if not doc:
        return jsonify({"error": "Не найден"}), 404
    if request.method == "PUT":
        data = request.get_json()
        doc.update(data)
        doc["updated_at"] = datetime.now().isoformat()
        return jsonify({"ok": True, "doc": doc})
    return jsonify(doc)

# ─── API: Роликовый участок ───────────────────────────────────────────────────
@app.route("/api/roller", methods=["GET"])
@require_login
def get_roller():
    return jsonify(list(DB["roller_docs"].values()))

@app.route("/api/roller", methods=["POST"])
@require_login
def create_roller():
    data = request.get_json()
    doc_id = str(uuid.uuid4())[:8].upper()
    doc = {
        "id": doc_id,
        "date": data.get("date", str(date.today())),
        "shift": data.get("shift", "1"),
        "rows": data.get("rows", []),
        "created_by": session["name"],
        "created_at": datetime.now().isoformat(),
    }
    DB["roller_docs"][doc_id] = doc
    return jsonify({"ok": True, "doc": doc})

@app.route("/api/roller/<doc_id>", methods=["GET", "PUT"])
@require_login
def roller_doc(doc_id):
    doc = DB["roller_docs"].get(doc_id)
    if not doc:
        return jsonify({"error": "Не найден"}), 404
    if request.method == "PUT":
        data = request.get_json()
        doc.update(data)
        doc["updated_at"] = datetime.now().isoformat()
        return jsonify({"ok": True, "doc": doc})
    return jsonify(doc)

# ─── API: Настурный колесный лист ─────────────────────────────────────────────
@app.route("/api/nakatka", methods=["GET"])
@require_login
def get_nakatka():
    return jsonify(list(DB["nakatka_docs"].values()))

@app.route("/api/nakatka", methods=["POST"])
@require_login
def create_nakatka():
    data = request.get_json()
    doc_id = str(uuid.uuid4())[:8].upper()
    doc = {
        "id": doc_id,
        "wagon_number": data.get("wagon_number", ""),
        "telega_number": data.get("telega_number", ""),
        "vagon_type": data.get("vagon_type", ""),
        "kontragent": data.get("kontragent", ""),
        "remont_type": data.get("remont_type", ""),
        "kp_rows": data.get("kp_rows", []),
        "created_by": session["name"],
        "created_at": datetime.now().isoformat(),
    }
    DB["nakatka_docs"][doc_id] = doc
    return jsonify({"ok": True, "doc": doc})

@app.route("/api/nakatka/<doc_id>", methods=["GET", "PUT"])
@require_login
def nakatka_doc(doc_id):
    doc = DB["nakatka_docs"].get(doc_id)
    if not doc:
        return jsonify({"error": "Не найден"}), 404
    if request.method == "PUT":
        data = request.get_json()
        doc.update(data)
        doc["updated_at"] = datetime.now().isoformat()
        return jsonify({"ok": True, "doc": doc})
    return jsonify(doc)

# ─── Pages ────────────────────────────────────────────────────────────────────
@app.route("/opzs")
@require_login
def opzs_page():
    return render_template("opzs.html", user=session["name"], role=session["role"],
                           uchastok=session.get("uchastok", ""))

@app.route("/kp")
@require_login
def kp_page():
    return render_template("kp.html", user=session["name"], role=session["role"],
                           uchastok=session.get("uchastok", ""))

@app.route("/nakatka")
@require_login
def nakatka_page():
    return render_template("nakatka.html", user=session["name"], role=session["role"])

@app.route("/wagons")
@require_login
def wagons_page():
    return render_template("wagons.html", user=session["name"], role=session["role"])

@app.template_filter('role_label')
def role_label_filter(role):
    return role_label(role)

@app.context_processor
def inject_helpers():
    def role_label(r):
        return {"nachalnik": "НАЧ.ЦЕХА", "master": "МАСТЕР", "defektoskopist": "ДЕФЕКТ.", "master_roller": "МАС.РОЛ."}.get(r, r.upper())
    return dict(role_label=role_label)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
