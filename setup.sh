# Preparación de entorno
python -m venv .env
source ./.env/bin/activate
pip install -r requirements.txt

python scripts/download_data.py