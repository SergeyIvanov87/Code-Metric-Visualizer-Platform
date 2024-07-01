import sys
import threading
import time

class AsyncExecutor:
    def __init__(self):
        self.async_executor = None

    def __execute__(self, function_to_execute, args):
        function_to_execute(*args)

    def run(self, function_to_execute, args):
        self.async_executor = threading.Thread(target=self.__execute__, args=[function_to_execute, args])
        self.async_executor.start()

    def join(self):
        self.async_executor.join()
