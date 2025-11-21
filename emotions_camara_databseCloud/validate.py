import os
import cv2
import numpy as np
from collections import Counter
import matplotlib.pyplot as plt

from emotion_detector import analyze_frame

# Emociones que maneja tu modelo / DeepFace
EMOTIONS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]

# Grupos de interés
GOOD = {"happy"}
NEUTRAL = {"neutral"}
NEGATIVE = {"angry", "disgust", "fear", "sad"}

# Ruta al conjunto de test
BASE_DIR = r"C:\Users\User\Documents\uni\4 año\jf\emotions_camara2\archive\test"


def get_true_label_from_path(path: str):
    parts = path.split(os.sep)
    for e in EMOTIONS:
        if e in parts:
            return e
    return None


def read_image_unicode(path: str):
    """Lee imagen incluso si la ruta tiene caracteres especiales."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        file_bytes = np.asarray(bytearray(data), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"Error leyendo imagen con imdecode: {path} -> {e}")
        return None


def plot_confusion_matrix(y_true, y_pred, labels):
    """
    Dibuja una matriz de confusión usando matplotlib.
    y_true: lista de etiquetas reales
    y_pred: lista de etiquetas predichas
    labels: lista de etiquetas en orden fijo (EMOTIONS)
    """
    n = len(labels)
    conf_matrix = np.zeros((n, n), dtype=int)

    # Rellenar la matriz
    for t, p in zip(y_true, y_pred):
        if t in labels and p in labels:
            i = labels.index(t)
            j = labels.index(p)
            conf_matrix[i, j] += 1

    fig, ax = plt.subplots()
    im = ax.imshow(conf_matrix)

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)

    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_title("Confusion matrix (FER test)")

    # Escribir los valores en cada celda
    for i in range(n):
        for j in range(n):
            value = conf_matrix[i, j]
            if value > 0:
                ax.text(
                    j,
                    i,
                    str(value),
                    ha="center",
                    va="center",
                )

    plt.tight_layout()
    plt.show()

def plot_grouped_confusion_matrix(y_true, y_pred):
    """
    Construye y muestra una matriz de confusión agrupada:
    - Positiva (happy)
    - Neutra (neutral)
    - Negativa (angry, disgust, fear, sad)

    surprise se ignora.
    """

    GROUPS = {
        "positive": {"happy"},
        "neutral": {"neutral"},
        "negative": {"angry", "disgust", "fear", "sad"},
    }

    # Función para mapear una emoción -> grupo
    def to_group(label):
        for group_name, group_set in GROUPS.items():
            if label in group_set:
                return group_name
        return None  # ignora surprise

    y_true_g = []
    y_pred_g = []

    for t, p in zip(y_true, y_pred):
        gt = to_group(t)
        gp = to_group(p)

        if gt is None:
            continue  # ignorar surprise en el real
        if gp is None:
            continue  # ignorar surprise en el predicho

        y_true_g.append(gt)
        y_pred_g.append(gp)

    groups = ["positive", "neutral", "negative"]
    n = len(groups)

    # Matriz numérica
    matrix = np.zeros((n, n), dtype=int)

    for t, p in zip(y_true_g, y_pred_g):
        i = groups.index(t)
        j = groups.index(p)
        matrix[i, j] += 1

    # Dibujar
    fig, ax = plt.subplots()
    im = ax.imshow(matrix, cmap="Blues")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(groups, rotation=45, ha="right")
    ax.set_yticklabels(groups)

    ax.set_xlabel("Predicted group")
    ax.set_ylabel("True group")
    ax.set_title("Confusion matrix (Grouped emotions)")

    # Mostrar números sobre las celdas
    for i in range(n):
        for j in range(n):
            ax.text(j, i, matrix[i, j], ha="center", va="center")

    plt.tight_layout()
    plt.show()


def main():
    y_true = []
    y_pred = []

    # Contadores por tipo de emoción (con la lógica que pides)
    stats = {
        "good_total": 0,
        "good_correct": 0,
        "neutral_total": 0,
        "neutral_correct": 0,
        "negative_total": 0,
        "negative_correct": 0,  # aquí cuenta predicción en cualquier negativa
    }

    print("Usando base_dir:", BASE_DIR)
    print("¿Existe la carpeta?", os.path.isdir(BASE_DIR))

    total_files = 0
    for root, _, files in os.walk(BASE_DIR):
        total_files += len(files)
    if total_files == 0:
        print("No se encontraron imágenes. Revisa la ruta BASE_DIR.")
        return

    for root, _, files in os.walk(BASE_DIR):
        for fname in files:
            if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            path = os.path.join(root, fname)
            true_label = get_true_label_from_path(path)
            if true_label is None:
                continue

            img = read_image_unicode(path)
            if img is None:
                continue

            results = analyze_frame(img)
            if not results:
                continue

            pred_label = results[0]["emotion"]

            y_true.append(true_label)
            y_pred.append(pred_label)

            # Estadísticas por categoría con la nueva lógica

            # Happy: solo cuenta si pred_label == "happy"
            if true_label in GOOD:
                stats["good_total"] += 1
                if pred_label in GOOD:
                    stats["good_correct"] += 1

            # Neutral: solo cuenta si pred_label == "neutral"
            elif true_label in NEUTRAL:
                stats["neutral_total"] += 1
                if pred_label in NEUTRAL:
                    stats["neutral_correct"] += 1

            # Negativas: cuenta como bien si pred_label es CUALQUIER negativa
            elif true_label in NEGATIVE:
                stats["negative_total"] += 1
                if pred_label in NEGATIVE:
                    stats["negative_correct"] += 1

            # surprise lo ignoramos para estas estadísticas

    # Métricas generales (exact match)
    total = len(y_true)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = correct / total if total > 0 else 0.0

    print("\n----- RESULTADOS GENERALES (label exacto) -----")
    print(f"Total imágenes analizadas: {total}")
    print(f"Aciertos (exactos): {correct}")
    print(f"Accuracy global (exacto): {accuracy:.3f}")

    # Estadísticas por tipo de emoción con tu criterio
    print("\n----- ESTADÍSTICAS POR TIPO DE EMOCIÓN (agrupadas) -----\n")

    if stats["good_total"] > 0:
        good_acc = stats["good_correct"] / stats["good_total"]
        print(f"Happy -> {stats['good_correct']}/{stats['good_total']}  Accuracy (happy correcto): {good_acc:.3f}")
    else:
        print("Happy -> no había imágenes en el dataset.")

    if stats["neutral_total"] > 0:
        neutral_acc = stats["neutral_correct"] / stats["neutral_total"]
        print(f"Neutral -> {stats['neutral_correct']}/{stats['neutral_total']}  Accuracy (neutral correcto): {neutral_acc:.3f}")
    else:
        print("Neutral -> no había imágenes en el dataset.")

    if stats["negative_total"] > 0:
        neg_acc = stats["negative_correct"] / stats["negative_total"]
        print(
            f"Negativas (angry/disgust/fear/sad) -> "
            f"{stats['negative_correct']}/{stats['negative_total']}  "
            f"Accuracy (cualquier negativa): {neg_acc:.3f}"
        )
    else:
        print("Negativas -> no había imágenes en el dataset.")

    # Matriz de confusión en texto
    print("\n----- MATRIZ DE CONFUSIÓN (true, pred) -> count -----")
    confusion = Counter((t, p) for t, p in zip(y_true, y_pred))
    for t in EMOTIONS:
        for p in EMOTIONS:
            c = confusion[(t, p)]
            if c > 0:
                print(f"{t:10s}  {p:10s}  {c}")

    # Matriz de confusión visual
    plot_confusion_matrix(y_true, y_pred, EMOTIONS)

    plot_grouped_confusion_matrix(y_true, y_pred)



if __name__ == "__main__":
    main()
