import requests
import unittest
import time

ESP32_STREAM = "http://192.168.1.119:81"
ESP32_IP = "http://192.168.1.119"
TIMEOUT  = 10  # seconds


class TestCameraWebServer(unittest.TestCase):

    #test1: checks the camera is alive 
    def test_01_status_endpoint_responds(self):
        response = requests.get(f"{ESP32_IP}/status", timeout=TIMEOUT)
        self.assertEqual(response.status_code, 200)

    #test2: checks that the response is valid
    def test_02_status_returns_json(self):
        response = requests.get(f"{ESP32_IP}/status", timeout=TIMEOUT)
        data = response.json()  # raises if not valid JSON
        self.assertIsInstance(data, dict)

    #test3 : the response is not just valid JSON, but also contains the right fields
    def test_03_status_has_expected_fields(self):
        response = requests.get(f"{ESP32_IP}/status", timeout=TIMEOUT)
        data = response.json()
        expected_fields = [
            "framesize", "quality", "brightness",
            "saturation", "contrast", "hmirror",
            "awb", "agc", "aec"
        ]
        for field in expected_fields:
            self.assertIn(field, data, msg=f"Missing field: {field}")

    #test4 :the camera replies to capture request successfully
    def test_04_capture_endpoint_responds(self):
        response = requests.get(f"{ESP32_IP}/capture", timeout=TIMEOUT)
        self.assertEqual(response.status_code, 200)

    #test5 : checks if the response to capture request is a valid jpeg image
    def test_05_capture_returns_jpeg_content_type(self):
        response = requests.get(f"{ESP32_IP}/capture", timeout=TIMEOUT)
        self.assertIn("image/jpeg", response.headers.get("Content-Type", ""))

    #test 6: checks that the picture is not empty and has data in it
    def test_06_capture_has_data(self):
        response = requests.get(f"{ESP32_IP}/capture", timeout=TIMEOUT)
        self.assertGreater(len(response.content), 0)

  

    #test 7: checks that control request changes something succesfully
    def test_07_control_changes_setting(self):
        # Set framesize to QVGA (value 5)
        requests.get(f"{ESP32_IP}/control?var=framesize&val=5", timeout=TIMEOUT)
        time.sleep(0.5)
        status = requests.get(f"{ESP32_IP}/status", timeout=TIMEOUT).json()
        self.assertEqual(status["framesize"], 5)

 
   #test8: verifies that the stream request works(only connection)
    def test_08_stream_endpoint_responds(self):
        response = requests.get(
            f"{ESP32_STREAM}/stream", timeout=TIMEOUT, stream=True
        )
        self.assertEqual(response.status_code, 200)
        response.close()

    #test9: the stream returns valid content
    def test_09_stream_returns_mjpeg_content_type(self):
        response = requests.get(
            f"{ESP32_STREAM}/stream", timeout=TIMEOUT, stream=True
        )
        content_type = response.headers.get("Content-Type", "")
        self.assertIn("multipart/x-mixed-replace", content_type)
        response.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
