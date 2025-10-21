from google.oauth2 import service_account
from googleapiclient.discovery import build

# Lê credenciais diretamente do arquivo JSON
credentials = service_account.Credentials.from_service_account_file("keys/service_account.json")

# Cria serviço do Google Sheets
sheets_service = build('sheets', 'v4', credentials=credentials)
