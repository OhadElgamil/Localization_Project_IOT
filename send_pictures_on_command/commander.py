import socket

HOST = '0.0.0.0'
PORT = 5000

def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Allow reusing the port immediately if the script restarts
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server listening on port {PORT}...")

        # Keep running forever, taking pictures on command
        photo_count = 0
        while True:
            print("\nWaiting for camera to connect and report 'READY'...")
            conn, addr = s.accept()
            
            with conn:
                # 1. Wait for the READY signal
                data = conn.recv(1024).decode('utf-8')
                if "READY" in data:
                    print(f"Camera at {addr[0]} is connected and READY.")
                    
                    # 2. Wait for manual trigger from you
                    input("Press ENTER to command the camera to take a picture...")
                    
                    # 3. Send the command
                    conn.sendall(b"SNAP\n")
                    print("Command sent. Receiving image...")
                    
                    # 4. Receive the image data until the ESP32 hangs up
                    image_data = b""
                    while True:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break # Connection closed by ESP32
                        image_data += chunk
                    
                    # 5. Save the file
                    if image_data:
                        filename = f"photo_{photo_count}.jpg"
                        with open(filename, "wb") as f:
                            f.write(image_data)
                        print(f"Success! Saved as {filename}")
                        photo_count += 1

if __name__ == "__main__":
    run_server()