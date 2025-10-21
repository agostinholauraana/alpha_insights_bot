import json
import base64
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)
from logging_config import setup_logging

# garante logging configurado (idempotente)
setup_logging()


def normalize_service_account_json(value: Any) -> Dict:
    """
    Normaliza uma entrada que representa credenciais de service account.

    Aceita:
    - dict -> retorna o dict
    - str contendo JSON cru -> retorna o dict
    - str contendo JSON com "\\n" escapados -> corrige e retorna o dict
    - str contendo base64-encoded JSON -> decodifica e retorna o dict

    Lança ValueError com mensagem explicativa se não conseguir decodificar.
    """
    if isinstance(value, dict):
        logger.debug('normalize_service_account_json: input is already a dict')
        return value

    if not isinstance(value, str):
        raise ValueError("Valor das credenciais deve ser dict ou string JSON/base64")

    # 1) tenta JSON cru
    try:
        logger.debug('normalize_service_account_json: trying raw json load')
        return json.loads(value)
    except Exception:
        logger.debug('normalize_service_account_json: raw json load failed')

    # 2) tenta corrigir escaped-newlines ("\\n")
    try:
        logger.debug('normalize_service_account_json: trying escaped-newlines fix')
        maybe = value.replace('\\n', '\n')
        return json.loads(maybe)
    except Exception:
        logger.debug('normalize_service_account_json: escaped-newlines attempt failed')

    # 3) tenta base64
    try:
        logger.debug('normalize_service_account_json: trying base64 decode')
        # cleanup common issues: whitespace/newlines
        candidate = value.strip().replace('\r', '').replace('\n', '')
        try:
            decoded = base64.b64decode(candidate)
            return json.loads(decoded.decode('utf-8'))
        except Exception as e:
            logger.debug('normalize_service_account_json: base64 first attempt failed: %s', e)
            # Try to auto-fix padding: base64 length must be multiple of 4
            try:
                pad_needed = (-len(candidate)) % 4
                if pad_needed:
                    candidate2 = candidate + ('=' * pad_needed)
                else:
                    candidate2 = candidate
                decoded = base64.b64decode(candidate2)
                logger.info('normalize_service_account_json: auto-fixed base64 padding')
                return json.loads(decoded.decode('utf-8'))
            except Exception as e2:
                logger.debug('normalize_service_account_json: base64 auto-fix failed: %s', e2)
                raise
    except Exception as e:
        logger.debug('normalize_service_account_json: base64 decode failed: %s', e)
        # Log some hints about base64 length/characters
        try:
            ln = len(value)
            logger.debug('normalize_service_account_json: input length=%d', ln)
        except Exception:
            pass

    raise ValueError(
        'GOOGLE_SERVICE_ACCOUNT_JSON não contém JSON válido. Tentadas: raw JSON, escaped-newlines e base64.'
    )
