import cv2
from deepface import DeepFace

# Cargar clasificador de rostro de OpenCV (solo se hace una vez)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def analyze_frame(frame):
    """
    Recibe un frame BGR de OpenCV.
    Devuelve una lista de diccionarios con:
        - box: (x, y, w, h)
        - emotion: string
        - gender: string
    """

    # Trabajar en escala de grises solo para la detección
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Detectar caras
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.3,
        minNeighbors=3,
    )

    results = []

    for (x, y, w, h) in faces:
        face = frame[y : y + h, x : x + w]

        try:
            analysis = DeepFace.analyze(
                face,
                actions=["emotion", "gender"],
                enforce_detection=False,
                detector_backend="opencv",
            )
        except Exception as e:
            print(f"[DeepFace] Error analizando rostro: {e}")
            continue

        if isinstance(analysis, list):
            analysis = analysis[0]

        emotion = analysis.get("dominant_emotion", "unknown")
        gender = analysis.get("dominant_gender", "unknown")

        results.append(
            {
                "box": (x, y, w, h),
                "emotion": emotion,
                "gender": gender,
            }
        )

    return results


def emotion_weight(emotion: str) -> float:
    """
    Devuelve un peso con signo según la emoción:

      - valor > 0  -> aumenta el estrés
      - valor < 0  -> reduce el estrés
      - valor ~ 0  -> casi no cambia

    Este valor se usará como incremento/decremento sobre un
    índice de estrés acumulado en main.py.
    """
    if not emotion:
        return 0.0

    e = emotion.lower()

    weights = {
        "angry": 2.0,
        "fear": 2.0,
        "disgust": 1.5,
        "sad": 1.0,
        "surprise": 0.2,  # casi neutra
        "neutral": -0.1,  # relaja un pelín
        "happy": -1.5,    # relaja bastante
    }

    return weights.get(e, 0.0)
