"""IngeScan - Aplicación Flask para reconocimiento de componentes electrónicos.

Carga un modelo YOLOv8 (best.pt) para detectar componentes en imágenes y enriquece
los resultados consultando la API de Nexar (Octopart) para obtener metadatos del
fabricante, MPN, descripción y categoría.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import requests
from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from ultralytics import YOLO
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _writable_dir(*candidates: Path) -> Path:
    """Devuelve el primer directorio creable/escribible de la lista."""
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_test"
            probe.touch()
            probe.unlink()
            return cand
        except OSError:
            continue
    # Último recurso: /tmp siempre debería existir
    fallback = Path("/tmp/ingescan")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# Ultralytics necesita un directorio de configuración escribible.
# En contenedores con FS de solo-lectura (/root no escribible), apuntamos a /tmp.
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)

# Directorio de uploads: dentro de static si se puede, si no en /tmp.
UPLOAD_DIR = _writable_dir(STATIC_DIR / "uploads", Path("/tmp/ingescan/uploads"))

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB

# Base de datos: respetar DATABASE_PATH si está definida, si no intentar BASE_DIR,
# y como fallback /tmp para entornos con FS de solo lectura.
_default_db_dir = _writable_dir(BASE_DIR, Path("/tmp/ingescan"))
DB_PATH = os.environ.get("DATABASE_PATH", str(_default_db_dir / "usuarios.db"))
# Asegurar que la carpeta destino del DB exista
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

MODEL_PATH = os.environ.get("MODEL_PATH", str(BASE_DIR / "best.pt"))
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.80"))

NEXAR_CLIENT_ID = os.environ.get("NEXAR_CLIENT_ID", "")
NEXAR_CLIENT_SECRET = os.environ.get("NEXAR_CLIENT_SECRET", "")
NEXAR_TOKEN_URL = "https://identity.nexar.com/connect/token"
NEXAR_GRAPHQL_URL = "https://api.nexar.com/graphql"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingescan")


# ---------------------------------------------------------------------------
# Capa de base de datos
# ---------------------------------------------------------------------------
@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                codigo TEXT NOT NULL UNIQUE,
                carrera TEXT NOT NULL,
                password TEXT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS historial (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL,
                componente TEXT NOT NULL,
                mpn TEXT,
                fabricante TEXT,
                descripcion TEXT,
                categoria TEXT,
                confianza REAL,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


# ---------------------------------------------------------------------------
# Cliente Nexar (Octopart)
# ---------------------------------------------------------------------------
def get_nexar_token() -> str | None:
    if not NEXAR_CLIENT_ID or not NEXAR_CLIENT_SECRET:
        logger.warning("Credenciales de Nexar no configuradas.")
        return None
    try:
        response = requests.post(
            NEXAR_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": NEXAR_CLIENT_ID,
                "client_secret": NEXAR_CLIENT_SECRET,
                "scope": "supply.domain",
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.RequestException as exc:
        logger.error("No se pudo obtener token de Nexar: %s", exc)
        return None


NEXAR_QUERY = """
query BuscarComponente($busqueda: String!) {
  supSearch(q: $busqueda, limit: 3) {
    results {
      part {
        mpn
        manufacturer { name }
        shortDescription
        category { name }
      }
    }
  }
}
"""


def search_component(name: str, token: str) -> list[dict]:
    try:
        response = requests.post(
            NEXAR_GRAPHQL_URL,
            json={"query": NEXAR_QUERY, "variables": {"busqueda": name}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("supSearch", {}).get("results", []) or []
    except requests.RequestException as exc:
        logger.error("Error consultando Nexar: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Modelo YOLO (carga única, perezosa)
# ---------------------------------------------------------------------------
_model: YOLO | None = None


def get_model() -> YOLO:
    global _model
    if _model is None:
        logger.info("Cargando modelo YOLO desde %s", MODEL_PATH)
        _model = YOLO(MODEL_PATH)
    return _model


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Aplicación Flask
# ---------------------------------------------------------------------------
def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-key-cambiar-en-produccion")
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("FLASK_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True

    init_db()

    # -----------------------------------------------------------------------
    # Autenticación
    # -----------------------------------------------------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "usuario" in session:
            return redirect(url_for("index"))

        if request.method == "POST":
            codigo = request.form.get("codigo", "").strip()
            password = request.form.get("password", "")
            with get_connection() as conn:
                user = conn.execute(
                    "SELECT * FROM usuarios WHERE codigo = ?", (codigo,)
                ).fetchone()
            if user and check_password_hash(user["password"], password):
                session.clear()
                session["usuario"] = user["nombre"]
                session["codigo"] = user["codigo"]
                session["carrera"] = user["carrera"]
                return redirect(url_for("index"))
            flash("Código o contraseña incorrectos.", "error")
            return redirect(url_for("login"))
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            nombre = request.form.get("nombre", "").strip()
            codigo = request.form.get("codigo", "").strip()
            carrera = request.form.get("carrera", "").strip()
            password = request.form.get("password", "")

            if not all([nombre, codigo, carrera, password]):
                flash("Todos los campos son obligatorios.", "error")
                return redirect(url_for("register"))
            if len(password) < 6:
                flash("La contraseña debe tener al menos 6 caracteres.", "error")
                return redirect(url_for("register"))

            with get_connection() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM usuarios WHERE codigo = ?", (codigo,)
                ).fetchone()
                if exists:
                    flash("El código de estudiante ya está registrado.", "error")
                    return redirect(url_for("register"))
                conn.execute(
                    "INSERT INTO usuarios (nombre, codigo, carrera, password) VALUES (?, ?, ?, ?)",
                    (nombre, codigo, carrera, generate_password_hash(password)),
                )
            flash("Registro exitoso. Inicia sesión.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Has cerrado sesión correctamente.", "success")
        return redirect(url_for("login"))

    # -----------------------------------------------------------------------
    # Historial
    # -----------------------------------------------------------------------
    @app.route("/historial")
    @login_required
    def historial():
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT componente, mpn, fabricante, descripcion, categoria, confianza, fecha
                FROM historial WHERE codigo = ? ORDER BY fecha DESC
                """,
                (session["codigo"],),
            ).fetchall()
        return render_template("historial.html", historial=rows)

    # -----------------------------------------------------------------------
    # Detección
    # -----------------------------------------------------------------------
    @app.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        if request.method != "POST":
            return render_template("index.html", componente=None, resultados=[])

        file = request.files.get("imagen")
        if not file or file.filename == "":
            flash("Debes seleccionar una imagen.", "error")
            return redirect(url_for("index"))
        if not allowed_file(file.filename):
            flash("Formato no permitido. Usa JPG, PNG o WEBP.", "error")
            return redirect(url_for("index"))

        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        original_path = UPLOAD_DIR / filename
        file.save(original_path)

        try:
            model = get_model()
            detection = model(str(original_path))[0]
            result_filename = f"result_{filename}"
            result_path = UPLOAD_DIR / result_filename
            detection.save(filename=str(result_path))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Error procesando imagen: %s", exc)
            flash("Ocurrió un error procesando la imagen. Intenta de nuevo.", "error")
            return redirect(url_for("index"))

        valid_boxes = [
            box for box in (detection.boxes or [])
            if float(box.conf[0]) >= CONFIDENCE_THRESHOLD
        ]
        if not valid_boxes:
            flash(
                "No se detectó un componente electrónico con la confianza mínima requerida.",
                "error",
            )
            return redirect(url_for("index"))

        best_box = max(valid_boxes, key=lambda b: float(b.conf[0]))
        class_id = int(best_box.cls[0])
        confidence = float(best_box.conf[0])
        componente = model.names[class_id]

        resultados: list[dict] = []
        token = get_nexar_token()
        if token:
            for result in search_component(componente, token):
                part = result.get("part") or {}
                if not part:
                    continue
                entry = {
                    "mpn": part.get("mpn", "Desconocido"),
                    "manufacturer": (part.get("manufacturer") or {}).get("name", "Desconocido"),
                    "descripcion": part.get("shortDescription", "Sin descripción"),
                    "categoria": (part.get("category") or {}).get("name", "Sin categoría"),
                }
                resultados.append(entry)
                with get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO historial
                        (codigo, componente, mpn, fabricante, descripcion, categoria, confianza)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session.get("codigo", "Desconocido"),
                            componente,
                            entry["mpn"],
                            entry["manufacturer"],
                            entry["descripcion"],
                            entry["categoria"],
                            confidence,
                        ),
                    )

        return render_template(
            "index.html",
            componente=componente,
            confianza=round(confidence * 100, 1),
            resultados=resultados,
            imagen_original=url_for("static", filename=f"uploads/{filename}"),
            imagen_procesada=url_for("static", filename=f"uploads/{result_filename}"),
        )

    # -----------------------------------------------------------------------
    # Health check para orquestadores (Render, Railway, Fly.io, Kubernetes)
    # -----------------------------------------------------------------------
    @app.route("/health")
    def health():
        return jsonify(status="ok"), 200

    @app.errorhandler(413)
    def too_large(_):
        flash("La imagen excede el tamaño máximo permitido (8 MB).", "error")
        return redirect(url_for("index"))

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
