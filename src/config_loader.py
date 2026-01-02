import os

def load_config():
    """
    Parses the hawk_settings.conf file present in the expected path.
    Converts numeric strings to floats/ints and comma-separated strings to lists.
    """
    config_data = {}
    # the .conf file is to be put in this specific directory in the deployment system
    config_path = os.path.expanduser('~/.config/Hawk/hawk_settings.conf')

    try:
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    value = value.strip()

                    if "," in value:
                        parts = [v.strip() for v in value.split(",")]
                        parsed = []
                        for v in parts:
                            if v.replace('.', '', 1).replace('-', '', 1).isdigit():
                                parsed.append(float(v) if '.' in v else int(v))
                            else:
                                parsed.append(v)
                        value = parsed
                    elif value.lower() in ("true", "false"):
                        value = value.lower() == "true"
                    else:
                        if value.replace('.', '', 1).isdigit():
                            value = float(value) if '.' in value else int(value)
                    
                    config_data[key.strip()] = value
        return config_data
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

# Singleton instance to be used across the app
CONFIG = load_config()
