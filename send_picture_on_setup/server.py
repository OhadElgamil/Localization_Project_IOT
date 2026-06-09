import socket

ESP32_IP = '192.168.1.45' # The IPv4 address of your ESP32
PORT = 5000

def fetch_photo(camera_ip, save_name):
    print(f"Connecting to {camera_ip} to request photo...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((camera_ip, PORT))
            
            image_data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                image_data += chunk
                
            if image_data:
                with open(save_name, "wb") as f:
                    f.write(image_data)
                print(f"Success! Saved as {save_name}")
    except Exception as e:
        print(f"Failed to fetch photo: {e}")

if __name__ == "__main__":
    fetch_photo(ESP32_IP, "pulled_image.jpg")