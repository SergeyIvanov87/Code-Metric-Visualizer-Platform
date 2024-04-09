import os

class Settings:
    def __init__(self):
        self.work_dir = os.getenv('WORK_DIR', '')
        self.project_dir = os.getenv('INITIAL_PROJECT_LOCATION', '')
        self.api_dir = os.getenv('SHARED_API_DIR', '')
        self.domain_name_api_entry = os.getenv('MAIN_SERVICE_NAME', '')
