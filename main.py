import time
import os
import threading
from cs50 import SQL
from env_vars import DB_NAME
import datetime
from mail_sender import notify


def notification_thread():
    # while True:
    #     now = datetime.datetime.now()
    #     if 1 < now.hour < 2:
    notify()
    quit()
    #     time.sleep(3500)  # 1h


t1 = threading.Thread(target=notification_thread())
t1.start()

os.system("flask run")
