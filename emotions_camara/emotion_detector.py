import cv2
from deepface import DeepFace

# Cargar clasificador de rostro de OpenCV (solo se hace una vez)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

def analyze_frame(frame):
    """
    Recibe un frame BGR de OpenCV.
    Devuelve una lista de diccionarios con:
        - box: (x, y, w, h)
        - emotion: string
        - gender: string
    """

    # Opcional: trabajar en escala de grises solo para la detección
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Detectar caras
    faces = face_cascade.detectMultiScale(
        gray, 
        scaleFactor=1.3, 
        minNeighbors=3
    )

    results = []

    for (x, y, w, h) in faces:
        face = frame[y:y+h, x:x+w]

        analysis = DeepFace.analyze(
            face,
            actions=['emotion', 'gender'],
            enforce_detection=False,
            detector_backend='opencv'  # si lo estabas usando
        )

        if isinstance(analysis, list):
            analysis = analysis[0]

        emotion = analysis.get('dominant_emotion', 'unknown')
        gender = analysis.get('dominant_gender', 'unknown')

        # NUEVO: calcular estrés
        stress_score, stress_level = stress_from_emotion(emotion)

        results.append({
            "box": (x, y, w, h),
            "emotion": emotion,
            "gender": gender,
            "stress_score": stress_score,
            "stress_level": stress_level,
        })

    return results

def stress_from_emotion(emotion: str):
    """
    Devuelve (score, level) a partir de la emoción dominante.
    score: número >= 0
    level: 'bajo', 'medio', 'alto'
    """
    if not emotion:
        return 0.0, "bajo"

    e = emotion.lower()

    weights = {
        "angry": 2.0,
        "fear": 2.0,
        "disgust": 1.5,
        "sad": 1.0,
        "surprise": 0.5,
        "neutral": 0.0,
        "happy": -1.0,
    }

    score = weights.get(e, 0.0)

    # No queremos estrés negativo
    if score < 0:
        score = 0.0

    if score == 0:
        level = "bajo"
    elif score < 2:
        level = "medio"
    else:
        level = "alto"

    return score, level
