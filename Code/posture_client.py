"""posture_client_minimal.py - Modified version for posture analysis client"""

import cv2
import socket
import pickle
import struct
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import PostureScorer from original module
from yolo9 import PostureScorer

# Server configuration
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 9999


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
    Main function for posture analysis client.
    Connects to video server, analyzes posture, and displays results.
    """
    # Get user ID from command line arguments
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
    # Initialize PostureScorer with user ID
    print(f"Initializing PostureScorer for user ID: {user_id}...")
    scorer = PostureScorer(user_id=user_id)
    
    # Connect to server
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((SERVER_HOST, SERVER_PORT))
        print("Connected to video server")
    except ConnectionRefusedError:
        print("Error: Could not connect to server. Run video_server_minimal.py first")
        return
    
    print("\n" + "="*50)
    print(f"POSTURE CLIENT - USER ID: {user_id}")
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
            
            # Process frame with PostureScorer
            annotated_frame, scores = scorer.process_frame(frame)
            
            # Display posture information on frame
            y_offset = 30
            
            if scores:
                overall = scores.get('overall', {})
                overall_zone = overall.get('zone', 0)
                overall_color = scorer.zone_colors[overall_zone]
                
                # Show overall posture
                cv2.putText(annotated_frame, 
                           f"Posture: {overall.get('risk', 'Unknown')} (Zone {overall_zone})", 
                           (10, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, overall_color, 2)
                y_offset += 30
                
                # Show user ID
                cv2.putText(annotated_frame, 
                           f"User ID: {user_id}", 
                           (10, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                y_offset += 20
                
                # Show individual parameters (limited to 3 to avoid clutter)
                param_count = 0
                for param, data in scores.items():
                    if param != 'overall' and param_count < 3:
                        zone = data['zone']
                        color = scorer.zone_colors[zone]
                        
                        display_name = param.replace('_', ' ').title()
                        text = f"{display_name}: {data['risk']} (Zone {zone})"
                        
                        cv2.putText(annotated_frame, text, (10, y_offset), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                        y_offset += 20
                        param_count += 1
            
            # Display annotated frame
            cv2.imshow(f'Posture Scoring - User ID: {user_id} - Press q to exit', annotated_frame)
            
            # Exit on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Cleanup resources
        client_socket.close()
        cv2.destroyAllWindows()
        print(f"\nPosture client stopped for user ID: {user_id}")


if __name__ == "__main__":
    main()
