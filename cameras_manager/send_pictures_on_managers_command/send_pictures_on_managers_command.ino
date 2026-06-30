#include <WiFi.h>
#include "esp_camera.h"

// ===========================
// Network & Pi Settings
const char* ssid = "PiNet";

const char* pi_ip = "10.42.0.1";
const int pi_port = 5000;

// ===========================
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

void setup() {
  Serial.begin(115200);
  Serial.println();

  // 1. Initialize Camera in JPEG mode
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
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size   = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed with error 0x%x\n", err);
    return;
  }
  Serial.println("Camera initialized!");

  // 2. Let sensor stabilize before connecting WiFi
  delay(500);
  for (int i = 0; i < 2; ++i) {
    camera_fb_t * fb = esp_camera_fb_get();
    esp_camera_fb_return(fb); 
  }

  // 3. Connect to Wi-Fi
  WiFi.begin(ssid);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  WiFiClient client;
  
  if (client.connect(pi_ip, pi_port)) {    
    Serial.println("Connected to Pi. Sending READY signal...");
    client.print("READY\n");

    while (client.connected()) {
      if (client.available()) {
        String command = client.readStringUntil('\n');
        command.trim(); 
        
        if (command == "DISCONNECT") {
          Serial.println("DISCONNECT command received from Pi. Reconnecting...");
          break; // Break loop to stop client and trigger a clean reconnect sequence
        }
        else if (command == "SNAP") {
          Serial.println("SNAP command received! Clearing old buffers...");
          
          for (int i = 0; i < 2; i++) {
            camera_fb_t* discard = esp_camera_fb_get();
            if (discard) {
              esp_camera_fb_return(discard);
            }
          }

          camera_fb_t * fb = esp_camera_fb_get();
          if (fb) {
            client.printf("%d\n", fb->len);
            client.write(fb->buf, fb->len);
            client.flush(); 
            
            esp_camera_fb_return(fb); 
            Serial.println("Fresh image sent successfully.");
          } else {
            Serial.println("Camera capture failed!");
          }
        }
      }
    }
    
    Serial.println("Cleaning up socket connection...");
    client.stop();
    delay(500); 
    
  } else {
    Serial.println("Cannot connect to Pi. Retrying in 2 seconds...");
    delay(2000);
  }
}