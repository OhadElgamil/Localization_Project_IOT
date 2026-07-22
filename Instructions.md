# Instructions
make sure that python3.10+ is installed
amd also this specific pi_camera package
```bash
sudo apt intsall python3-picamera2
```
## setup venv
create the venv
```bash
python3 -m venv venv
```
than start up the venv
```bash
source venv/bin/activate
```
download all the requirements
```bash
pip install -r requirements.txt
```


## Running The Project
start up the flutter app side server
```bash
cd PI/pi_server/
python3 server.py
```
than the pipeline runnning
```bash
cd PI/pipeline/
python3 pipeline.py
```

this is enough for a fully working system
in order to run the app, you should build and install it through android stuio using
```bash
flutter build apk --release
flutter install -d <device_id>
```
to view devices id's you can run
```bash
flutter devices
```


