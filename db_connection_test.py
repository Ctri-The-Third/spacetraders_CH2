import os
import psycopg2

ST_HOST = os.environ.get("ST_DB_HOST", "localhost")
ST_NAME = os.environ.get("ST_DB_NAME", "spacetraders")
ST_USER = os.environ.get("ST_DB_USER", "spacetraders")
ST_PASS = os.environ.get("ST_DB_PASSWORD", "spacetraders")
ST_PORT = os.environ.get("ST_DB_PORT", "5432")

print(ST_HOST, ST_NAME, ST_USER, ST_PASS, ST_PORT)

# conn = psycopg2.connect(dbname="test", user="postgres", password="secret")
conn = psycopg2.connect(
    dbname=ST_NAME, user=ST_USER, password=ST_PASS, host=ST_HOST, port=ST_PORT
)

cur = conn.cursor()
results = cur.execute("SELECT 1")

print(cur.fetchall())
