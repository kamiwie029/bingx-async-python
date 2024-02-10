import aiohttp 
import asyncio
import time
import hmac
from hashlib import sha256

class BingXStandard:
    restart_limit = 3
    request_blacklist = []

    def __init__(self, api_key, secret_key):
        self.url = "https://open-api.bingx.com"
        self.api_key = api_key
        self.secret_key = secret_key
        self.session = None
    
    async def blacklist_ticker(ticker, time=120):
        BingXStandard.request_blacklist.append(ticker)
        await asyncio.sleep(time)
        BingXStandard.request_blacklist.remove(ticker)

    async def get_query_string(params_dict: dict) -> str:
        sorted_keys = sorted(params_dict)
        params_str = "&".join(["%s=%s" % (param, params_dict[param]) for param in sorted_keys])
        return params_str+"&timestamp="+str(int(time.time() * 1000))

    async def _get_sign(self, api_secret, payload):
        signature = hmac.new(api_secret.encode("utf-8"), payload.encode("utf-8"), digestmod=sha256).hexdigest()
        return signature

    async def send_async_get(self, path, query_str, payload, session):
        url = f"{self.url}{path}?{query_str}&signature={await self._get_sign(self.secret_key, query_str)}"
        headers = {'X-BX-APIKEY': self.api_key,}
        async with session.get(url, headers=headers, data=payload) as response:
            return await response.json()

    async def handle_response_errors(self, response):
        match response["code"]:
            case 100410:
                raise BusyError(f"Encountered a busy error: {response['msg']}\n{response}")
            case 80012:
                raise ServiceUnavailable(f"Encountered a service unavailable error: {response['msg']}\n{response}")
            case _:
                if BingXStandard.restart_limit:
                    BingXStandard.restart_limit -=1
                    raise BusyError(f"Encountered an unknown error: {response['msg']}\n{response}\nRemaining restarts: {BingXStandard.restart_limit+1}")
                else:
                    raise UnknownError(f"Encountered an unknown error: {response['msg']}\n{response}\nRemaining restarts: {BingXStandard.restart_limit} - RAN OUT OF RESTARTS")


    async def get_ticker_price(self, ticker: str, session) -> aiohttp.ClientResponse:
        if ticker in BingXStandard.request_blacklist:
            return
        
        payload = {}
        path = '/openApi/swap/v2/quote/price'
        params_dict = {
            "symbol": ticker
            }
        query_str = await BingXStandard.get_query_string(params_dict)
        response = await self.send_async_get(path, query_str,payload, session)

        if response["code"] != 0:
            try:
                await self.handle_response_errors(response)
            except ServiceUnavailable:
                print(f"Encountered Service Unavailable error for ticker - {ticker}. Adding it to blacklist and will retry in 2 minutes.")
                asyncio.create_task(BingXStandard.blacklist_ticker(ticker, 120))
                response = None

        return response

class ServiceUnavailable(Exception):
    pass

class BusyError(Exception):
    pass

class UnknownError(Exception):
    pass