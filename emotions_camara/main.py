import cv2
from datetime import datetime

from emotion_detector import analyze_frame, stress_from_emotion
from db import init_db, get_connection, insert_emotion

NEGATIVE_EMOTIONS = {"angry", "fear", "disgust", "sad", "neutral"}
STRESS_TIME_THRESHOLD = 5  # segundos


current_emotion = None
emotion_start_time = None


def main():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("No se pudo abrir la cámara")
        return

    # estado para controlar tiempo en emociones negativas
    currently_negative = False
    negative_start_time = None

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

            # estrés "instantáneo" según emoción
            base_score, base_level = stress_from_emotion(emotion)
            em_lower = emotion.lower()

            if em_lower in NEGATIVE_EMOTIONS:
                if not currently_negative:
                    currently_negative = True
                    negative_start_time = now

                elapsed = 0
                if negative_start_time is not None:
                    elapsed = (now - negative_start_time).total_seconds()

                if elapsed < STRESS_TIME_THRESHOLD:
                    # 0–5 s: sin estrés
                    stress_score = 0.0
                    stress_level = "bajo"
                elif elapsed < STRESS_TIME_THRESHOLD * 2:
                    # 5–10 s: estrés medio (mitad del base_score)
                    stress_score = base_score / 2
                    stress_level = "medio"
                else:
                    # >10 s: estrés alto (score completo)
                    stress_score = base_score
                    stress_level = base_level


            else:
                # emoción no negativa -> reseteamos
                currently_negative = False
                negative_start_time = None
                stress_score = 0.0
                stress_level = "bajo"

            # dibujar en pantalla
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            text1 = f"{emotion} - {gender}"
            cv2.putText(frame, text1, (x, y - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            text2 = f"stress: {stress_level} ({stress_score:.1f})"
            cv2.putText(frame, text2, (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

            # guardar en BD
            insert_emotion(cursor, emotion, gender, stress_score, stress_level)

        conn.commit()
        cv2.imshow("Emociones - pulsa q para salir", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    conn.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
