# Algorithms
We use a large amount of algorithms, as this project relies on them heavily, this file will try to explain them as cleanly as possible

### Localization
The heavy algorithm - DOR PUT HERE

## Camera Image Snapping
This algorithm is the one taking pictures from each camera and decieds which images to pass on to the next level in pipe
We tests its performance by how quick can it capture images and pass them on - we measure it by sending time marks as a part of each packet that the camera's recieve and send.
### Performance: 
Pi-cam - 40ms
FRONT - 450ms
RIGHT - 370ms
LEFT - 420ms
Leaning on that information the algorithm draws images at a speed of 1 image from each camera every 500ms

## ArUco Detection
For ArUco markers detection, we use a pre-built framework fitted directly for ArUco markers, by OpenCV.
Its performance is great and available to view online.

