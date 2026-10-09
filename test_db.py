from db import get_db_connection
import mysql.connector

connection = None
try:
    connection = get_db_connection()
    print("MySQL connected successfully!")
    cursor = connection.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    for table in tables:
        print(table[0])
    cursor.close()
except mysql.connector.Error as error:
    print("Connection error:", error)
finally:
    if connection and connection.is_connected():
        connection.close()
