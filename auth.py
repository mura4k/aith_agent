import requests

from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"

payload={
  'scope': 'GIGACHAT_API_PERS'
}
headers = {
  'Content-Type': 'application/x-www-form-urlencoded',
  'Accept': 'application/json',
  'RqUID': '6e84deab-ce75-4c92-98e4-c6d895ccde3c',
  'Authorization': 'Basic MDE5Y2FlM2ItYmJjYS03YTcwLWI2OTYtMGIzYmU0NTkxZWZiOjQ3MWZkMzA3LTJjMzQtNDcwMi1hNDM5LTgxZjFhZjJjNDk0NA=='
}

response = requests.request("POST", url, headers=headers, data=payload, verify=False)

print(response.text)