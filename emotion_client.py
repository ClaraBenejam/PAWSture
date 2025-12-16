"""emotion_client_minimal.py - Modified version for emotion analysis client"""

import cv2
import socket
import pickle
import struct
from datetime import datetime
import sys

# Import original modules
from emotion_detector import analyze_frame, emotion_weight
from cloud_db import insert_emotion

# Server configuration
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 9999

# Original constants
NEGATIVE_EMOTIONS = {"angry", "fear", "disgust", "sad"}
STRESS_TIME_THRESHOLD = 5
STRESS_MIN, STRESS_MAX = 0.0, 100.0


def receive_frame(client_socket):
    """
    Receive a frame from the server via socket connection.
    
    Parameters:
        client_socket: Active socket connection to server
        
    Returns:
        Decoded frame as numpy array or None if connection lost
    """
    # Receive frame size (4 bytes)
    frame_size_data = b""
    while len(frame_size_data) < struct.calcsize("L"):
        data = client_socket.recv(4)
        if not data:
            return None
        frame_size_data += data
    
    frame_size = struct.unpack("L", frame_size_data)[0]
    
    # Receive frame data
    frame_data = b""
    while len(frame_data) < frame_size:
        packet = client_socket.recv(min(4096, frame_size - len(frame_data)))
        if not packet:
            return None
        frame_data += packet
    
    # Decode frame
    encoded_frame = pickle.loads(frame_data)
    frame = cv2.imdecode(encoded_frame, cv2.IMREAD_COLOR)
    return frame


def main():
    """
    Main function for emotion analysis client.
    Connects to video server, analyzes frames, and displays results.
    """
    # Get employee ID from command line arguments
    person_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
    # Connect to server
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((SERVER_HOST, SERVER_PORT))
        print(f"Connected to video server for employee ID: {person_id}")
    except ConnectionRefusedError:
        print("Error: Could not connect to server. Run video_server_minimal.py first")
        return
    
    # Initialize tracking variables
    stress_index = 0.0
    currently_negative = False
    negative_start_time = None
    last_db_insert_time = None
    
    print("\n" + "="*50)
    print(f"EMOTION CLIENT - EMPLOYEE ID: {person_id}")
    print("="*50)
    print("Press 'q' to exit")
    print("="*50 + "\n")
    
    try:
        while True:
            # Receive frame from server
            frame = receive_frame(client_socket)
            if frame is None:
                print("Server disconnected")
                break
            
            # Apply mirror effect
            frame = cv2.flip(frame, 1)
            now = datetime.now()
            
            # Analyze emotions in frame
            results = analyze_frame(frame)
            
            for r in results:
                x, y, w, h = r["box"]
                emotion = r["emotion"]
                gender = r["gender"]
                
                em_lower = emotion.lower()
                weight = emotion_weight(emotion)
                
                # Update stress index based on emotion
                if em_lower in NEGATIVE_EMOTIONS:
                    if not currently_negative:
                        currently_negative = True
                        negative_start_time = now
                    
                    elapsed = (now - negative_start_time).total_seconds() if negative_start_time else 0.0
                    
                    # Apply stress accumulation after threshold
                    if elapsed >= STRESS_TIME_THRESHOLD:
                        stress_index += weight
                else:
                    currently_negative = False
                    negative_start_time = None
                    stress_index += weight
                
                # Clamp stress index within bounds
                stress_index = max(STRESS_MIN, min(STRESS_MAX, stress_index))
                
                # Determine stress level category
                if stress_index < 15:
                    stress_level = "very low"
                elif stress_index < 30:
                    stress_level = "low"
                elif stress_index < 50:
                    stress_level = "medium"
                elif stress_index < 75:
                    stress_level = "very high"
                else:
                    stress_level = "high"
                
                # Draw detection results on frame
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
                
                text2 = f"stress: {stress_level} ({stress_index:.1f})"
                cv2.putText(
                    frame,
                    text2,
                    (x, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 0),
                    2,
                )
                
                # Insert data to database (max 1 per second)
                if last_db_insert_time is None or (now - last_db_insert_time).total_seconds() >= 1:
                    insert_emotion(person_id, emotion, gender, stress_index, stress_level)
                    last_db_insert_time = now
            
            # Display frame with annotations
            cv2.imshow(f"Emotions - Employee ID: {person_id} - press q to exit", frame)
            
            # Exit on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Cleanup resources
        client_socket.close()
        cv2.destroyAllWindows()
        print(f"\nEmotion client stopped for employee ID: {person_id}")


if __name__ == "__main__":
    main()