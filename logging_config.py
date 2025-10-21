import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: str | None = None, default_level: str = 'INFO') -> None:
    """Configura logging com RotatingFileHandler de forma idempotente.

    Lê variáveis de ambiente opcionais:
    - LOG_FILE: caminho do arquivo de log (default: logs/alpha_insights.log)
    - LOG_LEVEL: nível de log (DEBUG/INFO/WARNING/...)
    """
    if log_file is None:
        log_file = os.getenv('LOG_FILE', 'logs/alpha_insights.log')
    level_name = os.getenv('LOG_LEVEL', default_level).upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger()
    # Se já existe um RotatingFileHandler apontando para o mesmo arquivo, não reconfigura
    for h in logger.handlers:
        try:
            if isinstance(h, RotatingFileHandler) and os.path.abspath(getattr(h, 'baseFilename', '')) == os.path.abspath(log_file):
                return
        except Exception:
            continue

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')

    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(formatter)

    # Console handler também
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)

    logger.setLevel(level)
    logger.addHandler(fh)
    logger.addHandler(ch)
