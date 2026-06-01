# Preparación de entorno
python -m venv .env
source ./.env/bin/activate
pip install -r requirements.txt

# Descarga y procesamiento de datos
python scripts/download_data.py
python scripts/process_data.py
python scripts/spatial_analysis.py

# Inicialización de aplicación
streamlit run ./app/main.py