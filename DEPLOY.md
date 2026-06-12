# Guía de despliegue — IngeScan

Esta guía describe cómo desplegar IngeScan en producción. La app está empaquetada en **Docker** y usa **Gunicorn** como servidor WSGI.

---

## Tabla de contenidos

1. [Pre-vuelo: lista de verificación](#1-pre-vuelo-lista-de-verificación)
2. [Variables de entorno requeridas](#2-variables-de-entorno-requeridas)
3. [Render.com (recomendado)](#3-rendercom-recomendado)
4. [Railway](#4-railway)
5. [Fly.io](#5-flyio)
6. [Google Cloud Run](#6-google-cloud-run)
7. [AWS App Runner](#7-aws-app-runner)
8. [Heroku](#8-heroku)
9. [Docker en VPS (DigitalOcean / Linode / EC2)](#9-docker-en-vps-digitalocean--linode--ec2)
10. [Consideraciones de producción](#10-consideraciones-de-producción)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Pre-vuelo: lista de verificación

Antes de desplegar:

- [ ] `best.pt` está presente en la raíz del proyecto (o disponible en almacenamiento externo).
- [ ] Tienes credenciales válidas de **Nexar** (`CLIENT_ID` y `CLIENT_SECRET`).
- [ ] Generaste una `SECRET_KEY` segura:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] `requirements.txt` está actualizado.
- [ ] Probaste la imagen Docker localmente:
  ```bash
  docker build -t ingescan .
  docker run -p 8000:8000 --env-file .env ingescan
  ```
- [ ] El endpoint `GET /health` retorna `{"status":"ok"}`.

---

## 2. Variables de entorno requeridas

| Variable | Obligatorio | Valor recomendado |
|---|---|---|
| `SECRET_KEY` | ✅ | Cadena aleatoria de 64 caracteres |
| `FLASK_ENV` | ✅ | `production` |
| `NEXAR_CLIENT_ID` | ✅ | Tu ID de Nexar |
| `NEXAR_CLIENT_SECRET` | ✅ | Tu secret de Nexar |
| `PORT` | Automático | Inyectado por la plataforma |
| `CONFIDENCE_THRESHOLD` | Opcional | `0.80` |
| `LOG_LEVEL` | Opcional | `INFO` |
| `DATABASE_PATH` | Opcional | `/data/usuarios.db` (con disco persistente) |

---

## 3. Render.com (recomendado)

### Opción A — Blueprint (1 clic)

El proyecto incluye `render.yaml`. Sólo necesitas:

1. Haz push del código a GitHub/GitLab.
2. En Render → **New +** → **Blueprint**.
3. Conecta el repositorio. Render detecta `render.yaml` automáticamente.
4. Completa las variables `NEXAR_CLIENT_ID` y `NEXAR_CLIENT_SECRET` cuando lo pida.
5. **Deploy**.

### Opción B — Manual

1. New + → **Web Service** → conecta tu repo.
2. **Environment**: `Docker`.
3. **Plan**: mínimo `Standard` (2 GB RAM) — el modelo YOLO requiere memoria.
4. **Health check path**: `/health`.
5. Añade las variables de entorno de la sección 2.
6. (Opcional) Añade un **Disk** montado en `/app/data` para persistir `usuarios.db`.
7. **Create Web Service**.

URL final: `https://ingescan.onrender.com`.

---

## 4. Railway

1. `railway init` (o crea un proyecto desde la web).
2. Conecta el repositorio. Railway detecta el `Dockerfile`.
3. En **Variables**, añade las de la sección 2.
4. En **Settings → Networking** activa el dominio público.
5. (Recomendado) Añade un **Volume** montado en `/app/data` para SQLite.

Railway inyecta `$PORT` automáticamente — el `Dockerfile` ya lo respeta.

---

## 5. Fly.io

```bash
# 1. Instala flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login

# 2. Lanza la app (usa el Dockerfile)
fly launch --no-deploy
# Edita el fly.toml generado si quieres más RAM (recomendado: 2 GB+)

# 3. Configura secretos
fly secrets set \
  SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  NEXAR_CLIENT_ID=tu-id \
  NEXAR_CLIENT_SECRET=tu-secret \
  FLASK_ENV=production

# 4. (Opcional) Crea un volumen para persistencia
fly volumes create ingescan_data --size 1

# 5. Despliega
fly deploy
```

En `fly.toml`, asegura:
```toml
[http_service]
  internal_port = 8000
  force_https = true
  [http_service.checks]
    path = "/health"

[[vm]]
  memory = "2gb"
  cpu_kind = "shared"
  cpus = 1
```

---

## 6. Google Cloud Run

```bash
# 1. Configura el proyecto
gcloud config set project TU_PROJECT_ID

# 2. Construye y sube la imagen
gcloud builds submit --tag gcr.io/TU_PROJECT_ID/ingescan

# 3. Despliega
gcloud run deploy ingescan \
  --image gcr.io/TU_PROJECT_ID/ingescan \
  --platform managed \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --set-env-vars FLASK_ENV=production,CONFIDENCE_THRESHOLD=0.80 \
  --set-secrets SECRET_KEY=ingescan-secret-key:latest,NEXAR_CLIENT_ID=nexar-id:latest,NEXAR_CLIENT_SECRET=nexar-secret:latest
```

> ⚠️ Cloud Run usa **filesystem efímero**: SQLite no persistirá entre reinicios. Migra a Cloud SQL (Postgres) o usa Firestore.

---

## 7. AWS App Runner

1. Push del Dockerfile a **ECR**:
   ```bash
   aws ecr create-repository --repository-name ingescan
   docker build -t ingescan .
   docker tag ingescan:latest <account>.dkr.ecr.<region>.amazonaws.com/ingescan:latest
   aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
   docker push <account>.dkr.ecr.<region>.amazonaws.com/ingescan:latest
   ```
2. **App Runner** → Create service → Source: ECR → la imagen anterior.
3. Port: `8000`. Health check: `/health`.
4. Configurar variables de entorno (sección 2).
5. Memoria recomendada: **2 GB**.

---

## 8. Heroku

```bash
# Requiere CLI: https://devcenter.heroku.com/articles/heroku-cli
heroku login
heroku create ingescan-app

# El proyecto incluye Procfile y runtime.txt — funcionan tal cual.
heroku config:set \
  SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  NEXAR_CLIENT_ID=tu-id \
  NEXAR_CLIENT_SECRET=tu-secret \
  FLASK_ENV=production

# Despliegue por git
git push heroku main
```

> ⚠️ El slug de Heroku tiene **500 MB de límite**. PyTorch + el modelo `.pt` pueden quedar muy ajustados. Recomendado: usar `container:push` con el Dockerfile.

```bash
heroku stack:set container
heroku container:push web
heroku container:release web
```

---

## 9. Docker en VPS (DigitalOcean / Linode / EC2)

```bash
# En el VPS
git clone <repo>
cd ReconocimientoPC

# Crear .env con las variables de la sección 2
cp .env.example .env
nano .env

# Construir y correr
docker build -t ingescan .
docker run -d \
  --name ingescan \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v /var/data/ingescan:/app/data \
  ingescan
```

Luego coloca **Nginx** o **Caddy** delante con TLS:

```nginx
server {
  server_name ingescan.tudominio.com;
  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    client_max_body_size 10M;
  }
}
```

```bash
certbot --nginx -d ingescan.tudominio.com
```

---

## 10. Consideraciones de producción

### 💾 Persistencia de datos

SQLite es perfecto para empezar, pero **no persiste** en plataformas con filesystem efímero (Cloud Run, Heroku, App Runner). Opciones:

- **Disco persistente** (Render, Fly, Railway, EC2).
- **Migrar a PostgreSQL** y usar SQLAlchemy.
- Mover `DATABASE_PATH` a `/data/usuarios.db` cuando montes un volumen.

### 🤖 Modelo `best.pt` (51 MB)

- **Versionarlo en Git** funciona, pero infla el repo. Considera **Git LFS**.
- Alternativa: subirlo a **S3/GCS/Azure Blob** y descargarlo en el arranque:
  ```python
  # Añadir en app.py antes de get_model()
  if not Path(MODEL_PATH).exists():
      import urllib.request
      urllib.request.urlretrieve(os.environ["MODEL_URL"], MODEL_PATH)
  ```

### 🧠 Memoria

YOLO + PyTorch necesitan ~1.2–1.8 GB en runtime. **Plan mínimo recomendado: 2 GB RAM**. Por debajo, el proceso será OOM-killed en la primera inferencia.

### 🚀 Cold start

La primera petición de detección puede tardar **5–15 segundos** mientras carga el modelo. Para minimizarlo:

- Mantén el servicio "warm" (Render: `min instances = 1`).
- O carga el modelo eagerly en `create_app()` en vez de lazy.

### 🔒 Seguridad

- ✅ `SECRET_KEY` desde variable de entorno (nunca hardcoded).
- ✅ Contraseñas hasheadas con Werkzeug (`generate_password_hash`).
- ✅ Validación de extensiones de archivo.
- ✅ Límite de 8 MB por subida.
- ✅ Cookies `HttpOnly` y `Secure` en producción.
- 🔜 Añadir **rate limiting** (Flask-Limiter) en `/login` y `/register`.
- 🔜 Añadir **CSRF protection** (Flask-WTF) en formularios.

### 📊 Observabilidad

Logs estructurados a `stdout` (formato configurado en `app.py`). En la nube:

- Render / Railway / Fly: integrados.
- GCP: Cloud Logging.
- AWS: CloudWatch.

Para errores: integra **Sentry**:
```bash
pip install sentry-sdk[flask]
```
```python
import sentry_sdk
sentry_sdk.init(dsn=os.environ["SENTRY_DSN"])
```

---

## 11. Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| **OOM en primera inferencia** | RAM insuficiente | Subir el plan a ≥ 2 GB. |
| **Cold start lento (>30 s)** | Modelo se carga al primer request | Carga eagerly o usa min instances ≥ 1. |
| **`ModuleNotFoundError: cv2`** | Falta libGL en la imagen | Usa el Dockerfile (incluye `libgl1`). |
| **`Error: best.pt not found`** | Modelo no copiado en la imagen | Verifica que **no** esté en `.dockerignore`. |
| **Nexar 401** | Credenciales incorrectas | Revisa `NEXAR_CLIENT_ID` / `NEXAR_CLIENT_SECRET`. |
| **Sesión se pierde al recargar** | `SECRET_KEY` cambia entre reinicios | Define una `SECRET_KEY` fija en variables de entorno. |
| **413 Request Entity Too Large** | Imagen > 8 MB | Ajusta `MAX_CONTENT_LENGTH` en `app.py` y `client_max_body_size` en Nginx. |
| **SQLite "database is locked"** | Múltiples workers escribiendo | Mantén `--workers 1` o migra a PostgreSQL. |

---

## Resumen de archivos de despliegue

| Archivo | Para qué sirve |
|---|---|
| `Dockerfile` | Imagen del contenedor (todas las plataformas con Docker). |
| `.dockerignore` | Excluye archivos del build context. |
| `Procfile` | Comando de arranque para Heroku/Render sin Docker. |
| `runtime.txt` | Versión de Python para buildpacks. |
| `render.yaml` | Blueprint declarativo de Render. |
| `.env.example` | Plantilla de variables de entorno. |
| `requirements.txt` | Dependencias Python (con `gunicorn`). |

---

Si encuentras un problema no listado aquí, abre un issue en el repositorio con los logs y la plataforma usada.
