"""
Exporta best.pt → best.onnx para inferencia con ONNX Runtime.

Ejecutar UNA SOLA VEZ en local (donde hay RAM suficiente):
    python export_onnx.py

Luego subir best.onnx al repo / imagen Docker.
Con ONNX Runtime la inferencia en CPU es 2-4× más rápida que con PyTorch.
"""
from ultralytics import YOLO

model = YOLO("best.pt")
model.export(
    format="onnx",
    imgsz=320,        # tamaño fijo de inferencia
    simplify=True,    # simplifica el grafo → más rápido en CPU
    opset=17,
)
print("✓ Exportado a best.onnx")
print("  Recuerda agregar 'onnxruntime==1.20.1' a requirements.txt")
print("  y cambiar MODEL_PATH=best.onnx (o MODEL_PATH=/app/best.onnx)")
