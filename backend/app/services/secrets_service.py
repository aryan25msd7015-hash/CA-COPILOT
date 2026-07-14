"""AWS Secrets Manager lookup with an environment fallback."""
import json
import os


def get_secret(name: str, default: str = "") -> str:
    local = os.getenv(name)
    if local is not None:
        return local
    region = os.getenv("AWS_REGION")
    if not region:
        return default
    try:
        import boto3

        response = boto3.client("secretsmanager", region_name=region).get_secret_value(SecretId=name)
        value = response.get("SecretString", "")
        try:
            decoded = json.loads(value)
            return str(decoded.get(name, value))
        except json.JSONDecodeError:
            return value
    except Exception:
        return default
