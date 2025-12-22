from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Ajouter le répertoire parent au path pour importer embroidery_generator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import main as embroidery_main, optimize_rung_parameters

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
STATIC_FOLDER = 'static'

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, STATIC_FOLDER]:
    os.makedirs(folder, exist_ok=True)

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/optimize', methods=['POST'])
def optimize_svg():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Aucun fichier fourni'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Aucun fichier sélectionné'}), 400

        if not file.filename.lower().endswith('.svg'):
            return jsonify({'error': 'Le fichier doit être un SVG'}), 400

        # Récupérer les paramètres
        spacing = float(request.form.get('spacing', 3.0))
        density = float(request.form.get('density', 1.0))

        # Sauvegarder le fichier temporairement
        with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name

        try:
            # Simuler les arguments de ligne de commande
            original_argv = sys.argv.copy()
            sys.argv = [
                'main.py',
                temp_path,
                f'--spacing={spacing}',
                f'--density={density}',
                '--debug',
                '--verbose',
                '--no-preview'
            ]

            # Rediriger stdout pour capturer les logs
            import io
            from contextlib import redirect_stdout

            output_buffer = io.StringIO()
            with redirect_stdout(output_buffer):
                try:
                    embroidery_main()
                except SystemExit:
                    # La fonction main() fait sys.exit(0) à la fin, c'est normal
                    pass
                except Exception as e:
                    return jsonify({'error': f'Erreur lors du traitement: {str(e)}'}), 500

            logs = output_buffer.getvalue()

            # Restaurer sys.argv
            sys.argv = original_argv

            # Analyser les logs pour extraire les informations
            result = parse_logs(logs)

            # Chercher les fichiers générés
            output_files = {}
            debug_images = {}
            if os.path.exists(OUTPUT_FOLDER):
                for filename in os.listdir(OUTPUT_FOLDER):
                    if filename.endswith(('_rungs.svg', '_ready.svg')) or (filename.endswith('.svg') and not filename.startswith('debug_')):
                        # Map display name to filename
                        if '_rungs.svg' in filename:
                            output_files['Rungs Only'] = filename
                        elif '_ready.svg' in filename:
                            output_files['Ready to Edit'] = filename
                        else:
                            output_files[filename] = filename

                # Chercher les images de debug
                debug_dir = os.path.join(OUTPUT_FOLDER, 'debug')
                if os.path.exists(debug_dir):
                    for filename in os.listdir(debug_dir):
                        if filename.endswith(('.png', '.svg')) and filename.startswith('debug_'):
                            debug_images[filename] = f'{OUTPUT_FOLDER}/debug/{filename}'

            result['output_files'] = output_files
            result['debug_images'] = debug_images
            result['logs'] = logs[-2000:]  # Derniers 2000 caractères des logs

            return jsonify(result)

        finally:
            # Nettoyer le fichier temporaire
            os.unlink(temp_path)

    except Exception as e:
        return jsonify({'error': f'Erreur serveur: {str(e)}'}), 500

def parse_logs(logs):
    """Analyse les logs pour extraire les informations importantes"""
    result = {
        'rungs_count': 0,
        'intersections': 0,
        'bridges': 0,
        'coverage': 0.0,
        'success': False
    }

    lines = logs.split('\n')

    for line in lines:
        line = line.strip()

        # Nombre de rungs
        if 'Saving' in line and 'rungs' in line:
            try:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit() and i < len(parts) - 1 and 'rungs' in parts[i+1]:
                        result['rungs_count'] = int(part)
                        break
            except:
                pass

        # Bridges
        elif 'Saving' in line and 'bridges' in line:
            try:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit() and i < len(parts) - 1 and 'bridges' in parts[i+1]:
                        result['bridges'] = int(part)
                        break
            except:
                pass

        # Couverture
        elif 'Coverage:' in line:
            try:
                parts = line.split()
                for part in parts:
                    if ':' in part:
                        value = part.split(':')[1]
                        try:
                            coverage_ratio = float(value)
                            result['coverage'] = coverage_ratio * 100  # Convert to percentage
                            break
                        except:
                            pass
            except:
                pass

        # Succès
        elif 'Done!' in line:
            result['success'] = True

    # Set intersections to bridges if not found
    if 'intersections' not in result:
        result['intersections'] = result.get('bridges', 0)

    return result

@app.route('/api/download/<filename>')
def download_file(filename):
    """Télécharger un fichier généré"""
    try:
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'Fichier non trouvé'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/<path:filename>')
def serve_debug_image(filename):
    """Servir les images de debug"""
    try:
        print(f"DEBUG: Current working directory: {os.getcwd()}")
        debug_dir = os.path.join(OUTPUT_FOLDER, 'debug')
        print(f"DEBUG: Debug dir: {debug_dir}")
        file_path = os.path.join(debug_dir, filename)
        print(f"DEBUG: Looking for file: {file_path}")
        print(f"DEBUG: File exists: {os.path.exists(file_path)}")
        if os.path.exists(file_path):
            print(f"DEBUG: Serving file: {file_path}")
            return send_file(file_path, mimetype='image/png')
        else:
            print(f"DEBUG: File not found: {file_path}")
            return jsonify({'error': 'Image de debug non trouvée'}), 404
    except Exception as e:
        print(f"DEBUG: Error serving file: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)