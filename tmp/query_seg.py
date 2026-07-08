import paramiko
import sys

host = "mini"
user = "leo"
password = "!Zhao575936"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(host, username=user, password=password)

# Query segment 17 image_prompt for job 29
cmd = """cd /mnt/data/project/video_factory && python3 -c "
import sqlite3, json
conn = sqlite3.connect('data/data.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT id, image_prompt FROM video_segment WHERE job_id=29 AND segment_index=17').fetchone()
if row:
    print('id:', row['id'])
    print('---IMAGE_PROMPT---')
    print(row['image_prompt'])
else:
    print('NOT FOUND')
conn.close()
" """

stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode())
err = stderr.read().decode()
if err:
    print("STDERR:", err, file=sys.stderr)
client.close()
