from sqlalchemy import create_engine
from config.get_config import config_data

print("connecting sys db")
sys_engine = create_engine(config_data['mysql_sys'])
