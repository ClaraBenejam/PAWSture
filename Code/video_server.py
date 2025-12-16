"""
video_server_minimal_fixed.py
Minimal video server that shares camera frames with connected clients
"""

import cv2
import socket
import pickle
import struct
import threading
import time
import numpy as np


class MinimalVideoServer:
    """Server that streams video frames to multiple connected clients."""
    
    def __init__(self, host='127.0.0.1', port=9999):
        """
        Initialize video server.
        
        Parameters:
            host: Server IP address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.running = True
        self.clients = []
        self.lock = threading.Lock()
        self.server_socket = None
    
    def start_camera(self):
        """
        Initialize camera capture device.
        
        Returns:
            True if camera opened successfully, False otherwise
        """
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print("Error: Could not open camera")
            return False
        
        # Set camera resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("✓ Camera initialized")
        return True
    
    def handle_client(self, client_socket):
        """
        Handle individual client connection by streaming frames.
        
        Parameters:
            client_socket: Socket connection to client
        """
        try:
            while self.running:
                # Capture frame from camera
                ret, frame = self.cap.read()
                if not ret:
                    # Send black frame on camera error
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Encode and send frame
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                frame_data = pickle.dumps(buffer)
                frame_size = struct.pack("L", len(frame_data))
                
                # Send frame size and data
                try:
                    client_socket.sendall(frame_size)
                    client_socket.sendall(frame_data)
                except (socket.error, ConnectionError):
                    break  # Client disconnected
                
                # Control FPS (~30 FPS)
                time.sleep(0.033)
                
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            # Remove client from list and close connection
            with self.lock:
                if client_socket in self.clients:
                    self.clients.remove(client_socket)
            try:
                client_socket.close()
            except:
                pass
    
    def accept_connections(self):
        """Accept incoming client connections in a loop."""
        self.server_socket.settimeout(1.0)  # Timeout to check running status
        
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                print(f"Client connected: {addr}")
                
                with self.lock:
                    self.clients.append(client_socket)
                
                # Start thread for this client
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()
                
            except socket.timeout:
                continue  # Timeout, check if still running
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")
    
    def run(self):
        """Main server execution loop."""
        print("\n" + "="*50)
        print("MINIMAL VIDEO SERVER")
        print("="*50)
        
        if not self.start_camera():
            return
        
        # Create server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"Server listening on {self.host}:{self.port}")
        print("Waiting for client connections...")
        print("Press Ctrl+C to stop server")
        print("="*50 + "\n")
        
        # Start connection acceptance thread
        accept_thread = threading.Thread(target=self.accept_connections, daemon=True)
        accept_thread.start()
        
        try:
            # Keep main thread alive waiting for Ctrl+C
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nCtrl+C pressed. Stopping server...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Cleanly stop server and release resources."""
        print("Stopping server...")
        self.running = False
        
        # Close all client connections
        with self.lock:
            for client_socket in self.clients:
                try:
                    client_socket.close()
                except:
                    pass
            self.clients.clear()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        # Release camera
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        
        print("Server stopped successfully")


if __name__ == "__main__":
    server = MinimalVideoServer()
    server.run()
