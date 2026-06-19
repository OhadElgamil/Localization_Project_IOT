import socket

HOST = '0.0.0.0'
PORT = 5000

def run_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server listening on port {PORT}...")

        photo_count = 0
        while True:
            print("\nWaiting for camera to connect...")
            conn, addr = s.accept()
            
            with conn:
                print(f"Camera connected from {addr[0]}. Waiting for 'READY'...")
                
                # Read the initial READY signal including the newline character
                # Using makefile to easily read data line-by-line
                rfile = conn.makefile('rb')
                ready_line = rfile.readline().decode('utf-8').strip()
                
                if "READY" not in ready_line:
                    print("Did not receive READY signal. Closing connection.")
                    continue
                
                print("Camera is READY. Persistent connection established.")

                # Continuous capture loop using the existing persistent connection
                while True:
                    try:
                        # 1. Wait for manual user trigger
                        input("Press ENTER to command the camera to take a picture...")
                        
                        # 2. Send SNAP command
                        conn.sendall(b"SNAP\n")
                        print("Command sent. Waiting for image size...")
                        
                        # 3. Read the first line containing the image size in bytes
                        size_line = rfile.readline().decode('utf-8').strip()
                        if not size_line:
                            print("Connection closed by ESP32.")
                            break
                        
                        image_len = int(size_line)
                        print(f"Expecting image of size: {image_len} bytes. Receiving...")
                        
                        # 4. Read exactly x bytes from the stream
                        image_data = b""
                        bytes_remaining = image_len
                        
                        while bytes_remaining > 0:
                            # Read at most 4096 bytes or the remaining bytes of the image
                            chunk = conn.recv(min(4096, bytes_remaining))
                            if not chunk:
                                break  # Unexpected disconnection
                            image_data += chunk
                            bytes_remaining -= len(chunk)
                        
                        # 5. Save the file if all bytes were successfully received
                        if len(image_data) == image_len:
                            filename = f"photo_{photo_count}.jpg"
                            with open(filename, "wb") as f:
                                f.write(image_data)
                            print(f"Success! Saved as {filename}\n")
                            photo_count += 1
                        else:
                            print(f"Error: Received incomplete image ({len(image_data)}/{image_len} bytes).")
                            break

                    except (socket.error, ValueError) as e:
                        print(f"Connection error or invalid data: {e}")
                        break

if __name__ == "__main__":
    run_server()