from schemas.reading import Reading
from db import db
from typing import List, Tuple, Literal
from datetime import datetime
from sqlalchemy import cast, Float


# functions for creating and reading data from the database

def create(temperature, humidity):
    try:
        new_reading = Reading(
            temperature=temperature,
            humidity=humidity
        )
        db.session.add(new_reading)
        db.session.commit()
        return new_reading

    except Exception as e:
        db.session.rollback()
        print("Error:", e)


def read_latest() -> Tuple[datetime, str, str]:
    try:
        reading = Reading.query.order_by(Reading.timestamp.desc()).first()
        timestamp = reading.timestamp
        temperature = reading.temperature
        humidity = reading.humidity
        return (timestamp, temperature, humidity)
    except Exception as e:
        print("Error:", e)
        return None


def read_all(num_samples=50) -> List[Reading]:
    try:
        readings = Reading.query.order_by(Reading.timestamp.desc()).limit(num_samples).all()
        return readings
    except Exception as e:
        print("Error:", e)
        return None


def read_search(threshold_temperature: float, direction: Literal["above", "below"], start_date: datetime = None, end_date: datetime = None) -> List[Reading]:
    query = Reading.query
    if start_date:
        query = query.filter(Reading.timestamp >= start_date)
    if end_date:
        query = query.filter(Reading.timestamp <= end_date)

    all_readings = query.all()

    try:
        threshold = float(threshold_temperature)
    except (ValueError, TypeError):
        return all_readings  # Return all if threshold is invalid

    if direction == "above":
        return [r for r in all_readings if r.temperature and float(r.temperature) > threshold]
    elif direction == "below":
        return [r for r in all_readings if r.temperature and float(r.temperature) < threshold]
    else:
        raise ValueError(f"direction must be 'above' or 'below'. Value: {direction}")
