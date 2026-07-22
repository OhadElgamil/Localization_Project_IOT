# ArUco Barcode Localization

## Details about the project
This project provides real-time indoor localization for a mobile rig using ArUco marker barcodes.
A Raspberry Pi, connected to a built-in PiCam and three ESP-EYE modules (front/left/right), detects
ArUco markers placed at known positions in a room and computes the rig's global pose (position and
orientation) via marker-based PnP and least-squares estimation. The result is exposed over a REST API
and visualized live through a companion Flutter app, making it a low-cost, mobile, fully local, GPS-free alternative for localizing robots or devices indoors.

## Folder description:
* **PI**: Raspberry Pi side code that runs the whole localization system.
  * `pipeline/` — the manager: connects to the ESP32-CAM units and the PiCam, runs ArUco detection
    and pose estimation, and reports results to the Pi server (`api_client.py`, `aruco_localizer.py`,
    `camera_link.py`, `config.py`, `contracts.py`, `geometry.py`, `localization.py`, `marker_map.py`,
    `pipeline.py`, unit tests, `requirements.txt`, `README.md`).
  * `pi_server/` — Flask REST server exposing health/markers/localization endpoints consumed by the
    Flutter app (`server.py`, `requirements.txt`).
  * `cameras_manager/` — standalone tool for connecting to and calibrating multiple ESP32-CAM units
    (`cameras_manager.py`, `multiple_cameras_calibration.py`, `documentation.txt`).
* **calibration**: camera calibration script and the checkerboard images used to calibrate the
  cameras' intrinsic parameters (`calibration.py`, `calib_images/`, `calib_images_T1_bad/`).
* **ESP32**: firmware (Arduino sketches) that runs on the ESP32-CAM modules, plus wiring/build notes
  (`send_pictures_on_managers_command/`, `esp32cam_constant_stream/`, `parameters.h`, `SECRETS.h`,
  `compiled_program.bin`, `how_to_export_compiled_program.txt`).
* **ESP_EYE**: firmware for the ESP-EYE camera module (`send_pictures_on_command/`).
* **flutter_app**: Dart/Flutter source code for the mobile monitoring and calibration app
  (`lib/models/`, `lib/providers/`, `lib/screens/`, `lib/services/`, plus the standard Flutter
  platform folders `android/`, `ios/`, `linux/`, `macos/`, `windows/`, `web/`).
* **optitrack_server**: server that interfaces with the OptiTrack motion capture system, used as a
  ground-truth reference for evaluating localization accuracy (`server.py`, `requirements.txt`).
* **Documentation**: wiring/connection diagram and basic operating instructions.
* **Unit Tests**: tests for individual hardware components, input/output devices (`basic_tests.ino`,
  `HTTP_tests.py`, `README.md`).

## Libraries used in this project:
* opencv-contrib-python
* numpy
* requests
* flask
* flask-cors
* python3-picamera2 (installed via `sudo apt install python3-picamera2` on the Raspberry Pi)

## Project Poster:
<!-- Place your project poster here -->

This project is part of ICST - The Interdisciplinary Center for Smart Technologies, Taub Faculty of Computer Science, Technion
https://icst.cs.technion.ac.il/
