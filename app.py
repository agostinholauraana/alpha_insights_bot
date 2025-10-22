import os
import json
from typing import List, Dict
from dotenv import load_dotenv
import streamlit as st
import requests
from google_service_utils import normalize_service_account_json
from logging_config import setup_logging

# Inicializa logging para arquivo/console
setup_logging()

from google_service import (
    list_spreadsheets,
    get_form_responses,
    convert_excel_to_google_sheet,
    auto_convert_tabular_files,
)

# --------- Carregar variáveis de ambiente ---------
load_dotenv()

# Carrega segredos (prioriza st.secrets quando disponível)
def secret_get(key: str, default: str | None = None):
    try:
        return st.secrets.get(key, os.getenv(key, default))  # type: ignore[attr-defined]
    except Exception:
        return os.getenv(key, default)

# Disponibiliza credenciais do Google via env para google_service.py
for _k in ("GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT_FILE"):
    try:
        if _k in st.secrets:  # type: ignore[attr-defined]
            # Se o segredo for um dicionário (objeto JSON), garantir que seja armazenado
            # como uma string JSON válida (não a representação Python de dict).
            val = st.secrets[_k]  # type: ignore[index]
            # Log sem vazar private_key: mostra tipo e tamanho aproximado
            try:
                import logging
                logger = logging.getLogger('app')
                t = type(val).__name__
                s_len = len(json.dumps(val)) if isinstance(val, (dict, str)) else None
                logger.info(f"Setting env var { _k } from st.secrets (type={t}, approx_len={s_len})")
            except Exception:
                pass

            if isinstance(val, dict):
                os.environ[_k] = json.dumps(val, ensure_ascii=False)
            else:
                s = str(val)
                # tentativa automática: se parece base64 mas tamanho não múltiplo de 4, corrige padding
                import re
                if re.fullmatch(r'[A-Za-z0-9+/=\n\r]+', s) and (len(s.strip().replace('\n','').replace('\r','')) % 4) != 0:
                    pad_needed = (-len(s.strip().replace('\n','').replace('\r',''))) % 4
                    s_fixed = s + ('=' * pad_needed)
                    try:
                        # valida com a função de normalização (poderá levantar se inválido)
                        normalize_service_account_json(s_fixed)
                        os.environ[_k] = s_fixed
                        logger = __import__('logging').getLogger('app')
                        logger.info(f'Auto-fixed base64 padding for env var {_k} from st.secrets')
                    except Exception:
                        os.environ[_k] = s
                else:
                    os.environ[_k] = s
    except Exception:
        pass

API_KEY = secret_get("GEMINI_API_KEY") or secret_get("GOOGLE_API_KEY")
DEFAULT_MODEL = secret_get("GEMINI_MODEL", "gemini-2.0-flash-exp")
DEFAULT_TEMPERATURE = float(secret_get("GEMINI_TEMPERATURE", "0.7"))
ABACUS_API_KEY = secret_get("ABACUS_API_KEY")
ABACUS_MODEL = secret_get("ABACUS_MODEL", "gemini-2.0-flash-exp")
ABACUS_URL = "https://routellm.abacus.ai/v1/chat/completions"

# Drive: pasta alvo (opcional) e auto conversão
DRIVE_FOLDER_ID = secret_get("GOOGLE_DRIVE_FOLDER_ID")
AUTO_CONVERT = (secret_get("GOOGLE_AUTO_CONVERT_TABULAR", "true") or "true").strip().lower() == "true"

# --------- Configuração da página ---------
st.set_page_config(
    page_title="Alpha Insights | Assistente de Análise",
    layout="wide",
)

# --------- Inicializar histórico ---------
if "history" not in st.session_state:
    st.session_state.history = []

if "google_sheets_cache" not in st.session_state:
    st.session_state.google_sheets_cache = None

if 'chat_input' not in st.session_state:
    st.session_state.chat_input = ""

# --------- Diagnóstico de credenciais Google (sidebar) ---------
def diagnose_google_credentials():
    """Valida e exibe estado das credenciais do service account sem vazar private_key."""
    secret_val = None
    try:
        if 'GOOGLE_SERVICE_ACCOUNT_JSON' in getattr(st, 'secrets', {}):  # type: ignore[attr-defined]
            secret_val = st.secrets['GOOGLE_SERVICE_ACCOUNT_JSON']  # type: ignore[index]
    except Exception:
        # fallback para env
        secret_val = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')

    # Allow env-only setups
    if secret_val is None:
        secret_val = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')

    with st.sidebar.expander('🔐 Diagnóstico das credenciais Google', expanded=True):
        if not secret_val:
            st.info('Nenhuma credencial encontrada em st.secrets ou variável de ambiente GOOGLE_SERVICE_ACCOUNT_JSON.')
            st.write('Dica: adicione o JSON da service account em `st.secrets` como um objeto JSON ou defina `GOOGLE_SERVICE_ACCOUNT_FILE` apontando para o arquivo .json.')
            return

        # Não exibir a private_key raw. Apenas mostrar chaves de topo e status.
        try:
            info = normalize_service_account_json(secret_val)
            keys = list(info.keys())
            st.success('Credenciais válidas (JSON carregado).')
            st.write('Chaves encontradas:', ', '.join(keys))
            if 'client_email' in info:
                st.write('client_email:', info.get('client_email'))
            if 'project_id' in info:
                st.write('project_id:', info.get('project_id'))
            # Mostrar versão mascarada da private_key se existir
            if 'private_key' in info:
                st.code('private_key: ' + ('***masked***'))
        except ValueError as ve:
            msg = str(ve)
            st.error('Credenciais inválidas: ' + msg)
            # tentativa de detecção simples: pode ser base64 truncado?
            s = str(secret_val)
            import re
            if re.fullmatch(r'[A-Za-z0-9+/=\n\r]+', s) and len(s) % 4 != 0:
                st.warning('A string parece conter apenas caracteres base64, mas o tamanho não é múltiplo de 4 — pode estar truncada.')
            st.write('Soluções sugeridas:')
            st.write('- No Streamlit Cloud: adicione o JSON como objeto em `st.secrets` (recomendado).')
            st.write('- Se estiver usando string JSON, garanta que seja JSON válido (ex.: `json.dumps(seu_dict)`).')
            st.write('- Se estiver usando base64, gere com `base64.b64encode(json.dumps(obj).encode()).decode()` e confirme integridade.')
        except Exception as e:
            st.error('Erro ao validar credenciais: ' + str(e))

# Executa diagnóstico na sidebar
diagnose_google_credentials()

# --------- Funções auxiliares ---------
def get_google_sheets_context() -> str:
    if st.session_state.google_sheets_cache:
        return st.session_state.google_sheets_cache
    
    try:
        # opcionalmente converte arquivos tabulares antes de listar
        if AUTO_CONVERT:
            try:
                auto_convert_tabular_files(parent_folder_id=DRIVE_FOLDER_ID, include_csv=True, include_xls=True, max_conversions=20)
            except Exception as ce:
                st.warning(f"Conversão automática desabilitada: {ce}")

        sheets = list_spreadsheets(include_excel=True, folder_id=DRIVE_FOLDER_ID)
        if not sheets:
            return ""
        
        context = f"\n\n**Planilhas disponíveis no Google Drive:**\n"
        for sheet in sheets[:20]:
            label = ""
            mt = sheet.get('mimeType')
            if mt and mt != 'application/vnd.google-apps.spreadsheet':
                label = " [Excel]"
            context += f"- {sheet['name']}{label} (ID: {sheet['id']})\n"
        
        st.session_state.google_sheets_cache = context
        return context
    except Exception as e:
        st.error(f"Erro ao carregar planilhas do Drive: {e}")
        return ""

def process_special_commands(prompt: str) -> tuple[bool, str]:
    prompt_lower = prompt.lower().strip()
    
    if any(word in prompt_lower for word in ["liste os planilhas", "listar planilhas", "mostrar planilhas", "planilhas disponíveis"]):
        try:
            sheets = list_spreadsheets(include_excel=True, folder_id=DRIVE_FOLDER_ID)
            if not sheets:
                return True, "Nenhuma planilha encontrada no Google Drive."
            
            response = f"**Encontrei {len(sheets)} planilha(s) no Google Drive:**\n\n"
            for i, sheet in enumerate(sheets, 1):
                label = ""
                mt = sheet.get('mimeType')
                if mt and mt != 'application/vnd.google-apps.spreadsheet':
                    label = " [Excel]"
                response += f"{i}. **{sheet['name']}**{label}\n"
                response += f"   - ID: `{sheet['id']}`\n"
                response += f"   - Modificado: {sheet.get('modifiedTime', 'N/A')}\n\n"
            
            st.info(f"Planilhas do Google Drive carregadas - {len(sheets)} encontrada(s)")
            return True, response
        except Exception as e:
            return True, f"Erro ao listar planilhas: {str(e)}"
    
    if "respostas do planilha" in prompt_lower or "respostas da planilha" in prompt_lower:
        try:
            sheets = list_spreadsheets(include_excel=True, folder_id=DRIVE_FOLDER_ID)
            if not sheets:
                return True, "Nenhuma planilha encontrada no Google Drive."
            
            google_sheets = [s for s in sheets if s.get('mimeType') == 'application/vnd.google-apps.spreadsheet']
            candidate = google_sheets[0] if google_sheets else sheets[0]
            sheet_id = candidate['id']
            sheet_name = candidate['name']
            mime = candidate.get('mimeType')
            
            if mime and mime != 'application/vnd.google-apps.spreadsheet':
                try:
                    converted = convert_excel_to_google_sheet(sheet_id, new_title=f"{sheet_name} (convertido)", parent_folder_id=DRIVE_FOLDER_ID)
                    sheet_id = converted['id']
                    sheet_name = converted.get('name', sheet_name)
                except Exception as ce:
                    return True, f"Falha ao converter Excel: {ce}"
            
            responses = get_form_responses(sheet_id)
            
            if not responses:
                return True, f"Nenhuma resposta encontrada na planilha '{sheet_name}'."
            
            response = f"**Respostas do planilha '{sheet_name}':**\n\nTotal de respostas: **{len(responses)}**\n\n"
            for i, resp in enumerate(responses[:3], 1):
                response += f"**Resposta {i}:**\n"
                for key, value in resp.items():
                    response += f"- {key}: {value}\n"
                response += "\n"
            
            if len(responses) > 3:
                response += f"_... e mais {len(responses) - 3} resposta(s)._"
            
            st.success(f"{len(responses)} resposta(s) retornada(s) com sucesso")
            return True, response
        except Exception as e:
            return True, f"Erro ao buscar respostas: {str(e)}"
    
    return False, ""

def call_abacus_streaming(messages: List[Dict[str, str]]):
    headers = {
        "Authorization": f"Bearer {ABACUS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ABACUS_MODEL,
        "messages": messages,
        "temperature": DEFAULT_TEMPERATURE,
        "stream": True,
    }
    
    try:
        response = requests.post(ABACUS_URL, headers=headers, json=payload, stream=True, timeout=60)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue
    except requests.exceptions.RequestException as e:
        yield f"\n\n**Erro na API:** {str(e)}"

# --------- Interface ---------
st.set_page_config(page_title="Alpha Insights", layout="wide")

# Sidebar, histórico, chat e lógica de entrada do usuário seguem igual ao código que você enviou
# (o importante é que a parte antiga do drive_service foi removida e substituída pelos wrappers)
