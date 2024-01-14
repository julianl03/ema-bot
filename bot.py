"""
Does not place real orders. Instead, the trades are logged to a JSON file to simulate placing orders.
"""
import json
import requests
import datetime
import time
import discord
import asyncio
from datetime import datetime, timezone, timedelta
import yfinance as yf 

discord_client = discord.Client(intents=discord.Intents.default())

CHANNEL_ID = 0 #DISCORD CHANNEL ID
CMC_API_KEY = "PLACEHOLDER" #CMC api key
DISCORD_TOKEN = "PLACEHOLDER" #Discord bot token
CURRENT_DATE = datetime.now(timezone.utc)
ORDER_SIZE = 50

@discord_client.event

async def on_ready():
    print("SUCCESSFULLY CONNECTED")

def get_prices(ticker, timespan):
	"""
	get_prices uses yahoo finance to obtain price data for a ticker.

	returns closing-price data

	-ticker: the ticker to get historical price data for, type string
	-timespan: the number of days to obtain price data for
	"""
	data = yf.Ticker(ticker).history(period=timespan)
	data = data["Close"]
	
	return data

def load_data(filename):
	"""
	load_data reads and returns JSON data from a file.

	returns file data as JSON

	-filename: name of the file to be opened, type string
	"""

	file = open(filename, "r")
	data = json.load(file)
	file.close()
	
	return data

def calculate_SMA(ticker, sma_type, current_date):
	"""
	calculate_SMA calculates the simple moving average for a ticker based on historical price data.

	returns the sma_type-DAY SMA value (float)

	-ticker: ticker that the SMA should be calculated for, type string
	-sma_type: which SMA should be calculated (e.g. 50-day SMA), type int
	-current_date: the current date, type datetime object
	"""

	prices = get_prices(ticker, str(sma_type+1)+"d")
	day = current_date
	dates = []
	total_price = 0
	print(prices)
	for price in prices:
		total_price = total_price+float(price)
	x_day_SMA = total_price/sma_type

	return x_day_SMA

def calculate_EMA(ticker, ema_type, current_date, smoothing_factor, previous_ema):
	"""
	calculate_EMA calculates the exponential moving average for a ticker based on historical price data.

	returns the ema_type-DAY EMA value (float)

	-ticker: ticker that the EMA should be calculated for, type string
	-ema_type: which SMA should be calculated (e.g. 50-day EMA), type int
	-current_date: the current date, type datetime object
	-smoothing_factor: value to be used for the smoothing factor in the EMA formula, type int
	-previous_EMA: value to be used for the previous EMA value used in the EMA formula, type float
	"""

	prices = get_prices(ticker, str(ema_type+1)+"d")
	current_price = float(prices[current_date.strftime("%Y-%m-%d")])
	x_day_EMA = (current_price*(smoothing_factor/(1+ema_type)))+(previous_ema*(1-(smoothing_factor/(1+ema_type))))

	return x_day_EMA


def calculate_data(ticker, ticker_data):
	"""
	calculate_data is a helper function for the moving-average calculation. If the previous EMA data in the file containing ticker price data is listed as "-1",
	it will perform a SMA calculation instead of an EMA-calculation (as it does not have the previous EMA data).

	returns the 50-day EMA, 200-day EMA, and a boolean indicating if an EMA calculation or SMA calculation was performed (TRUE -> EMA, FALSE -> SMA)

	-ticker: the ticker for which EMA and SMA data is to be calculated for, type string
	-ticker_data: calculuated historical price data for the ticker, type JSON
	"""

	today = CURRENT_DATE.strftime("%d-%m-%y")

	if (ticker_data["50EMA"] == -1 or ticker_data["200EMA"] == -1): #if no previous EMA value available, calculate SMA instead
		ema_50 = calculate_SMA(ticker, 50, CURRENT_DATE)
		ema_200 = calculate_SMA(ticker, 200, CURRENT_DATE)
		return ema_50, ema_200, False
	else:
		ema_50 = calculate_EMA(ticker, 50, CURRENT_DATE, 2, ticker_data["50EMA"])
		ema_200 = calculate_EMA(ticker, 200, CURRENT_DATE, 2, ticker_data["200EMA"])
		return ema_50, ema_200, True

def check_delta(ticker, price_data):
	"""
	check_delta checks for EMA-crossovers, (50-day EMA crossing above or below the 200-day EMA)

	returns a list or None (if a crossover is found, a list in form [ticker, type_of_crossover] is returned)

	-ticker: ticker being checked, type string
	-price_data: MA price data for ticker, type JSON
	"""

	print("CHECKING "+ticker)
	print("PREVIOUS DAY:\n50 EMA: %f\n200 EMA: %f"%(price_data["OLD50EMA"], price_data["OLD200EMA"]))
	print("\nCURRENT DAY:\n50 EMA: %f\n200 EMA: %f\n"%(price_data["50EMA"], price_data["200EMA"]))

	if price_data["OLD50EMA"] - price_data["OLD200EMA"] < 0: #50 ema was below 200 ema
		if price_data["50EMA"] - price_data["200EMA"] > 0:
			return [ticker, "GOLDEN"]
	elif price_data["OLD50EMA"] - price_data["OLD200EMA"] > 0: #50 ema was above 200 ema
		if price_data["50EMA"] - price_data["200EMA"] < 0:
			return [ticker, "DEATH"]
	else:
		return None

	return None

def get_current_price(ticker):
	"""
	Gets the current price for a ticker (using live-quotes from CoinMarketCap)

	returns the current price of ticker (float)

	-ticker: the ticker to obtain live data for, type string
	"""

	url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"

	if ticker[-4:] == "-USD": #if ticker ends in "-USD", remove it
		ticker=ticker[0:3]

	parameters = {'symbol':ticker}
	headers = {'Accepts': 'application/json','X-CMC_PRO_API_KEY': CMC_API_KEY}
	session = requests.Session()
	session.headers.update(headers)
	response = session.get(url, params=parameters)
	data = json.loads(response.text)
	price = data["data"][ticker][0]["quote"]["USD"]["price"]

	return price

def make_trade(trade, active_trades):
	"""
	Opens a trade for ticker. Direction depends on the type of crossover.

	returns trades (data containing active trades), and logs of actions taken

	-trade: trade data, type list [ticker, crossover type]
	-active_trades: trades being made, type JSON
	"""

	#trade form: [ticker, cross-type]
	trades = active_trades
	logs = []

	if trade[1] == "GOLDEN":
		trades[CURRENT_DATE.strftime("%Y-%m-%d")+" "+str(trade[0])] = {"quantity":ORDER_SIZE, "entry":get_current_price(trade[0]), "direction":"BUY"}
		logs.append(("<Opened long position of size "+ str(trades[CURRENT_DATE.strftime("%Y-%m-%d")+" "+str(trade[0])]["quantity"]) + " on $"+ trade[0]).upper()+">")
	else:
		trades[CURRENT_DATE.strftime("%Y-%m-%d")+" "+str(trade[0])] = {"quantity":ORDER_SIZE, "entry":get_current_price(trade[0]), "direction":"SELL"}
		logs.append(("<Opened short position of size "+ str(trades[CURRENT_DATE.strftime("%Y-%m-%d")+" "+str(trade[0])]["quantity"]) + " on $"+ trade[0]).upper()+">")

	return trades, logs

def get_ma_data(ticker, price_data):
	"""
	creates a string containing price information to be shown on discord.

	returns a string

	-ticker: ticker the information is for, type string
	-price_data: price data for ticker, type JSON
	"""

	info = """"""
	info += "\n\nFOR "+ticker.upper()+"\n\n"
	info += "PREVIOUS: \n" + ("50 EMA: %f\t200 EMA: %f"%(price_data["OLD50EMA"], price_data["OLD200EMA"]))
	info += "\n\nCURRENT: \n" + ("50 EMA: %f\t200 EMA: %f\n\n"%(price_data["50EMA"], price_data["200EMA"]))

	return info

def calculate_and_make_trades():
	active_trades = load_data("active_trades.json")
	tickers = load_data("tickers.json")
	activity_log = []
	log_data=[]
	trades_to_make = []
	ma_information = []

	#for every ticker calculate MAs
	for ticker in tickers:
		ema50temp, ema200temp, ema = calculate_data(ticker, tickers[ticker])
		if ema:
			tickers[ticker]["OLD50EMA"], tickers[ticker]["OLD200EMA"] = tickers[ticker]["50EMA"], tickers[ticker]["200EMA"]
			tickers[ticker]["50EMA"], tickers[ticker]["200EMA"] = ema50temp, ema200temp
		else:
			tickers[ticker]["50EMA"], tickers[ticker]["200EMA"], tickers[ticker]["OLD50EMA"], tickers[ticker]["OLD200EMA"] = ema50temp, ema200temp, ema50temp, ema200temp

		tickers[ticker]["date-calculated"] = CURRENT_DATE.strftime("%Y-%m-%d")

	for ticker in tickers:
		print(ticker)
		print(tickers[ticker])
		trade = check_delta(ticker, tickers[ticker]) #check for crossovers
		try:
			ma_information.append(get_ma_data(ticker, tickers[ticker]))
		except Exception as e:
			print(e)
		if trade:
			trades_to_make.append(trade)

	#make trades and log data
	for trade in trades_to_make:
		active_trades, log_data = make_trade(trade, active_trades)
		if len(log_data) >= 1:
			activity_log.append(log_data)

	with open("tickers.json", "w") as file:
		json.dump(tickers, file)
	with open("active_trades.json", "w") as file:
		json.dump(active_trades, file)

	return ma_information, activity_log

async def get_data_in_background():
    """
    Background process for the discord bot, gets data from the api every day and sends messages to a discord channel with calculated data
    any actions the bot makes.
    """

    await discord_client.wait_until_ready()
    channel = discord_client.get_channel(CHANNEL_ID)

    while not discord_client.is_closed():
    	logs = []
    	ma_data=[]

    	try:
    		ma_data, logs = calculate_and_make_trades()
    	except Exception as e:
    		print(e)

    	await channel.send("----------------------------------")
    	await channel.send("["+CURRENT_DATE.strftime("%Y-%m-%d")+"]\n")

    	for ma in ma_data: #show information on discord
    		await channel.send(ma)

    	if len(logs) >= 1:
    		for log in logs:
    			await channel.send(log[0]) #show actions taken on discord
    	else:
    		await channel.send("NO ACTIONS TAKEN TODAY")
    		print("NO ACTIONS TAKEN")
    	await channel.send("[END FOR "+CURRENT_DATE.strftime("%Y-%m-%d")+"]")

    	await asyncio.sleep(86400) #wait 24 hours

async def main():
    async with discord_client:
        discord_client.loop.create_task(get_data_in_background())
        await discord_client.start(DISCORD_TOKEN)

asyncio.run(main())
