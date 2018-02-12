#!python3
# -*- coding: utf-8 -*-

import json
import db_connector

with open('tag_table.json', 'r') as json_file:
    tag_dict = json.load(json_file)

print(tag_dict)

db = db_connector.connect()
cursor = db.cursor()

print('Start to transfer tags...')
for k, v in tag_dict.items():
    query = 'INSERT INTO tag_table (wrong_tag, right_tag) VALUES ("{}", "{}");'.format(k, v)
    cursor.execute(query)
db.commit()
db_connector.disconnect()
print('Done.')

