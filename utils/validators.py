import re

def validate_pan(pan: str) -> bool:
    if not pan:
        return True # Optional field
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
    return bool(re.match(pattern, pan.upper()))

def validate_status(status: str) -> bool:
    return status in ['ACTIVE', 'INACTIVE', 'BLOCKED']
