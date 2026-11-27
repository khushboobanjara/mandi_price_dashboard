
import requests

url = "https://api.dharun.dev/v1/mandi"

params = {
    "commodity": "Wheat",
    "state": "Rajasthan",
    "limit": 5
}

try:
    response = requests.get(url, params=params, timeout=20)

    print("HTTP Status:", response.status_code)
    response.raise_for_status()

    result = response.json()
    print("API metadata:")
    print(result.get("meta"))

    print("Response keys:", result.keys())
    print("Records:")
    for record in result.get("data", []):
        print(record)

except requests.exceptions.RequestException as error:
    print("API Error:", error)
