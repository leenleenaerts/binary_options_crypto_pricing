"""
This Python script calculates the probability of a specified cryptocurrency (either 'BTC' or 'ETH') trading at or
above a given strike price (K) on a specific expiration date and time. The script interacts with the Deribit
API to obtain option price data and current cryptocurrency price. It then uses quadratic interpolation to estimate option
prices and ITM probabilities, making predictions for different strike prices and time to expiration. Finally, it prints
the predicted probability and predicted binary option prices to the console.
"""

# Import necessary modules
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from tqdm import tqdm
import scipy as sc
import numpy as np
import matplotlib.pyplot as plt

# Input parameters
coin = "BTC"  # Crypto-currency symbol ('BTC', 'ETH')
K = 28000  # Strike price of the option
expiration_time = datetime(2023, 8, 31, 22)  # Expiration date and time of the option (y, m, d, h)


now = datetime.now()
time_to_expiration = (expiration_time - datetime.now()).total_seconds() / (365*24*60*60) # in years
discount_rate = 0.0525

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
def get_option_data(coin, exp_date):
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

    # Update progress bar
    pbar.update(1)

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
def get_coin_price(msg):
    url = 'https://test.deribit.com/api/v2/public/get_index_price'
    response = requests.post(url, json=msg).json()
    return response["result"]["index_price"]


# Get the current price of the coin
msg = \
    {"jsonrpc": "2.0",
     "method": "public/get_index_price",
     "id": 42,
     "params": {
        "index_name": coin.lower() + "_usd"}
    }

price = get_coin_price(msg)

# Get all option dates for a given currency added to a list
option_names = get_option_name(coin)
# Create a list of expiration_dates
dates = []
for name in option_names:
    date = name.split('-')[1]
    date = datetime.strptime(date, "%d%b%y")
    # Remove double dates
    if date not in dates:
        dates.append(date)

# create a list of time to expirations in seconds
time_to_expirations = []
for date in dates:
    time_to_expirations.append((date + timedelta(hours=2) - now).total_seconds() / (365*24*60*60))

# Initialize progress bar
pbar = tqdm(total=len(dates))

# Calculate predicted probability of being ITM at expiration for all expiration dates and store probabilities in a list
ITM_probabilities = []
for exp_date in dates:
    # Get the option data for the specified coin and expiration date
    price_list = get_option_data(coin, exp_date)

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
    # We create a binary option (call bull spread with an extremely small difference in strike prices: dstrike) paying out $ 1.00 if the coinprice is ATM/ITM at expiration.
    dstrike = price/10000
    predicted_price_at_K = Interpolation(K)
    probability_ITM = ((Interpolation(K - dstrike / 2) - Interpolation(K + dstrike / 2)) / dstrike) * np.exp(time_to_expiration * discount_rate)
    ITM_probabilities.append(probability_ITM)

# Interpolate the option probabilities for different time to expirations using a quadratic interpolation method
Interpolation = sc.interpolate.interp1d(time_to_expirations, ITM_probabilities, kind='quadratic', fill_value='extrapolate')

# Calculate the predicted ITM probability at the given expiration time and strike price
predicted_probability = Interpolation(time_to_expiration)
price_yes = predicted_probability * np.exp(-time_to_expiration * discount_rate)
price_no = np.exp(-discount_rate * time_to_expiration) - price_yes

# Close the progress bar
pbar.close()

# Print the results
print(f"{coin} is currently trading at $ {price:.2f}")
print(f"Probability of {coin} trading on or above {K} on {expiration_time} is {100 * predicted_probability:.2f} %")
print(f"Value of shares : YES - {100 * price_yes:.2f} ¢\n"
      f"                   NO - {100 * price_no:.2f} ¢")

# Plot the predicted ITM probabilities against different expiration dates
plt.title(f"Predicted {coin} Call Option ITM probability at different expiration times")
plt.plot(time_to_expirations, ITM_probabilities, 'ro', ms=3)
min_t = min(time_to_expirations)
max_t = max(time_to_expirations)
range_t = max_t - min_t
values = np.linspace(0, max_t + range_t * 0.2, 100000)
plt.plot(time_to_expiration, predicted_probability, 'go', ms=5)
plt.plot(values, Interpolation(values))
plt.ylabel('ITM probability')
plt.xlabel('time to expiration (years)')
plt.show()
