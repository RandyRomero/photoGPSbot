import db_connector1
from handle_logs import log

db = db_connector1.DB()
if not db:
    log.warning('Can\'t connect to db.')

query = 'SELECT * FROM photo_queries_table WHERE camera_name="xyz"'
cursor = db.execute_query(query)
print(cursor.rowcount)
