import os
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import sys
import tempfile

# Configure import paths - point to root containing shaketune 
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now we can import using the package name
from shaketune.graph_creators import (
    AxesMapGraphCreator,
    BeltsGraphCreator, 
    ShaperGraphCreator,
    StaticGraphCreator,
    VibrationsGraphCreator
)

app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/process/<macro_type>', methods=['POST'])
def process_data(macro_type):
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Only CSV files are allowed"}), 400

    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Create temporary directory for output
        output_dir = tempfile.mkdtemp()
        
        # Process based on macro type
        if macro_type == "axes_map":
            creator = AxesMapGraphCreator(filepath, output_dir)
        elif macro_type == "belts":
            creator = BeltsGraphCreator(filepath, output_dir)
        elif macro_type == "shaper":
            creator = ShaperGraphCreator(filepath, output_dir)
        elif macro_type == "vibrations":
            creator = VibrationsGraphCreator(filepath, output_dir)
        elif macro_type == "static":
            creator = StaticGraphCreator(filepath, output_dir)
        elif macro_type == "excitate":
            creator = StaticGraphCreator(filepath, output_dir)  # Using StaticGraphCreator for excitation data
        else:
            return jsonify({"error": f"Unknown macro type: {macro_type}"}), 400

        # Generate graphs
        creator.create_graph()
        
        # Find generated graph file(s)
        graph_files = []
        for file in os.listdir(output_dir):
            if file.endswith(('.png', '.pdf')):
                graph_files.append(os.path.join(output_dir, file))

        if not graph_files:
            return jsonify({"error": "No graphs were generated"}), 500

        # For now, return the first graph file
        # TODO: Support multiple graph files if needed
        return send_file(graph_files[0], mimetype='image/png')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # Cleanup temporary files
        try:
            os.remove(filepath)
            for root, dirs, files in os.walk(output_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(output_dir)
        except:
            pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
