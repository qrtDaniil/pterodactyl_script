import sys
import logging
from pydactyl import PterodactylClient
import time
import json
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("disk_monitor.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def load_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        logger.info("Конфигурация успешно загружена")
        return config
    except Exception as e:
        logger.critical(f"Ошибка при загрузке конфигурации: {e}")
        sys.exit(1)

config = load_config()
if config:
    API_KEY = config['API_KEY']
    BASE_URL = config['BASE_URL']
    srv_id = config['srv_id']
else:
    sys.exit(1)

api = PterodactylClient(BASE_URL, API_KEY)


def get_disk_limit():
    try:
        server_details = api.client.servers.get_server(srv_id)
        disk_limit_mb = server_details['limits']['disk']
        logger.info(f"Лимит диска сервера: {disk_limit_mb} MB")
        return disk_limit_mb
    except Exception as e:
        logger.critical(f"Ошибка при получении лимита диска: {e}")
        sys.exit(1)


def get_disk_usage(disk_limit_mb):
    try:
        disk_limit_bytes = disk_limit_mb * 1024 * 1024
        server_stats = api.client.servers.get_server_utilization(srv_id)
        disk_used_bytes = server_stats['resources']['disk_bytes']
        disk_usage_percentage = (disk_used_bytes / disk_limit_bytes) * 100
        return disk_usage_percentage
    except Exception as e:
        logger.critical(f"Ошибка при расчёте использования диска: {e}")
        sys.exit(1)


def delete_files():
    folder_to_delete = "TTSHubProxy/tts-cache"

    try:
        logger.info("Останавливаем сервер...")
        api.client.servers.send_power_action(srv_id, "stop")
        time.sleep(10)

        api.client.servers.files.delete_files(srv_id, [folder_to_delete])
        logger.info(f"Папка {folder_to_delete} успешно удалена")
        time.sleep(10)

        logger.info("Запускаем сервер...")
        api.client.servers.send_power_action(srv_id, "start")
        logger.info("Сервер успешно запущен")
    except Exception as e:
        logger.exception(f"Ошибка при выполнении операции с сервером: {e}")


def check_disk_usage():
    try:
        disk_limit_mb = get_disk_limit()
        disk_usage_percentage = get_disk_usage(disk_limit_mb)

        if disk_usage_percentage > 80:
            logger.warning(f"Использование диска: {disk_usage_percentage:.2f}% - внимание! Превышение 80%. Удаляем файлы...")
            delete_files()
        else:
            logger.info(f"Использование диска: {disk_usage_percentage:.2f}% - норма")
    except Exception as e:
        logger.error(f"Критическая ошибка при проверке диска: {e}")
        sys.exit(1)


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_disk_usage, IntervalTrigger(hours=1))

    scheduler.start()
    logger.info("Планировщик включен. Проверка диска будет выполняться каждый час")
    check_disk_usage()

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.warning("Планировщик остановлен")

if __name__ == "__main__":
    start_scheduler()
