#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>

// ===========================
// Configuration - UPDATE THESE
// ===========================
const char* ssid = "PiNet";
const char* pi_ip = "10.42.0.1"; // Raspberry Pi's IP address

const uint16_t tcp_port = 8888;
const uint16_t udp_port = 9999;

// AI Thinker Camera Pins
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

WiFiUDP udp;
char packetBuffer[255]; 

void setup_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  
  // SVGA (800x600) is a good balance between network speed and ArUco clarity
  config.frame_size = FRAMESIZE_SVGA;
  config.jpeg_quality = 12; // 0-63 lower means higher quality
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed");
    return;
  }
}

void setup() {
  Serial.begin(115200);
  
  setup_camera();

  // Connect to WiFi
  WiFi.begin(ssid);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");

  // Start UDP listener
  udp.begin(udp_port);
  Serial.printf("Listening for UDP triggers on port %d\n", udp_port);
}

void send_frame() {
  camera_fb_t * fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    return;
  }

  WiFiClient client;
  if (client.connect(pi_ip, tcp_port)) {
    // Send 4-byte length header (Little Endian, matching Python's '<I')
    uint32_t image_len = fb->len;
    client.write((const uint8_t *)&image_len, 4);
    
    // Send payload
    client.write(fb->buf, fb->len);
    client.stop();
  } else {
    Serial.println("TCP Connection failed");
  }

  // Return the frame buffer back to the driver for reuse
  esp_camera_fb_return(fb);
}

void loop() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    int len = udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0;
    
    // If the trigger is received, capture and send
    if (strncmp(packetBuffer, "CAPTURE", 7) == 0) {
      send_frame();
    }
  }
}