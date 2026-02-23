# modules/gps_codes.py

REASON_MAP = {
    0:  ("Signal Quality Low", "Receiver flagged signal as weak/invalid."),
    1:  ("Bad Latitude", "Lat outside valid range (-90 to 90)."),
    2:  ("Bad Longitude", "Lon outside valid range (-180 to 180)."),
    3:  ("Bad Speed", "Speed exceeds max limits (Drift/Jump)."),
    4:  ("Bad Angle", "Heading angle invalid."),
    5:  ("Bad HDOP", "HDOP too high (Urban Canyon effect)."),
    6:  ("Speed Filter Jump", "Impossible acceleration detected."),
    7:  ("Abnormal Speed", "App logic flagged speed as inconsistent."),
    8:  ("GPS Off / Forced", "GPS manually requested OFF or Sleep mode."),
    9:  ("RMC Status Invalid", "NMEA RMC status is 'V' (Void)."),
    10: ("Minimum Satellites", "Sats in use < MINSAT (4)."),
    11: ("Precision Error", "PDOP/HDOP are exactly 0.0 (Warm-up)."),
    12: ("NaN Latitude", "Latitude is Not a Number."),
    13: ("NaN Longitude", "Longitude is Not a Number."),
    14: ("LPM Filtered", "Low Power Mode logic ignored fix."),
    15: ("Abnormal Altitude", "Altitude jumped drastically.")
}

def decode_reason(code):
    """Returns a list of short reason strings for a given integer code."""
    if code is None: return []
    reasons = []
    # If code is 0, it usually means no error *flags*, but if Fix=0, it's just searching.
    if code == 0: return ["Searching / No Error Flags"]
    
    for bit, (short_desc, _) in REASON_MAP.items():
        if code & (1 << bit):
            reasons.append(short_desc)
    return reasons

#add running this function isolately , with asking for code input from user

if __name__ == "__main__":
    while True:
        try:
            user_input = input("Enter an integer code to decode (or 'exit' to quit): ")
            if user_input.lower() == 'exit':
                print("Exiting.")
                break
            code = int(user_input)
            reasons = decode_reason(code)
            print(f"Decoded Reasons for code {code}: {', '.join(reasons) if reasons else 'None'}")
        except ValueError:
            print("Invalid input. Please enter a valid integer code or 'exit'.")