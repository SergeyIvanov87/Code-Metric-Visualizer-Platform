from datetime import datetime

def get_timestamp():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]
