import sys
import logging
from pydactyl import PterodactylClient
import time
import json
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("disk_monitor.log", encoding="utf-8"),
    ],
    force=True,
)

logger = logging.getLogger(__name__)

def load_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        print("Конфигурация успешно загружена")
        return config
    except Exception as e:
        print(f"Ошибка при загрузке конфигурации: {e}")
        sys.exit(1)

config = load_config()
if config:
    API_KEY = config['API_KEY']
    BASE_URL = config['BASE_URL']
    srv_id = config['srv_id']
else:
    sys.exit(1)  # Завершаем программу, если конфигурация отсутствует

api = PterodactylClient(BASE_URL, API_KEY)

def get_disk_limit():
    try:
        server_details = api.client.servers.get_server(srv_id)
        disk_limit_mb = server_details['limits']['disk']
        logger.debug(f"Лимит диска сервера: {disk_limit_mb} MB")
        return disk_limit_mb
    except Exception as e:
        logger.critical(f"Ошибка при получении лимита диска: {e}")
        sys.exit(1)  # Завершаем программу

def get_disk_usage(disk_limit_mb):
    try:
        disk_limit_bytes = disk_limit_mb * 1024 * 1024
        server_stats = api.client.servers.get_server_utilization(srv_id)
        disk_used_bytes = server_stats['resources']['disk_bytes']
        disk_usage_percentage = (disk_used_bytes / disk_limit_bytes) * 100
        logger.debug(f"Использование диска: {disk_usage_percentage:.2f}%")
        return disk_usage_percentage
    except Exception as e:
        logger.critical(f"Ошибка при расчёте использования диска: {e}")
        sys.exit(1)  # Завершаем программу

def delete_files():
    """
    Функция для безопасного удаления указанных файлов на сервере: останавливает сервер -> удаляет файлы -> перезапускает сервер
    """
    files_to_delete = [
        "TTSHubProxy/voices_cache.ldb",
        "TTSHubProxy/voices-cache-log.ld"
    ]

    try:
        logger.info("Останавливаем сервер...")
        api.client.servers.send_power_action(srv_id, "stop")
        time.sleep(10)

        server_details = api.client.servers.get_server(srv_id)
        if server_details['status'] != 'offline':
            logger.error("Сервер не удалось выключить. Отмена удаления файлов.")
            return

        logger.info("Сервер успешно остановлен. Удаляем файлы...")
        
        api.client.servers.files.delete_files(srv_id, files_to_delete)
        logger.info(f"Файлы {', '.join(files_to_delete)} успешно удалены.")

        # Перезапуск сервера
        logger.info("Запускаем сервер...")
        api.client.servers.send_power_action(srv_id, "start")
        time.sleep(10)

        server_details = api.client.servers.get_server(srv_id)
        if server_details['status'] == 'running':
            logger.info("Сервер успешно запущен")
        else:
            logger.error("Сервер не удалось запустить после удаления файлов.")
    except Exception as e:
        logger.error(f"Ошибка при удалении файлов или управлении сервером: {e}")

def check_disk_usage():
    try:
        disk_limit_mb = get_disk_limit()
        disk_usage_percentage = get_disk_usage(disk_limit_mb)

        if disk_usage_percentage > 80:
            print(f"Использование диска: {disk_usage_percentage:.2f}% - внимание! Превышение 80%. Удаляем файлы...")
            delete_files()
        else:
            print(f"Использование диска: {disk_usage_percentage:.2f}% - норма")
    except Exception as e:
        logger.error(f"Критическая ошибка при проверке диска: {e}")
        sys.exit(1)  # Завершаем программу

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_disk_usage, IntervalTrigger(seconds=5))

    scheduler.start()
    print("Планировщик включен. Проверка диска будет выполняться каждый час")

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Планировщик остановлен.")

if __name__ == "__main__":
    start_scheduler()
