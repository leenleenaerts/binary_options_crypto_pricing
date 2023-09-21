'''
This Python script calculates the predicted price and the probability of a specified cryptocurrency call option (either 'BTC' or 'ETH')
trading at or above a given strike price (K) on a specific expiration date and time. The script interacts with the Deribit API
to obtain option price data and the current cryptocurrency price. It then uses quadratic interpolation to estimate option prices
and implied ITM probabilities based on available market data. Finally, it prints the predicted regular call option price, implied ITM probability
and predicted prices of binary options to the console and plots the predicted option prices against different strike prices for visualization.
'''

# Import necessary modules
import json
import requests
import pandas as pd
from datetime import datetime
from tqdm import tqdm
import scipy as sc
import numpy as np
import matplotlib.pyplot as plt

# Input parameters
coin = "ETH" # Crypto-currency symbol ('BTC', 'ETH')
K = 1700 # Strike price of the option
expiration_time = datetime(2023, 8, 25, 10) # Expiration date and time of the option (y, m, d, h)

discount_rate = 0.0525
time_to_expiration = (expiration_time - datetime.now()).total_seconds() / (365*24*60*60) # in years

# Function to get a list of option names for a given coin and expiration time
def get_option_name(coin, expiration_time, type):
    # Request public API to get instrument data
    r = requests.get("https://deribit.com/api/v2/public/get_instruments?currency=" + coin + "&kind=option")
    result = json.loads(r.text)

    # Extract option names
    name = pd.json_normalize(result['result'])['instrument_name']
    name = list(name)

    # Create a prefix for the option names based on the coin and expiration date
    start = coin + "-" + expiration_time.strftime("%#d%b%y").upper()

    name_list = []
    # Filter option names based on the option type (call or put)
    if type == "call":
        for option in name:
            if option[-1] == "C" and start in option:
                name_list.append(option)
    else:
        for option in name:
            if option[-1] == "P" and start in option:
                name_list.append(option)

    return name_list

# Function to get option price data for a given coin and list of option names
def get_option_data(coin, name_list):
    # Initialize data frame to store option price data
    coin_df = []

    # Loop to download data for each Option Name
    for i in range(len(name_list)):
        # Download option data -- requests and convert json to pandas
        r = requests.get('https://deribit.com/api/v2/public/get_order_book?instrument_name=' + name_list[i])
        result = json.loads(r.text)
        df = pd.json_normalize(result['result'])

        # Append data to data frame
        coin_df.append(df)

    # Finalize data frame
    coin_df = pd.concat(coin_df)

    # Remove data we don't need
    coin_df = coin_df[["instrument_name", "mark_price"]].copy()

    price_list = coin_df.values.tolist()
    start = coin + "-" + expiration_time.strftime("%#d%b%y").upper()

    # Extract strike prices from option names and convert them to integers for easier processing
    for pair in price_list:
        pair[0] = int(pair[0].split('-')[2])

    return price_list

# Function to get the current price of the coin using the Deribit API
def get_coin_price(msg):
    url = 'https://test.deribit.com/api/v2/public/get_index_price'
    response = requests.post(url, json=msg).json()
    return response["result"]["index_price"]

# Get the current price of the coin
msg = {
    "jsonrpc": "2.0",
    "method": "public/get_index_price",
    "id": 42,
    "params": {
        "index_name": coin.lower() + "_usd"
    }
}

while True:
    price = get_coin_price(msg)

    # Get the option data for the specified coin and expiration date
    option_names = get_option_name(coin, expiration_time, "call")
    price_list = get_option_data(coin, option_names)

    # Initialize lists to store relevant strike prices and option prices
    strikes, prices = [], []

    # Filter and collect data for strike prices within 70% to 130% of the goal strike price
    for pair in price_list:
        if K * 0.7 <= pair[0] <= K * 1.3:
            strikes.append(pair[0])
            prices.append(pair[1] * price)

    # Interpolate the option prices using a quadratic interpolation method
    Interpolation = sc.interpolate.interp1d(strikes, prices, kind='quadratic', fill_value='extrapolate')

    # Calculate the predicted option price at the given strike price and the probability of it expiring ITM
    # We create a binary option (call bull spread with an extremely small difference in strike prices: dstrike)
    # paying out $ 1.00 if the coin price is ATM/ITM at expiration.
    dstrike = price / 10000
    predicted_price_at_K = Interpolation(K)
    price_yes = ((Interpolation(K - dstrike / 2) - Interpolation(K + dstrike / 2)) / dstrike)
    probability_ITM = price_yes * np.exp(time_to_expiration * discount_rate)
    price_no = np.exp(-discount_rate * time_to_expiration) - price_yes

    # Print the results
    print(f"ETH-AUG25        {100 * probability_ITM:.2f} %")
