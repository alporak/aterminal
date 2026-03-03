import os
import re

# ---------------------------------------------------------
# CONFIGURATION: ONLY CAPTURE THESE SPECIFIC TAGS
# ---------------------------------------------------------
ALLOWED_TAGS = {
    "ATCMD",
    "MDM.QTL",
    "AT.RSP",
    "MODEM",
    "MODEM.ST",
    "MODEM.ACTION"
}

def clean_logs_filtered():
    current_directory = os.getcwd()
    log_files = [f for f in os.listdir(current_directory) if f.endswith(".log")]

    if not log_files:
        print("No .log files found in this directory.")
        return

    # Regex to capture the TAG (group 1) and the MESSAGE (group 2)
    # It ignores the timestamp garbage at the start
    regex_pattern = re.compile(r"-\[(.*?)\]\s+(.*)")

    for filename in log_files:
        print(f"--- EXTRACTING FROM: {filename} ---")
        
        try:
            with open(filename, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    match = regex_pattern.search(line)
                    if match:
                        tag = match.group(1)
                        msg = match.group(2)
                        
                        # FILTER: Only print if the tag is in our allowed list
                        if tag in ALLOWED_TAGS:
                            print(f"[{tag}] {msg}")
                            
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            
        print(f"--- END OF {filename} ---\n")

if __name__ == "__main__":
    clean_logs_filtered()
    input("Press Enter to close...")