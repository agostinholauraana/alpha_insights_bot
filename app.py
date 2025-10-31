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
   convert_excel_to_google_sheet
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
       sheets = list_spreadsheets(include_excel=True)
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
           sheets = list_spreadsheets(include_excel=True)
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
           sheets = list_spreadsheets(include_excel=True)
           if not sheets:
               return True, "Nenhuma planilha encontrada no Google Drive."
          
           google_sheets = [s for s in sheets if s.get('mimeType') == 'application/vnd.google-apps.spreadsheet']
           candidate = google_sheets[0] if google_sheets else sheets[0]
           sheet_id = candidate['id']
           sheet_name = candidate['name']
           mime = candidate.get('mimeType')
          
           if mime and mime != 'application/vnd.google-apps.spreadsheet':
               try:
                   converted = convert_excel_to_google_sheet(sheet_id, new_title=f"{sheet_name} (convertido)")
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


<<<<<<< HEAD
# Sidebar com configurações (estilo compacto e moderno)
with st.sidebar:
   # Logo e título (sem emojis)
   st.markdown(
       """
       <div style="text-align: center; padding: 1.25rem 0 1.5rem;">
           <div class="alphy-wrap">
               <div class="alphy-avatar">
                   <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                       <rect x="14" y="18" width="36" height="28" rx="8" fill="#FFFFFF" stroke="#93C5FD"/>
                       <circle cx="26" cy="32" r="4" fill="#2563EB"/>
                       <circle cx="38" cy="32" r="4" fill="#2563EB"/>
                       <rect x="28" y="10" width="8" height="6" rx="2" fill="#3B82F6"/>
                   </svg>
               </div>
           </div>
           <div style="font-size: 1.1rem; font-weight: 600; color: #111827;">Alpha Insights</div>
           <div style="font-size: 0.75rem; color: #6B7280; margin-top: 0.25rem;">Assistente de Análise</div>
       </div>
       """,
       unsafe_allow_html=True,
   )


   st.markdown("---")
  
   # Seção: Ações Rápidas
   st.markdown('<div class="sidebar-title">AÇÕES RÁPIDAS</div>', unsafe_allow_html=True)
  
   col1, col2 = st.columns(2)
   with col1:
       if st.button("Reload", use_container_width=True, key="reload_btn"):
           st.session_state.google_sheets_cache = None
           ctx = get_google_sheets_context()
           # conta planilhas no contexto
           count = ctx.count("(ID:") if ctx else 0
           st.success(f"Atualizado • {count} planilhas")
  
   with col2:
       if st.button("Limpar", use_container_width=True, key="clear_btn"):
           st.session_state.history = []
           st.rerun()
  
   st.markdown("---")
  
   # Seção: Comandos Rápidos
   st.markdown('<div class="sidebar-title">COMANDOS RÁPIDOS</div>', unsafe_allow_html=True)
  
   # Inicializa session state para prefill da entrada
   if 'prefill_command' not in st.session_state:
       st.session_state.prefill_command = None
  
   comandos = [
       "Receita total do mês",
       "Vendas por produto",
       "Relatório de desempenho",
       "Comparar meses",
       "Liste as planilhas disponíveis",
       "Mostre as respostas da planilha"
   ]
  
   for idx, comando in enumerate(comandos):
       if st.button(comando, key=f"cmd_{idx}", use_container_width=True):
           # Preenche o campo de entrada SEM enviar
           st.session_state.prefill_command = comando + " "
           st.session_state.chat_input = st.session_state.prefill_command
           st.rerun()
  
   # Espaçador
   st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
  
   # Contador de mensagens (sem emojis)
   msg_count = len(st.session_state.history)
   st.markdown(
       f"""
       <div style=\"text-align: center; font-size: 0.7rem; color: #9CA3AF; padding: 0.75rem 0;\">{msg_count} mensagens no histórico</div>
       """,
       unsafe_allow_html=True,
   )


# Container do chat (sem header grande)
st.markdown('<div class="chat-container">', unsafe_allow_html=True)


# Exibir histórico do chat
if st.session_state.history:
   for msg in st.session_state.history:
       role = msg["role"]
       content = msg["content"]
      
       if role == "assistant":
           st.markdown(f'''
               <div class="assistant-bubble">
                   <div class="name-chip alphy">Alphy</div>
                   <div style="display: block;">{content}</div>
               </div>
           ''', unsafe_allow_html=True)
       else:
           st.markdown(f'''
               <div class="user-bubble">
                   <div class="name-chip user">Você</div>
                   <div style="display: block;">{content}</div>
               </div>
           ''', unsafe_allow_html=True)
else:
   # Mensagem de boas-vindas
   st.markdown(
       """
       <div style="text-align: center; padding: 3.25rem 2rem 2.5rem;">
           <div class="alphy-wrap" style="justify-content: center; margin-bottom: 0.75rem;">
               <div class="alphy-avatar">
                   <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                       <rect x="14" y="18" width="36" height="28" rx="8" fill="#FFFFFF" stroke="#93C5FD"/>
                       <circle cx="26" cy="32" r="4" fill="#2563EB"/>
                       <circle cx="38" cy="32" r="4" fill="#2563EB"/>
                       <rect x="28" y="10" width="8" height="6" rx="2" fill="#3B82F6"/>
                   </svg>
               </div>
           </div>
           <h2 style="font-weight: 700; color: #1F2937; margin-bottom: 0.5rem; font-size: 1.6rem; letter-spacing: -0.01em;">Olá, eu sou o Alphy!</h2>
           <div class="name-chip alphy" style="margin: 0 auto 0.25rem;">O bot de consulta de planilhas da Alpha Insights</div>
           <p style="font-size: 0.9rem; color: #6B7280; line-height: 1.6; max-width: 520px; margin: 0.25rem auto 0;"></p>
           <p style="font-size: 0.8rem; color: #9CA3AF; margin-top: 0.75rem;">Use os comandos rápidos da sidebar ou digite sua pergunta abaixo.</p>
       </div>
       """,
       unsafe_allow_html=True,
   )


st.markdown('</div>', unsafe_allow_html=True)


# Input do usuário (com key para controlar via session_state)
if st.session_state.get('prefill_command'):
   # Se houve prefill numa iteração anterior, já colocamos em chat_input e limpamos a flag
   st.session_state.prefill_command = None


prompt = st.chat_input("Digite sua mensagem...", key='chat_input')


if prompt:
   # Adiciona mensagem do usuário ao histórico
   st.session_state.history.append({"role": "user", "content": prompt})


   # Exibe mensagem do usuário com novo estilo
   st.markdown(f'''
       <div class="user-bubble">
           <div class="name-chip user">Você</div>
           <div style="display: block;">{prompt}</div>
       </div>
   ''', unsafe_allow_html=True)
  
   # Verifica se é um comando especial
   is_special, special_response = process_special_commands(prompt)
  
   if is_special:
       # Resposta direta do comando especial
       st.session_state.history.append({"role": "assistant", "content": special_response})
       st.markdown(f'''
           <div class="assistant-bubble">
               <div class="name-chip alphy">Alphy</div>
               <div style="display: block;">{special_response}</div>
           </div>
       ''', unsafe_allow_html=True)
       st.rerun()
   else:
       # Prepara contexto com dados das planilhas
       sheets_context = get_google_sheets_context()
      
       system_message = {
           "role": "system",
           "content": f"""Você é Alphy, o assistente de análise de dados da Alpha Insights. Identifique-se como Alphy nas respostas quando fizer sentido.


{sheets_context}


Você tem acesso às planilhas acima e pode ajudar o usuário a:
- Analisar dados
- Responder perguntas sobre as planilhas
- Gerar insights e relatórios
- Processar informações de planilhas


Seja objetivo, profissional e forneça respostas em português brasileiro."""
       }
      
       # Monta histórico de mensagens
       messages = [system_message]
       for h in st.session_state.history[-10:]:  # Últimas 10 mensagens
           messages.append({"role": h["role"], "content": h["content"]})
      
       # Chama a API com streaming
       with st.spinner("Pensando..."):
           response_placeholder = st.empty()
           full_response = ""
          
           try:
               for chunk in call_abacus_streaming(messages):
                   full_response += chunk
                   response_placeholder.markdown(f'''
                       <div class="assistant-bubble">
                           <div class="name-chip alphy">Alphy</div>
                           <div style="display: block;">{full_response}</div>
                       </div>
                   ''', unsafe_allow_html=True)
              
               # Adiciona resposta ao histórico
               st.session_state.history.append({"role": "assistant", "content": full_response})
          
           except Exception as e:
               error_msg = f"Erro ao processar sua mensagem: {str(e)}"
               st.error(error_msg)
               st.session_state.history.append({"role": "assistant", "content": error_msg})


# Rodapé discreto
st.markdown("""
   <div style="text-align: center; padding: 2rem 0 1rem; margin-top: 2rem; border-top: 1px solid #E5E7EB;">
       <div style="font-size: 0.7rem; color: #9CA3AF;">
           Alpha Insights © 2025
       </div>
   </div>
""", unsafe_allow_html=True)




=======
# Sidebar, histórico, chat e lógica de entrada do usuário seguem igual ao código que você enviou
# (o importante é que a parte antiga do drive_service foi removida e substituída pelos wrappers)
>>>>>>> 7248b37 (fix: normalize Google service account JSON, auto-fix base64 padding, add diagnostics & logging)





