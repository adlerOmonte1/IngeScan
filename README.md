# IngeScan

**IngeScan** es una aplicación web que utiliza visión por computadora e inteligencia artificial para **identificar componentes electrónicos** a partir de una imagen, y enriquece los resultados con información técnica obtenida desde la API de Nexar (Octopart).

Construida con **Flask + YOLOv8 (Ultralytics)**, con autenticación de usuarios, historial de búsquedas y una interfaz responsiva con estética profesional.

---

## Tabla de contenidos

- [Características](#características)
- [Arquitectura](#arquitectura)
- [Stack tecnológico](#stack-tecnológico)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Requisitos previos](#requisitos-previos)
- [Instalación local](#instalación-local)
- [Variables de entorno](#variables-de-entorno)
- [Uso](#uso)
- [Modelo de IA](#modelo-de-ia)
- [Despliegue](#despliegue)
- [Roadmap](#roadmap)
- [Licencia](#licencia)

---

## Características

- 🤖 **Detección con IA** — Modelo YOLOv8 entrenado para reconocer componentes electrónicos.
- 🔎 **Información técnica enriquecida** — Consulta MPN, fabricante, descripción y categoría vía Nexar (Octopart).
- 👤 **Autenticación de usuarios** — Registro y login con contraseñas hasheadas (Werkzeug).
- 📚 **Historial personal** — Cada usuario conserva el registro de sus detecciones.
- 🎨 **UI profesional y responsiva** — Diseño limpio inspirado en LinkedIn, totalmente adaptable a móvil/tablet/escritorio.
- 🚀 **Listo para producción** — Dockerfile, Gunicorn, healthcheck y configuración para Render/Railway/Fly.io.
- 🔐 **Seguridad por defecto** — Validación de archivos, límite de tamaño, cookies HttpOnly, secretos por variables de entorno.

---

## Arquitectura

```
┌─────────────┐   imagen   ┌──────────────┐   nombre   ┌──────────────┐
│  Navegador  │ ─────────▶ │  Flask (web) │ ─────────▶ │ YOLOv8 (.pt) │
└─────────────┘            └──────┬───────┘            └──────┬───────┘
       ▲                          │                           │
       │                          │ MPN, fabricante,          │ clase + confianza
       │                          ▼ descripción               │
       │                   ┌──────────────┐                   │
       └──── HTML/UI ───── │  Nexar API   │ ◀─────────────────┘
                           └──────────────┘
                                  ▲
                                  │  historial / usuarios
                                  ▼
                           ┌──────────────┐
                           │  SQLite DB   │
                           └──────────────┘
```

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11, Flask 2.3 |
| IA / Visión | Ultralytics YOLOv8, PyTorch, OpenCV |
| Datos | SQLite |
| API externa | Nexar GraphQL (Octopart) |
| Frontend | HTML5, CSS3, JavaScript vanilla |
| Servidor WSGI | Gunicorn |
| Contenedor | Docker |

---

## Estructura del proyecto

```
ReconocimientoPC/
├── app.py                  # Aplicación Flask (factory create_app)
├── best.pt                 # Modelo YOLOv8 entrenado (51 MB)
├── requirements.txt        # Dependencias Python
├── runtime.txt             # Versión de Python para PaaS
├── Procfile                # Comando de arranque para Heroku/Render
├── Dockerfile              # Imagen para despliegue containerizado
├── .dockerignore
├── .gitignore
├── .env.example            # Plantilla de variables de entorno
├── render.yaml             # Blueprint de Render.com
├── README.md
├── DEPLOY.md               # Guía de despliegue en la nube
├── static/
│   ├── styles.css          # Sistema de diseño
│   ├── img/                # Imágenes estáticas
│   └── uploads/            # Imágenes cargadas (generadas en runtime)
└── templates/
    ├── base.html           # Layout base (navbar + toasts)
    ├── login.html
    ├── register.html
    ├── index.html          # Página de detección
    └── historial.html
```

---

## Requisitos previos

- **Python 3.11+**
- **pip** y **virtualenv**
- Cuenta y credenciales en [Nexar](https://nexar.com/api) (para consultas a Octopart)
- (Opcional) **Docker** para despliegue en contenedor

---

## Instalación local

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd ReconocimientoPC

# 2. Crear y activar entorno virtual
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
# Edita .env con tus credenciales de Nexar y una SECRET_KEY

# 5. Ejecutar la aplicación en desarrollo
export FLASK_DEBUG=1
python app.py
```

La app se sirve en `http://localhost:5000`.

---

## Variables de entorno

Definidas en `.env` (ver `.env.example` para la plantilla completa):

| Variable | Descripción | Default |
|---|---|---|
| `SECRET_KEY` | Clave de Flask para firmar cookies de sesión | `dev-key-...` |
| `FLASK_ENV` | `development` o `production` | — |
| `FLASK_DEBUG` | `1` para modo debug | `0` |
| `PORT` | Puerto HTTP | `5000` |
| `NEXAR_CLIENT_ID` | ID de cliente de Nexar | — |
| `NEXAR_CLIENT_SECRET` | Secret de Nexar | — |
| `CONFIDENCE_THRESHOLD` | Umbral mínimo de confianza (0–1) | `0.80` |
| `MODEL_PATH` | Ruta al archivo `.pt` | `best.pt` |
| `DATABASE_PATH` | Ruta al SQLite | `usuarios.db` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |

> 💡 Genera una `SECRET_KEY` segura con:
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## Uso

1. **Registra** una cuenta con tu código de estudiante.
2. **Inicia sesión**.
3. En la página principal, **arrastra una imagen** o haz clic para seleccionarla.
4. Haz clic en **"Analizar componente"**.
5. La IA detectará el componente; si la confianza supera el umbral, se mostrará junto con su información técnica desde Nexar.
6. Revisa todas tus búsquedas pasadas en **Historial**.

### Endpoints principales

| Ruta | Método | Descripción |
|---|---|---|
| `/` | GET / POST | Página principal y procesamiento de imagen |
| `/login` | GET / POST | Inicio de sesión |
| `/register` | GET / POST | Registro de usuario |
| `/logout` | GET | Cierre de sesión |
| `/historial` | GET | Historial del usuario autenticado |
| `/health` | GET | Healthcheck (para orquestadores) |

---

## Modelo de IA

El archivo `best.pt` es un modelo **YOLOv8** entrenado para detectar componentes electrónicos (Arduino, sensores, resistencias, etc.).

- Formato: PyTorch / Ultralytics
- Tamaño: ~51 MB
- Se carga **una sola vez** en memoria (lazy loading) en el primer request.
- Umbral de confianza configurable vía `CONFIDENCE_THRESHOLD`.

> ⚠️ El modelo es relativamente grande. Para optimizar el cold start en plataformas con disco limitado, considera servirlo desde S3/GCS y descargarlo en el arranque (ver [DEPLOY.md](DEPLOY.md)).

---

## Despliegue

Esta aplicación está lista para desplegarse en:

- **Render.com** (recomendado, con `render.yaml`)
- **Railway**
- **Fly.io**
- **Google Cloud Run**
- **AWS App Runner / ECS**
- **Heroku** (con buildpacks)

👉 Consulta la guía completa en **[DEPLOY.md](DEPLOY.md)**.

### Quick start con Docker

```bash
docker build -t ingescan .
docker run -p 8000:8000 \
  -e SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  -e NEXAR_CLIENT_ID=tu-id \
  -e NEXAR_CLIENT_SECRET=tu-secret \
  ingescan
```

Abre [http://localhost:8000](http://localhost:8000).

---

## Roadmap

- [ ] Soporte multi-detección (mostrar todos los componentes encontrados).
- [ ] Exportar historial a CSV/PDF.
- [ ] Roles (admin / docente / estudiante).
- [ ] Migrar de SQLite a PostgreSQL en producción.
- [ ] Tests automatizados (pytest).
- [ ] Pipeline CI/CD (GitHub Actions).

---

## Licencia

Proyecto académico desarrollado por el equipo IngeScan. Uso educativo y de investigación.
