# Shaketune Web Service

This web service provides an HTTP API for processing Klipper shaper calibration data and generating graphs.

## API Endpoints

### POST /process/{macro_type}

Process CSV data and generate graphs for the specified macro type.

Available macro types:
- axes_map
- belts
- shaper
- vibrations
- static

Request:
- Method: POST
- Content-Type: multipart/form-data
- Body: CSV file in the 'file' field

Response:
- Success: PNG image file
- Error: JSON with error message

### GET /health

Health check endpoint.

Response:
- 200 OK with {"status": "healthy"}

## Running the Service

### Using Python directly

1. Install dependencies:
```bash
cd shaketune/webservice
pip install -r requirements.txt
cd ../..
pip install -r requirements.txt
```

2. Run the service:
```bash
cd shaketune/webservice
python app.py
```

### Using Gunicorn

1. Install dependencies as above, then run:
```bash
cd shaketune/webservice
gunicorn --bind 0.0.0.0:5000 app:app
```

### Using Docker

1. Build the image:
```bash
docker build -t shaketune-webservice -f shaketune/webservice/Dockerfile .
```

2. Run the container:
```bash
docker run -p 5000:5000 shaketune-webservice
```

## Example Usage

Using curl to process a CSV file:

```bash
curl -X POST -F "file=@/path/to/your/data.csv" http://localhost:5000/process/shaper -o output.png
