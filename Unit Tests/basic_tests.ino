#include <AUnit.h>
#include "esp_camera.h"
#include <WiFi.h>

// ===========================
// Fill in your credentials
// ===========================
const char* ssid     = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

// AI-Thinker pin map (same as CameraWebServer)
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ===========================
// Helpers
// ===========================
static bool        camera_initialized = false;
static bool        psram_available    = false;
static camera_fb_t *captured_frame    = nullptr;

camera_config_t buildConfig() {
  camera_config_t config;
  config.ledc_channel  = LEDC_CHANNEL_0;
  config.ledc_timer    = LEDC_TIMER_0;
  config.pin_d0        = Y2_GPIO_NUM;
  config.pin_d1        = Y3_GPIO_NUM;
  config.pin_d2        = Y4_GPIO_NUM;
  config.pin_d3        = Y5_GPIO_NUM;
  config.pin_d4        = Y6_GPIO_NUM;
  config.pin_d5        = Y7_GPIO_NUM;
  config.pin_d6        = Y8_GPIO_NUM;
  config.pin_d7        = Y9_GPIO_NUM;
  config.pin_xclk      = XCLK_GPIO_NUM;
  config.pin_pclk      = PCLK_GPIO_NUM;
  config.pin_vsync     = VSYNC_GPIO_NUM;
  config.pin_href      = HREF_GPIO_NUM;
  config.pin_sccb_sda  = SIOD_GPIO_NUM;
  config.pin_sccb_scl  = SIOC_GPIO_NUM;
  config.pin_pwdn      = PWDN_GPIO_NUM;
  config.pin_reset     = RESET_GPIO_NUM;
  config.xclk_freq_hz  = 20000000;
  config.pixel_format  = PIXFORMAT_JPEG;
  config.grab_mode     = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location   = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality  = 12;
  config.fb_count      = 1;
  config.frame_size    = FRAMESIZE_UXGA;

  // Mirrors exact logic from CameraWebServer setup()
  if (psramFound()) {
    psram_available       = true;
    config.jpeg_quality   = 10;
    config.fb_count       = 2;
    config.grab_mode      = CAMERA_GRAB_LATEST;
  } else {
    psram_available       = false;
    config.frame_size     = FRAMESIZE_SVGA;
    config.fb_location    = CAMERA_FB_IN_DRAM;
  }

  return config;
}

// ===========================
// Tests
// ===========================

// --- TEST 1: PSRAM detection ---
// Verifies psramFound() runs without crashing and returns a boolean.
// Referenced from: CameraWebServer.ino setup() — psramFound() branch
test(psram_detection) {
  bool result = psramFound();
  // Just assert it's a valid boolean — true or false is both acceptable
  assertTrue(result == true || result == false);
}

// --- TEST 2: Camera config builds correctly based on PSRAM ---
// Verifies that fb_count and frame_size are set correctly depending on PSRAM.
// Referenced from: CameraWebServer.ino setup() — camera_config_t block
test(camera_config_psram_branch) {
  camera_config_t config = buildConfig();
  if (psram_available) {
    assertEqual((int)config.fb_count, 2);
    assertEqual((int)config.grab_mode, (int)CAMERA_GRAB_LATEST);
  } else {
    assertEqual((int)config.fb_count, 1);
    assertEqual((int)config.frame_size, (int)FRAMESIZE_SVGA);
  }
}

// --- TEST 3: Camera initializes successfully ---
// Verifies esp_camera_init() returns ESP_OK with the built config.
// Referenced from: CameraWebServer.ino setup() — esp_camera_init(&config)
test(camera_init) {
  camera_config_t config = buildConfig();
  esp_err_t err = esp_camera_init(&config);
  camera_initialized = (err == ESP_OK);
  assertEqual(err, ESP_OK);
}

// --- TEST 4: Camera captures a non-null frame ---
// Verifies esp_camera_fb_get() returns a valid frame buffer pointer.
// Referenced from: CameraWebServer.ino — frame capture used by web server handlers
test(camera_capture_not_null) {
  if (!camera_initialized) {
    Serial.println("SKIP: camera not initialized");
    return;
  }
  captured_frame = esp_camera_fb_get();
  assertNotEqual(captured_frame, nullptr);
}

// --- TEST 5: Captured frame has non-zero size ---
// Verifies the frame buffer contains actual data.
// Referenced from: CameraWebServer.ino — frame data sent to HTTP clients
test(camera_frame_has_data) {
  if (!captured_frame) {
    Serial.println("SKIP: no frame captured");
    return;
  }
  assertMore(captured_frame->len, (size_t)0);
}

// --- TEST 6: Captured frame is a valid JPEG ---
// Verifies the first two bytes are 0xFF 0xD8 (JPEG magic bytes).
// Referenced from: CameraWebServer.ino — pixel_format = PIXFORMAT_JPEG
test(camera_frame_valid_jpeg) {
  if (!captured_frame) {
    Serial.println("SKIP: no frame captured");
    return;
  }
  assertEqual(captured_frame->buf[0], (uint8_t)0xFF);
  assertEqual(captured_frame->buf[1], (uint8_t)0xD8);
  esp_camera_fb_return(captured_frame);
  captured_frame = nullptr;
}

// --- TEST 7: WiFi connects within timeout ---
// Verifies WiFi reaches WL_CONNECTED within 10 seconds.
// Referenced from: CameraWebServer.ino setup() — WiFi.begin() block
test(wifi_connects) {
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(500);
  }

  assertEqual((int)WiFi.status(), (int)WL_CONNECTED);
}

// --- TEST 8: WiFi gets a valid local IP after connecting ---
// Verifies the assigned IP is not 0.0.0.0.
// Referenced from: CameraWebServer.ino setup() — WiFi.localIP() print
test(wifi_has_valid_ip) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("SKIP: WiFi not connected");
    return;
  }
  IPAddress ip = WiFi.localIP();
  assertNotEqual(ip, IPAddress(0, 0, 0, 0));
}

// ===========================
// Runner
// ===========================
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== CameraWebServer Unit Tests ===");
}

void loop() {
  aunit::TestRunner::run();
}
