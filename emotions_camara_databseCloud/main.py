import cv2
from datetime import datetime

from emotion_detector import analyze_frame, emotion_weight
from cloud_db import insert_emotion

# Emociones claramente negativas
NEGATIVE_EMOTIONS = {"angry", "fear", "disgust", "sad"}

# Segundos que tiene que durar una emoción negativa para que empiece a sumar estrés
STRESS_TIME_THRESHOLD = 5  # segundos

# Rango del índice acumulado de estrés
STRESS_MIN, STRESS_MAX = 0.0, 100.0


def main():
    person_id = "demo_user"
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("No se pudo abrir la cámara")
        return

    # Índice acumulado de estrés
    stress_index = 0.0

    # Para saber si llevamos un rato en emoción negativa
    currently_negative = False
    negative_start_time: datetime | None = None

    # Para no saturar la base de datos
    last_db_insert_time: datetime | None = None

    while True:
        ret, frame = cap.read()
        if not ret:
            print("No se pudo leer un frame de la cámara")
            break

        frame = cv2.flip(frame, 1)
        now = datetime.now()

        results = analyze_frame(frame)

        for r in results:
            x, y, w, h = r["box"]
            emotion = r["emotion"]
            gender = r["gender"]

            em_lower = emotion.lower()
            weight = emotion_weight(emotion)

            # --- Actualizar índice de estrés ---

            if em_lower in NEGATIVE_EMOTIONS:
                # Entramos (o seguimos) en emoción negativa
                if not currently_negative:
                    currently_negative = True
                    negative_start_time = now

                elapsed = (
                    (now - negative_start_time).total_seconds()
                    if negative_start_time is not None
                    else 0.0
                )

                # Solo sumamos estrés si la emoción negativa se mantiene
                if elapsed >= STRESS_TIME_THRESHOLD:
                    # weight > 0 para emociones malas -> sube el índice
                    stress_index += weight
            else:
                # Salimos de una emoción negativa
                currently_negative = False
                negative_start_time = None

                # Emociones neutras/positivas relajan un poco el índice
                # (weight suele ser <= 0)
                stress_index += weight

            # Mantener el índice dentro del rango 0-100
            stress_index = max(STRESS_MIN, min(STRESS_MAX, stress_index))

            # --- Convertir índice acumulado en nivel de estrés ---
            
            if stress_index < 15:
                stress_level = "muy bajo"
            elif stress_index < 30:
                stress_level = "bajo"
            elif stress_index < 50:
                stress_level = "medio"
            elif stress_index < 75:
                stress_level = "muy alto"
            else:
                stress_level = "alto"

            # --- Dibujar en pantalla ---

            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            text1 = f"{emotion} - {gender}"
            cv2.putText(
                frame,
                text1,
                (x, y - 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
            )

            text2 = f"estrés: {stress_level} ({stress_index:.1f})"
            cv2.putText(
                frame,
                text2,
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 0),
                2,
            )

            # --- Guardar en Supabase (máx. 1 vez/segundo) ---

            if (
                last_db_insert_time is None
                or (now - last_db_insert_time).total_seconds() >= 1
            ):
                insert_emotion(person_id,emotion, gender, stress_index, stress_level)
                last_db_insert_time = now

        cv2.imshow("Emociones - pulsa q para salir", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
