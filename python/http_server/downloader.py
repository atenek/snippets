#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import itertools
import logging
import os
import shutil
import signal
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Dict, Iterator, List
from urllib.parse import urlparse

import requests


# =========================
# Конфигурация
# =========================

DOWNLOAD_LIST: List[Dict[str, str]] = [
    {
        "url": "http://192.168.208.199:62000/download/Docker_Course.pdf?rate=100000000",
        "md5": "a8c879ee312ef952791982f4a5d508dc",
    },
    {
        "url": "http://192.168.208.199:62000/download/D3_2017.pdf?rate=100000000",
        "md5": "3b07cc4ddaa2d2327f1b6bef93b3e3b2",
    },
    {
        "url": "http://192.168.208.199:62000/download/Plotly.pdf?rate=100000000",
        "md5": "be0541cc438ea46a16a0a762f18552e3",
    },
    {
        "url": "http://192.168.208.199:62000/download/D3.pdf?rate=100000000",
        "md5": "d28c4d3844cc901d2a57e5937c0c727d",
    },
    {
        "url": "http://192.168.208.199:62000/download/Java.pdf?rate=100000000",
        "md5": "54dd6feeaa13ae933f85ee01c1b12403",
    },
]

DOWNLOAD_DIR = Path("./downloads")
LOG_DIR = Path("./logs")

DEBUG_LOG_FILE = LOG_DIR / "debug.log"
WARN_LOG_FILE = LOG_DIR / "warn.log"
ERROR_LOG_FILE = LOG_DIR / "error.log"

MAX_WORKERS = 8

CHUNK_SIZE = 1024 * 1024  # 1 MB
REQUEST_TIMEOUT = (10, 60)
USER_AGENT = "DownloadTester/1.0"
LOG_BACKUP_COUNT = 30

REMOVE_BROKEN_PARTS = True
IDLE_SLEEP_SECONDS = 0.2


# =========================
# Глобальное состояние
# =========================

stop_event = threading.Event()
shutdown_requested = False
session_local = threading.local()


# =========================
# Логирование
# =========================

class ExactLevelFilter(logging.Filter):
    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("download_tester")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    debug_handler = TimedRotatingFileHandler(
        filename=str(DEBUG_LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    debug_handler.suffix = "%Y-%m-%d"
    debug_handler.setFormatter(formatter)
    debug_handler.setLevel(logging.DEBUG)

    warn_handler = TimedRotatingFileHandler(
        filename=str(WARN_LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    warn_handler.suffix = "%Y-%m-%d"
    warn_handler.setFormatter(formatter)
    warn_handler.setLevel(logging.WARNING)
    warn_handler.addFilter(ExactLevelFilter(logging.WARNING))

    error_handler = TimedRotatingFileHandler(
        filename=str(ERROR_LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.suffix = "%Y-%m-%d"
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(ExactLevelFilter(logging.ERROR))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(debug_handler)
    logger.addHandler(warn_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# =========================
# Сигналы
# =========================

def handle_signal(signum, frame) -> None:
    global shutdown_requested
    shutdown_requested = True
    logger.warning("Получен сигнал остановки (%s). Запрошено штатное завершение...", signum)
    stop_event.set()


# =========================
# Утилиты
# =========================

def sanitize_filename(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()
    return safe or "downloaded_file"


def filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    if not name:
        name = "downloaded_file"
    return sanitize_filename(name)


def validate_input(download_list: List[Dict[str, str]]) -> None:
    if not isinstance(download_list, list) or not download_list:
        raise ValueError("DOWNLOAD_LIST должен быть непустым списком словарей")

    for idx, item in enumerate(download_list):
        if not isinstance(item, dict):
            raise ValueError(f"Элемент #{idx} не является словарем")

        if "url" not in item or "md5" not in item:
            raise ValueError(f"Элемент #{idx} должен содержать ключи 'url' и 'md5'")

        if not isinstance(item["url"], str) or not item["url"].strip():
            raise ValueError(f"Элемент #{idx}: некорректный url")

        if not isinstance(item["md5"], str) or len(item["md5"].strip()) != 32:
            raise ValueError(f"Элемент #{idx}: некорректный md5")


def cleanup_download_dir(download_dir: Path) -> None:
    download_dir.mkdir(parents=True, exist_ok=True)

    for entry in download_dir.iterdir():
        try:
            if entry.is_file() or entry.is_symlink():
                entry.unlink()
                logger.info("Удален файл из каталога загрузки при старте: %s", entry)
            elif entry.is_dir():
                shutil.rmtree(entry)
                logger.info("Удален каталог из каталога загрузки при старте: %s", entry)
        except Exception as exc:
            logger.error("Не удалось удалить %s при очистке каталога загрузки: %s", entry, exc)


def detect_unfinished_downloads(download_dir: Path) -> None:
    if not download_dir.exists():
        return

    part_files = list(download_dir.rglob("*.part"))
    if not part_files:
        logger.info("Незавершенные скачивания не обнаружены")
        return

    for part_file in part_files:
        try:
            size = part_file.stat().st_size
        except OSError:
            size = -1

        logger.error(
            "Обнаружено незавершенное скачивание: temp-файл=%s, размер=%s байт",
            part_file,
            size,
        )

        if REMOVE_BROKEN_PARTS:
            try:
                part_file.unlink(missing_ok=True)
                logger.warning("Удален незавершенный temp-файл: %s", part_file)
            except Exception as exc:
                logger.error(
                    "Не удалось удалить незавершенный temp-файл %s: %s",
                    part_file,
                    exc,
                )


def cleanup_temp_file(part_path: Path, task_uuid: str, reason: str, warn_message: str) -> None:
    try:
        part_path.unlink(missing_ok=True)
        logger.warning(
            "task_id=%s | Temp-файл удален %s: %s",
            task_uuid,
            reason,
            part_path,
        )
    except Exception as cleanup_exc:
        logger.error(
            "task_id=%s | Не удалось удалить temp-файл %s: %s",
            task_uuid,
            warn_message,
            cleanup_exc,
        )


def get_thread_session() -> requests.Session:
    if not hasattr(session_local, "session"):
        sess = requests.Session()
        sess.headers.update({"User-Agent": USER_AGENT})
        session_local.session = sess
        logger.info("Инициализирована новая HTTP session для потока")
    return session_local.session


def infinite_item_stream(download_list: List[Dict[str, str]]) -> Iterator[Dict[str, str]]:
    yield from itertools.cycle(download_list)


# =========================
# Основная логика скачивания
# =========================

def download_and_validate(item: Dict[str, str], download_dir: Path) -> bool:
    task_uuid = str(uuid.uuid4())

    url = item["url"]
    expected_md5 = item["md5"].strip().lower()

    filename = filename_from_url(url)
    part_path = download_dir / f"{filename}.{task_uuid}.part"

    logger.info(
        "task_id=%s | Старт скачивания: url=%s -> %s",
        task_uuid,
        url,
        part_path,
    )

    session = get_thread_session()

    try:
        with session.get(url, stream=True, timeout=REQUEST_TIMEOUT) as response:
            response.raise_for_status()

            md5 = hashlib.md5()

            with part_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if stop_event.is_set():
                        logger.warning(
                            "task_id=%s | Скачивание прервано штатной остановкой: url=%s, temp=%s",
                            task_uuid,
                            url,
                            part_path,
                        )
                        cleanup_temp_file(
                            part_path=part_path,
                            task_uuid=task_uuid,
                            reason="после штатной остановки",
                            warn_message="после штатной остановки",
                        )
                        return False

                    if not chunk:
                        continue

                    f.write(chunk)
                    md5.update(chunk)

        actual_md5 = md5.hexdigest().lower()

        if actual_md5 != expected_md5:
            logger.error(
                "task_id=%s | MD5 mismatch: url=%s, файл=%s, expected=%s, actual=%s",
                task_uuid,
                url,
                part_path,
                expected_md5,
                actual_md5,
            )
            cleanup_temp_file(
                part_path=part_path,
                task_uuid=task_uuid,
                reason="после MD5 mismatch",
                warn_message="после MD5 mismatch",
            )
            return False

        logger.info(
            "task_id=%s | Файл успешно скачан и проверен: %s",
            task_uuid,
            part_path,
        )

        try:
            part_path.unlink(missing_ok=True)
            logger.info(
                "task_id=%s | Temp-файл удален после проверки: %s",
                task_uuid,
                part_path,
            )
        except Exception as exc:
            logger.error(
                "task_id=%s | Не удалось удалить temp-файл после проверки: %s",
                task_uuid,
                exc,
            )

        logger.info("task_id=%s | Задача завершена успешно", task_uuid)
        return True

    except requests.RequestException as exc:
        if stop_event.is_set():
            logger.warning(
                "task_id=%s | Сетевая операция прервана из-за штатной остановки: url=%s, error=%s",
                task_uuid,
                url,
                exc,
            )
            cleanup_temp_file(
                part_path=part_path,
                task_uuid=task_uuid,
                reason="после штатной остановки",
                warn_message="после штатной остановки",
            )
            return False

        logger.error(
            "task_id=%s | Ошибка сети при скачивании url=%s: %s",
            task_uuid,
            url,
            exc,
        )
        cleanup_temp_file(
            part_path=part_path,
            task_uuid=task_uuid,
            reason="после сетевой ошибки",
            warn_message="после сетевой ошибки",
        )
        return False

    except Exception as exc:
        if stop_event.is_set():
            logger.warning(
                "task_id=%s | Задача завершена во время штатной остановки: url=%s, error=%s",
                task_uuid,
                url,
                exc,
            )
            cleanup_temp_file(
                part_path=part_path,
                task_uuid=task_uuid,
                reason="после штатной остановки",
                warn_message="после штатной остановки",
            )
            return False

        logger.error(
            "task_id=%s | Ошибка обработки url=%s: %s",
            task_uuid,
            url,
            exc,
        )
        cleanup_temp_file(
            part_path=part_path,
            task_uuid=task_uuid,
            reason="после ошибки",
            warn_message="после ошибки",
        )
        return False


def run_forever(download_list: List[Dict[str, str]], download_dir: Path, max_workers: int) -> None:
    item_iter = infinite_item_stream(download_list)

    total_submitted = 0
    total_success = 0
    total_failed = 0
    total_stopped = 0

    logger.info(
        "Запуск непрерывного режима: постоянное число сессий=%d, URL в пуле=%d",
        max_workers,
        len(download_list),
    )

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dl") as executor:
        futures = set()

        def submit_next() -> None:
            nonlocal total_submitted
            if stop_event.is_set():
                return
            item = next(item_iter)
            future = executor.submit(download_and_validate, item, download_dir)
            futures.add(future)
            total_submitted += 1
            logger.debug("Отправлена новая задача. submitted=%d active=%d", total_submitted, len(futures))

        for _ in range(max_workers):
            submit_next()

        while not stop_event.is_set():
            if not futures:
                logger.warning("Нет активных задач, выполняется повторное заполнение пула")
                for _ in range(max_workers):
                    submit_next()
                time.sleep(IDLE_SLEEP_SECONDS)
                continue

            done, _ = wait(futures, timeout=1.0, return_when=FIRST_COMPLETED)

            if not done:
                continue

            for future in done:
                futures.discard(future)

                try:
                    result = future.result()
                    if result:
                        total_success += 1
                    else:
                        if stop_event.is_set():
                            total_stopped += 1
                        else:
                            total_failed += 1
                except Exception as exc:
                    if stop_event.is_set():
                        total_stopped += 1
                        logger.warning("Задача завершилась во время штатной остановки: %s", exc)
                    else:
                        total_failed += 1
                        logger.error("Неожиданная ошибка в задаче скачивания: %s", exc)

                if not stop_event.is_set():
                    submit_next()

            logger.info(
                "Статистика: submitted=%d, success=%d, failed=%d, stopped=%d, active=%d",
                total_submitted,
                total_success,
                total_failed,
                total_stopped,
                len(futures),
            )

        logger.warning("Ожидание завершения активных задач: %d", len(futures))

        while futures:
            done, _ = wait(futures, timeout=1.0, return_when=FIRST_COMPLETED)
            for future in done:
                futures.discard(future)
                try:
                    result = future.result()
                    if result:
                        total_success += 1
                    else:
                        total_stopped += 1
                except Exception as exc:
                    total_stopped += 1
                    logger.warning("Задача завершилась во время штатной остановки: %s", exc)

    logger.warning(
        "Непрерывный режим остановлен: submitted=%d, success=%d, failed=%d, stopped=%d",
        total_submitted,
        total_success,
        total_failed,
        total_stopped,
    )


def main() -> int:
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        validate_input(DOWNLOAD_LIST)
    except ValueError as exc:
        logger.error("Ошибка конфигурации: %s", exc)
        return 1

    cleanup_download_dir(DOWNLOAD_DIR)

    logger.info("Сервис тестового скачивания запущен")
    logger.info("Каталог загрузки: %s", DOWNLOAD_DIR.resolve())
    logger.info("Debug лог: %s", DEBUG_LOG_FILE.resolve())
    logger.info("Warn лог: %s", WARN_LOG_FILE.resolve())
    logger.info("Error лог: %s", ERROR_LOG_FILE.resolve())
    logger.info("Ротация логов: ежедневно, хранить %d файлов", LOG_BACKUP_COUNT)
    logger.info("Параллельных сессий: %s", MAX_WORKERS)
    logger.info("Файлов в пуле URL: %s", len(DOWNLOAD_LIST))

    run_forever(DOWNLOAD_LIST, DOWNLOAD_DIR, MAX_WORKERS)

    if shutdown_requested:
        logger.info("Штатная остановка завершена, проверка .part как ошибок не выполняется")
    else:
        detect_unfinished_downloads(DOWNLOAD_DIR)

    logger.warning("Сервис остановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main())