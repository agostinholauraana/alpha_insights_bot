"""
🔧 Módulo de integração com Google Drive e Google Sheets
Fornece funções para listar planilhas e ler respostas de planilhas.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_service_utils import normalize_service_account_json
from logging_config import setup_logging

# garante que logging file handler esteja ativo
setup_logging()

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Escopos necessários para Drive e Sheets
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly'
]


class GoogleSheetsService:
    """Classe para gerenciar integração com Google Drive e Sheets"""
    
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Inicializa o serviço com autenticação via service account.
        
        Args:
            credentials_path: Caminho para o arquivo JSON de credenciais.
                            Se None, busca em 'keys/alphainsights-bot-analitico-2e700b6f55ae.json'
        """
        # Estratégias de carregamento de credenciais (em ordem):
        # 1) Variável de ambiente GOOGLE_SERVICE_ACCOUNT_JSON com o JSON completo
        # 2) Variável de ambiente GOOGLE_SERVICE_ACCOUNT_FILE com caminho para o arquivo
        # 3) Caminho fornecido por parâmetro credentials_path
        # 4) Caminho padrão local em ./keys/...
        try:
            creds = None

            json_env = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
            file_env = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')

            if json_env:
                try:
                    info = normalize_service_account_json(json_env)
                    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                    logger.info("🔐 Credenciais carregadas de GOOGLE_SERVICE_ACCOUNT_JSON")
                except Exception as e:
                    logger.error(f"Erro ao carregar GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
                    raise
            elif file_env and os.path.exists(file_env):
                creds = service_account.Credentials.from_service_account_file(file_env, scopes=SCOPES)
                logger.info(f"🔐 Credenciais carregadas de GOOGLE_SERVICE_ACCOUNT_FILE: {file_env}")
            else:
                if credentials_path is None:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    credentials_path = os.path.join(base_dir, 'keys', 'alphainsights-bot-analitico-2e700b6f55ae.json')
                if not os.path.exists(credentials_path):
                    raise FileNotFoundError(
                        "❌ Credenciais não encontradas. Defina GOOGLE_SERVICE_ACCOUNT_JSON (conteúdo) ou "
                        "GOOGLE_SERVICE_ACCOUNT_FILE (caminho), ou coloque o JSON em ./keys/."
                    )
                creds = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
                logger.info(f"🔐 Credenciais carregadas do arquivo local: {credentials_path}")

            self.credentials = creds
            
            # Constrói os clientes da API
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
            
            logger.info("✅ Google Sheets Service inicializado com sucesso")
            
        except Exception as e:
            logger.error(f"❌ Erro ao inicializar Google Service: {e}")
            raise

    @property
    def service_account_email(self) -> str:
        """Retorna o e-mail da service account carregada."""
        try:
            return self.credentials.service_account_email  # type: ignore[attr-defined]
        except Exception:
            return "(service account)"
    
    def list_spreadsheets(self, max_results: int = 100, folder_id: Optional[str] = None, include_excel: bool = False) -> List[Dict[str, Any]]:
        """
        Lista todos os arquivos de planilha do Google Drive acessíveis.
        
        Args:
            max_results: Número máximo de resultados a retornar
            folder_id: ID da pasta do Drive para filtrar planilhas (opcional)
            
        Returns:
            Lista de dicionários com informações das planilhas:
            [
                {
                    "id": "abc123...",
                    "name": "planilha de Satisfação",
                    "webViewLink": "https://docs.google.com/spreadsheets/d/...",
                    "createdTime": "2024-01-15T10:30:00.000Z",
                    "modifiedTime": "2024-10-19T14:20:00.000Z"
                },
                ...
            ]
        """
        try:
            logger.info("📋 Listando planilhas do Google Drive (todas as unidades)...")
            
            # Query para buscar apenas planilhas, não excluídas
            if include_excel:
                base_query = (
                    "(mimeType='application/vnd.google-apps.spreadsheet' "
                    "or mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
                    "or mimeType='application/vnd.ms-excel' "
                    "or mimeType='text/csv') and trashed=false"
                )
            else:
                base_query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
            
            # Se folder_id fornecido, filtra apenas planilhas dessa pasta
            if folder_id:
                base_query += f" and '{folder_id}' in parents"
                logger.info(f"📂 Filtrando planilhas da pasta: {folder_id}")
            
            all_files: List[Dict[str, Any]] = []
            page_token: Optional[str] = None
            fetched = 0
            
            while True:
                page_size = min(200, max_results - fetched) if max_results else 200
                if page_size <= 0:
                    break
                params = {
                    'q': base_query,
                    'pageSize': page_size,
                    'fields': 'nextPageToken, files(id, name, webViewLink, createdTime, modifiedTime, parents, mimeType)',
                    'orderBy': 'modifiedTime desc',
                    'supportsAllDrives': True,
                    'includeItemsFromAllDrives': True,
                    'corpora': 'allDrives',
                }
                if page_token:
                    params['pageToken'] = page_token
                
                results = self.drive_service.files().list(**params).execute()
                files = results.get('files', [])
                all_files.extend(files)
                fetched += len(files)
                page_token = results.get('nextPageToken')
                if not page_token or (max_results and fetched >= max_results):
                    break
            
            logger.info(f"✅ {len(all_files)} planilha(s) encontrada(s)")
            
            return all_files
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.error("❌ Nenhum arquivo encontrado ou sem permissão")
                return []
            elif e.resp.status == 403:
                logger.error("❌ Sem permissão para acessar o Drive. Verifique as permissões da service account")
                raise PermissionError("Sem permissão para acessar o Google Drive")
            else:
                logger.error(f"❌ Erro HTTP ao listar planilhas: {e}")
                raise
                
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao listar planilhas: {e}")
            raise
    
    def get_spreadsheet_info(self, spreadsheet_id: str) -> Dict[str, Any]:
        """
        Obtém informações sobre uma planilha específica.
        
        Args:
            spreadsheet_id: ID da planilha no Google Sheets
            
        Returns:
            Dicionário com informações da planilha:
            {
                "title": "planilha de Satisfação",
                "sheets": [
                    {"title": "Respostas", "sheetId": 0, "rowCount": 150, "columnCount": 10},
                    ...
                ]
            }
        """
        try:
            logger.info(f"📊 Obtendo informações da planilha {spreadsheet_id}...")
            
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            
            info = {
                "title": spreadsheet.get('properties', {}).get('title', 'Sem título'),
                "sheets": []
            }
            
            for sheet in spreadsheet.get('sheets', []):
                props = sheet.get('properties', {})
                info['sheets'].append({
                    "title": props.get('title', 'Sheet1'),
                    "sheetId": props.get('sheetId', 0),
                    "rowCount": props.get('gridProperties', {}).get('rowCount', 0),
                    "columnCount": props.get('gridProperties', {}).get('columnCount', 0)
                })
            
            logger.info(f"✅ Planilha '{info['title']}' com {len(info['sheets'])} aba(s)")
            
            return info
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.error(f"❌ Planilha {spreadsheet_id} não encontrada")
                raise FileNotFoundError(f"Planilha {spreadsheet_id} não encontrada")
            elif e.resp.status == 403:
                logger.error(f"❌ Sem permissão para acessar a planilha {spreadsheet_id}")
                raise PermissionError(f"Sem permissão para acessar a planilha. Compartilhe com a service account.")
            else:
                logger.error(f"❌ Erro HTTP ao obter info da planilha: {e}")
                raise
                
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao obter info: {e}")
            raise
    
    def get_form_responses(
        self, 
        spreadsheet_id: str, 
        sheet_name: Optional[str] = None,
        range_notation: str = "A:Z"
    ) -> List[Dict[str, Any]]:
        """
        Lê as respostas de um planilha (planilha) e retorna como lista de dicionários.
        
        Args:
            spreadsheet_id: ID da planilha no Google Sheets
            sheet_name: Nome da aba (opcional, usa primeira aba se None)
            range_notation: Notação de intervalo (padrão: "A:Z" = todas as colunas A até Z)
            
        Returns:
            Lista de dicionários onde cada dict é uma linha com colunas mapeadas:
            [
                {"Nome": "Ana", "Email": "ana@example.com", "Nota": "10", ...},
                {"Nome": "João", "Email": "joao@example.com", "Nota": "8", ...},
                ...
            ]
        """
        try:
            # Se não especificou a aba, descobre a primeira
            if sheet_name is None:
                info = self.get_spreadsheet_info(spreadsheet_id)
                if not info['sheets']:
                    logger.warning("⚠️ Planilha sem abas")
                    return []
                sheet_name = info['sheets'][0]['title']
            
            range_full = f"'{sheet_name}'!{range_notation}"
            
            logger.info(f"📖 Lendo respostas de {spreadsheet_id} ({range_full})...")
            
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_full
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                logger.info("ℹ️ Nenhum dado encontrado na planilha")
                return []
            
            # Primeira linha é o cabeçalho
            headers = values[0]
            data_rows = values[1:]
            
            # Converte linhas em dicionários
            responses = []
            for row in data_rows:
                # Preenche células vazias para manter alinhamento com cabeçalhos
                row_dict = {}
                for i, header in enumerate(headers):
                    row_dict[header] = row[i] if i < len(row) else ""
                responses.append(row_dict)
            
            logger.info(f"✅ {len(responses)} resposta(s) carregada(s)")
            
            return responses
            
        except HttpError as e:
            if e.resp.status == 404:
                logger.error(f"❌ Planilha ou aba '{sheet_name}' não encontrada")
                raise FileNotFoundError(f"Planilha ou aba '{sheet_name}' não encontrada")
            elif e.resp.status == 403:
                logger.error("❌ Sem permissão para ler a planilha")
                raise PermissionError("Sem permissão para ler a planilha. Compartilhe com a service account.")
            else:
                logger.error(f"❌ Erro HTTP ao ler respostas: {e}")
                raise
                
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao ler respostas: {e}")
            raise

    def convert_excel_to_google_sheet(self, file_id: str, new_title: Optional[str] = None, parent_folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Converte um arquivo Excel (.xlsx) existente no Drive para uma Planilha Google.

        Args:
            file_id: ID do arquivo Excel no Drive
            new_title: Título opcional para a nova planilha Google
            parent_folder_id: Pasta destino opcional

        Returns:
            Dict com { 'id': ..., 'name': ... }
        """
        try:
            body: Dict[str, Any] = {
                'mimeType': 'application/vnd.google-apps.spreadsheet'
            }
            if new_title:
                body['name'] = new_title
            if parent_folder_id:
                body['parents'] = [parent_folder_id]

            created = self.drive_service.files().copy(
                fileId=file_id,
                body=body,
                supportsAllDrives=True,
                fields='id, name'
            ).execute()

            logger.info(f"✅ Arquivo convertido para Google Sheets: {created.get('name')} ({created.get('id')})")
            return created
        except HttpError as e:
            logger.error(f"❌ Erro ao converter arquivo: {e}")
            raise

    def auto_convert_tabular_files(
        self,
        parent_folder_id: Optional[str] = None,
        include_csv: bool = True,
        include_xls: bool = True,
        max_conversions: int = 10,
    ) -> Dict[str, Any]:
        """
        Converte automaticamente arquivos tabulares (CSV/XLS/XLSX) para Google Sheets
        quando ainda não existe uma planilha com o mesmo nome base.

        Returns: { 'converted': int, 'skipped': int }
        """
        try:
            files = self.list_spreadsheets(max_results=500, folder_id=parent_folder_id, include_excel=True)
            google_sheets = [f for f in files if f.get('mimeType') == 'application/vnd.google-apps.spreadsheet']
            others = [f for f in files if f.get('mimeType') != 'application/vnd.google-apps.spreadsheet']

            def base_name(name: str) -> str:
                for ext in ['.xlsx', '.xls', '.csv']:
                    if name.lower().endswith(ext):
                        return name[: -len(ext)].strip()
                return name.strip()

            sheet_names = set(base_name(f.get('name', '')).lower() for f in google_sheets)

            converted = 0
            skipped = 0
            for f in others:
                mt = f.get('mimeType', '')
                if mt == 'text/csv' and not include_csv:
                    skipped += 1
                    continue
                if mt in ('application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') and not include_xls:
                    skipped += 1
                    continue
                bn = base_name(f.get('name', ''))
                if bn.lower() in sheet_names:
                    skipped += 1
                    continue
                # Converte
                created = self.convert_excel_to_google_sheet(f['id'], new_title=bn, parent_folder_id=parent_folder_id)
                sheet_names.add(bn.lower())
                converted += 1
                if max_conversions and converted >= max_conversions:
                    break

            return {'converted': converted, 'skipped': skipped}
        except Exception as e:
            logger.error(f"❌ Erro ao conversão automática: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Erro inesperado ao converter arquivo: {e}")
            raise


# Singleton global para reutilização
_service_instance: Optional[GoogleSheetsService] = None


def get_google_service(credentials_path: Optional[str] = None) -> GoogleSheetsService:
    """
    Retorna instância singleton do GoogleSheetsService.
    
    Args:
        credentials_path: Caminho para credenciais (opcional)
        
    Returns:
        Instância do GoogleSheetsService
    """
    global _service_instance
    
    if _service_instance is None:
        _service_instance = GoogleSheetsService(credentials_path)
    
    return _service_instance

def get_service_account_email() -> str:
    """Convenience para exibir o e-mail da service account na UI."""
    service = get_google_service()
    return service.service_account_email


# Funções de conveniência para uso direto
def list_spreadsheets(max_results: int = 100, folder_id: Optional[str] = None, include_excel: bool = False) -> List[Dict[str, Any]]:
    """Lista planilhas disponíveis, opcionalmente de uma pasta específica"""
    service = get_google_service()
    return service.list_spreadsheets(max_results, folder_id, include_excel)


def get_form_responses(
    spreadsheet_id: str, 
    sheet_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Lê respostas de um planilha/planilha"""
    service = get_google_service()
    return service.get_form_responses(spreadsheet_id, sheet_name)


def get_spreadsheet_info(spreadsheet_id: str) -> Dict[str, Any]:
    """Obtém informações sobre uma planilha"""
    service = get_google_service()
    return service.get_spreadsheet_info(spreadsheet_id)

def convert_excel_to_google_sheet(file_id: str, new_title: Optional[str] = None, parent_folder_id: Optional[str] = None) -> Dict[str, Any]:
    """Wrapper para conversão de Excel em Google Sheets"""
    service = get_google_service()
    return service.convert_excel_to_google_sheet(file_id, new_title, parent_folder_id)

def auto_convert_tabular_files(parent_folder_id: Optional[str] = None, include_csv: bool = True, include_xls: bool = True, max_conversions: int = 10) -> Dict[str, Any]:
    """Wrapper para conversão automática de CSV/XLS(X) em Google Sheets"""
    service = get_google_service()
    return service.auto_convert_tabular_files(parent_folder_id, include_csv, include_xls, max_conversions)
