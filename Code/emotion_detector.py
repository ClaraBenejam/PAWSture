"""
Emotion detection using DeepFace library.
Analyzes faces in video frames to detect emotions and gender.
"""

import cv2
from deepface import DeepFace

# Load OpenCV face classifier (once at module load)
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def analyze_frame(frame):
    """
    Analyze faces in frame to detect emotions and gender.
    
    Parameters:
        frame: BGR image frame from OpenCV
        
    Returns:
        List of dictionaries with detection results:
        - box: (x, y, width, height) of face
        - emotion: Detected emotion string
        - gender: Detected gender string
    """
    # Convert to grayscale for face detection
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Detect faces with optimized parameters
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.3,
        minNeighbors=3,
    )
    
    results = []
    
    # Process each detected face
    for (x, y, w, h) in faces:
        face_roi = frame[y: y + h, x: x + w]
        
        try:
            # Analyze face with DeepFace
            analysis = DeepFace.analyze(
                face_roi,
                actions=["emotion", "gender"],
                enforce_detection=False,
                detector_backend="opencv",
            )
            
            # Handle DeepFace output format
            if isinstance(analysis, list):
                analysis = analysis[0]
            
            emotion = analysis.get("dominant_emotion", "unknown")
            gender = analysis.get("dominant_gender", "unknown")
            
            results.append({
                "box": (x, y, w, h),
                "emotion": emotion,
                "gender": gender,
            })
            
        except Exception as e:
            print(f"[DeepFace] Error analyzing face: {e}")
            continue
    
    return results


def emotion_weight(emotion: str) -> float:
    """
    Get weight value for emotion to calculate stress index.
    
    Parameters:
        emotion: Emotion string from analysis
        
    Returns:
        Weight value:
        - Positive: Increases stress
        - Negative: Decreases stress
        - Near zero: Minimal effect
    """
    if not emotion:
        return 0.0
    
    emotion = emotion.lower()
    
    # Weight definitions based on emotional impact
    weights = {
        "angry": 2.0,      # High stress increase
        "fear": 2.0,       # High stress increase
        "disgust": 1.5,    # Medium stress increase
        "sad": 1.0,        # Low stress increase
        "surprise": 0.2,   # Minimal effect
        "neutral": -0.1,   # Slight stress reduction
        "happy": -1.5,     # Significant stress reduction
    }
    
    return weights.get(emotion, 0.0)
