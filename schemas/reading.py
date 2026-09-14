from db import db
from utils import get_current_utc_time, decrypt_data


# defines the reading model for the database
# encrypted temperature and humidity values, and a timestamp
# includes properties to handle encryption and decryption
class Reading(db.Model):
    __tablename__ = "readings"

    # Primary Key: Unique ID for each database row
    id = db.Column(db.Integer, primary_key=True, index=True)

    # timestamp of when the reading when a row is created
    timestamp = db.Column(db.DateTime(timezone=True), default=get_current_utc_time)

    # Private Database Columns: Store the raw AES ciphertext as strings.
    _temperature = db.Column("temperature", db.String(16), nullable=False)
    _humidity = db.Column("humidity", db.String(16), nullable=False)

    @property
    def temperature(self):
        if self._temperature is None:
            return None
        return decrypt_data(self._temperature)

    @property
    def humidity(self):
        if self._humidity is None:
            return None
        return decrypt_data(self._humidity)

    @temperature.setter
    def temperature(self, value):
        if value is None:
            self._temperature = None
        self._temperature = value

    @humidity.setter
    def humidity(self, value):
        if value is None:
            self._humidity = None
        self._humidity = value
