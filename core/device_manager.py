import sqlite3

class DeviceManager:
    """Manages device information (IMEI, custom names) using an SQLite database."""
    
    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        """Creates the devices table if it doesn't exist."""
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    imei TEXT PRIMARY KEY,
                    custom_name TEXT,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def get_device_name(self, imei):
        """Gets the custom name for a given IMEI."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT custom_name FROM devices WHERE imei = ?", (imei,))
        result = cursor.fetchone()
        return result[0] if result and result[0] else imei

    def set_device_name(self, imei, name):
        """Sets or updates the custom name for a given IMEI."""
        with self._conn:
            self._conn.execute("""
                INSERT INTO devices (imei, custom_name) VALUES (?, ?)
                ON CONFLICT(imei) DO UPDATE SET custom_name = excluded.custom_name
            """, (imei, name))

    def update_last_seen(self, imei):
        """Updates the last seen timestamp for a device."""
        with self._conn:
            self._conn.execute("""
                UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE imei = ?
            """, (imei,))

    def close(self):
        self._conn.close()