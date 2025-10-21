# Alpha Insights – Assistente de Análise (Streamlit)

Um chatbot em PT-BR com UI moderna, integrado ao Google Drive/Sheets (via Service Account) e com backend de IA configurável (Gemini direto ou via Abacus.ai/RouteLLM).

## Recursos
- UI minimalista, responsiva e translúcida (Streamlit)
- Integração com Google Drive/Sheets (lista e lê planilhas, allDrives)
- Suporte a respostas de planilhas (mapeamento por cabeçalhos)
- Chat com histórico, comandos rápidos e streaming de respostas

## Requisitos
- Python 3.10+
- Conta Google Cloud com Service Account e acesso aos arquivos do Drive/Sheets

## Configuração local
1) Copie `.env.example` para `.env` e preencha as variáveis necessárias:
```env
# Gemini (opcional se usar Abacus)
GEMINI_API_KEY=xxxxx
GEMINI_MODEL=gemini-2.5-pro
GEMINI_TEMPERATURE=0.3

# Abacus.ai (opcional; se definido, o app usa Abacus em vez de Gemini SDK)
ABACUS_API_KEY=xxxxx
ABACUS_MODEL=gemini-2.5-pro

# Google Service Account – escolha UMA forma:
# (A) JSON completo (recomendado para deploy)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account", ...}
# (B) Caminho do arquivo local
GOOGLE_SERVICE_ACCOUNT_FILE=keys/alphainsights-bot-analitico-2e700b6f55ae.json
```

2) Instale as dependências e rode:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Como funciona a autenticação do Google
O app procura credenciais nesta ordem:
1. `GOOGLE_SERVICE_ACCOUNT_JSON` (conteúdo JSON)
2. `GOOGLE_SERVICE_ACCOUNT_FILE` (caminho para um arquivo .json)
3. `./keys/<arquivo>.json` (fallback local)

Escopos usados (apenas leitura):
- Drive Readonly: `https://www.googleapis.com/auth/drive.readonly`
- Sheets Readonly: `https://www.googleapis.com/auth/spreadsheets.readonly`

Compartilhe as planilhas/arquivos com o email da Service Account (veja no app ou no JSON: `client_email`).

## Deploy via GitHub + Streamlit Community Cloud
1. Suba este repositório para o seu GitHub (sem `keys/` e sem `.env`, já ignorados pelo `.gitignore`).
2. No Streamlit Cloud, crie um novo app apontando para `app.py` do seu repositório.
3. Em “Secrets”, cole as chaves (exemplo):
```toml
GEMINI_API_KEY = "xxxxx"
GEMINI_MODEL = "gemini-2.5-pro"
GEMINI_TEMPERATURE = "0.3"
ABACUS_API_KEY = "xxxxx" # opcional
ABACUS_MODEL = "gemini-2.5-pro"
GOOGLE_SERVICE_ACCOUNT_JSON = "{\"type\":\"service_account\", ... }"
```
4. Salve e implante. O app inicia automaticamente.

## Deploy alternativo (Render, Railway, etc.)
- Use o mesmo repositório.
- Configure as variáveis de ambiente equivalentes.
- Comando de start: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`

## Observações
- Arquivos Excel/CSV aparecem na listagem, mas a leitura direta é feita para Planilhas Google. Para converter, compartilhe e use a função de conversão no Drive (ou adapte a função `convert_excel_to_google_sheet`, exigirá escopos de escrita).
- Certifique-se de compartilhar os arquivos com a Service Account.
- A UI já está em “wide mode” e com tema configurado em `.streamlit/config.toml`.

## Exemplos recomendados para `secrets.toml` (Streamlit Cloud)

1) Objetos JSON (recomendado — mais seguro e direto):

```toml
[secrets]
GOOGLE_SERVICE_ACCOUNT_JSON = { 
	type = "service_account",
	project_id = "meu-projeto",
	private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
	client_email = "sa@meu-projeto.iam.gserviceaccount.com"
}
```

2) String JSON (use apenas se não puder armazenar como objeto):

```toml
[secrets]
GOOGLE_SERVICE_ACCOUNT_JSON = "{ \"type\": \"service_account\", \"project_id\": \"meu-projeto\", ... }"
```

3) Base64-encoded JSON (último recurso):

```toml
[secrets]
# Gere com: base64.b64encode(json.dumps(obj).encode()).decode()
GOOGLE_SERVICE_ACCOUNT_JSON = "eyAidHlwZSI6ICJzZXJ2aWNlX2FjY291bnQiLCAi..."
```

## Diagnóstico de credenciais

O app exibe um diagnóstico na sidebar que valida o `GOOGLE_SERVICE_ACCOUNT_JSON` sem mostrar a `private_key` em claro. Se houver problemas, a seção oferece dicas (ex.: "parece base64 truncado") e passos para corrigir.

## Logs

Você pode controlar o arquivo e o nível de logs via variáveis de ambiente:

- `LOG_FILE` (opcional) — caminho para o arquivo de log. Default: `logs/alpha_insights.log`
- `LOG_LEVEL` (opcional) — nível de log (DEBUG, INFO, WARNING, ERROR). Default: `INFO`

Exemplo (exportando antes de rodar):

```bash
export LOG_FILE=/tmp/alpha_insights.log
export LOG_LEVEL=DEBUG
streamlit run app.py
```
