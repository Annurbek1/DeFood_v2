import re
def validate_phone(phone: str) -> bool:
    return bool(re.match(r'^\+?[1-9]\d{1,14}$', phone))

def validate_coordinates(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180