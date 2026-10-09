import os
import mysql.connector


def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "12345678"),
        database=os.environ.get("DB_NAME", "carpool_db"),
        port=int(os.environ.get("DB_PORT", "3306")),
    )


if __name__ == "__main__":
    connection = None
    try:
        connection = get_db_connection()
        print("MySQL connected successfully!")
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES")
        for row in cursor.fetchall():
            print(row[0])
        cursor.close()
    except mysql.connector.Error as error:
        print("MySQL connection failed:", error)
    finally:
        if connection and connection.is_connected():
            connection.close()
