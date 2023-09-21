# Import necessary modules
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
import scipy as sc
import numpy as np


def get_book_summary_by_currency(currency, kind):
    url = "/api/v2/public/get_book_summary_by_currency"
    parameters = {
        'currency': currency,
        'kind': kind,
    }
    # send HTTPS GET request
    api_exchange_address = "https://www.deribit.com"
    json_response = requests.get((api_exchange_address + url + "?"), params=parameters)
    response_dict = json.loads(json_response.content)
    book_summary = response_dict["result"]

    return book_summary


# Function to get a list of call option names for a given coin and expiration time
def get_option_name(coin, expiration_time=None):

    # Request public API to get instrument data
    r = requests.get("https://deribit.com/api/v2/public/get_instruments?currency=" + coin + "&kind=option")
    result = json.loads(r.text)

    # Extract option names
    name = pd.json_normalize(result['result'])['instrument_name']
    name = list(name)

    name_list = []
    # Create a prefix for the option names based on the coin and expiration date
    if expiration_time:
        start = coin + "-" + expiration_time.strftime("%#d%b%y").upper()
        # Filter option names based on the option type and expiration_date
        for option in name:
            if option[-1] == "C" and start in option:
                name_list.append(option)

    # No expiration date given in funtion call
    else:
        for option in name:
                if option[-1] == "C":
                    name_list.append(option)
    return name_list


# Function to get list of option price data for a given coin and list of option names
def get_option_data(coin, exp_date, expiration_time):
    option_name = get_option_name(coin, exp_date)

    # Initialize data frame to store option price data
    coin_df = []

    # Loop to download data for each Option Name
    for i in range(len(option_name)):
        # Download option data -- requests and convert json to pandas
        r = requests.get('https://deribit.com/api/v2/public/get_order_book?instrument_name=' + option_name[i])
        result = json.loads(r.text)
        df = pd.json_normalize(result['result'])

        # Append data to data frame
        coin_df.append(df)

    # Finalize data frame
    coin_df = pd.concat(coin_df)

    # Remove data we don't need
    coin_df = coin_df[["instrument_name", "mark_price"]].copy()

    pricelist = coin_df.values.tolist()
    start = coin + "-" + expiration_time.strftime("%#d%b%y").upper()

    # Extract strike prices from option names and convert them to integers for easier processing
    for pair in pricelist:
        pair[0] = int(pair[0].split('-')[2])

    return pricelist


# Function to get the current price of the coin using the Deribit API
def get_coin_price(coin):
    msg = \
        {"jsonrpc": "2.0",
         "method": "public/get_index_price",
         "id": 42,
         "params": {
             "index_name": coin.lower() + "_usd"}
         }
    url = 'https://test.deribit.com/api/v2/public/get_index_price'
    response = requests.post(url, json=msg).json()
    return response["result"]["index_price"]


def find_probability(coin, expiration_time, strikelist):

    now = datetime.now()
    time_to_expiration = (expiration_time - datetime.now()).total_seconds() / (365 * 24 * 60 * 60)  # in years
    discount_rate = 0.0525

    # Get the current price of the coin
    price = get_coin_price(coin)

    if price == 0:
        print("Error: Unable to fetch the current price from Deribit API.")
        exit()

    book = get_book_summary_by_currency(coin, 'option')
    filtered_book = [{'instrument_name': item['instrument_name'], 'mark_price': item['mark_price']} for item in book]
    # Get all option dates for a given currency added to a list
    option_names = get_option_name(coin)

    # Calculate predicted probability of being ITM at expiration for all expiration dates and store probabilities in a list
    ITM_probabilities = []
    date_string = expiration_time.strftime("%e%b%y").upper()

    strikes, prices = [], []
    # Initialize lists to store relevant strike prices and option prices
    price_list = []
    for item in filtered_book:
        instrument_name = item['instrument_name']
        mark_price = item['mark_price']

        # Check if the target date is part of the instrument name
        if date_string.strip() == instrument_name.split('-')[1] and instrument_name[-1] == 'C':
            # Extract the strike number after the target date
            parts = instrument_name.split('-')
            if len(parts) >= 3:
                strikes.append(int(parts[2]))
                prices.append(mark_price * price)

    # Interpolate the option prices using a quadratic interpolation method
    Interpolation = sc.interpolate.interp1d(strikes, prices, kind='quadratic', fill_value='extrapolate')
    # Calculate the predicted option price at the given strike price and the probability of it expiring ITM
    # We create a binary option (call bull spread with an extremely small difference in strike prices: dstrike) paying out $ 1.00 if the coinprice is ATM/ITM at expiration.
    dstrike = price / 10000
    probs = []
    for strike in strikelist:
        prob = ((Interpolation(strike - dstrike / 2) - Interpolation(strike + dstrike / 2)) / dstrike) * np.exp(time_to_expiration * discount_rate)
        probs.append(prob)
    return price, probs

# Main function
if __name__ == "__main__":
    expiration_time = datetime(2023, 9,22, 2)  # Example expiration time 2 am

    coin = "BTC"  # Example coin
    strikes = [25500, 26000, 26500, 27000, 27500, 28000,28500, 29000]  # Example strike

    price, problist = find_probability(coin, expiration_time, strikes)

    print(f"{coin} | $ {price} | {expiration_time}")
    print("-----------------------")
    for i in range(len(strikes)-1, -1, -1):
        print(f"{strikes[i]} | {problist[i]*100:0.1f} %")
    print("-----------------------")

    for k in range(len(strikes) - 1):
        for j in range(k+1,len(strikes)):
            print(f"{strikes[k]} - {strikes[j]} | {100 * (problist[k] - problist[j]):.2f} %")



    coin = "ETH"  # Example coin
    strikes = [1540,1580, 1620, 1660,1700,1740]  # Example strike

    price, problist = find_probability(coin, expiration_time, strikes)

    print()
    print(f"{coin} | $ {price} | {expiration_time}")
    print("-----------------------")
    for i in range(len(strikes)-1,-1,-1):
        print(f"{strikes[i]} | {problist[i] * 100:0.1f} %")
    print("-----------------------")

    for k in range(len(strikes) - 1):
        for j in range(k + 1, len(strikes)):
            print(f"{strikes[k]} - {strikes[j]} | {100 * (problist[k] - problist[j]):.2f} %")







