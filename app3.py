import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import logging

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

def get_stock_financials(stock_url):
    """Fetches the financials table and returns a JSON string where the original
    rows become columns and columns become rows."""
    try:
        response = requests.get(stock_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"❌ Error fetching the page: {e}")
        return None

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        stock_table = soup.find('table')
        currency_info=soup.find('div',class_="hidden pb-1 text-sm text-faded lg:block")
        if not stock_table:
            raise ValueError("⚠️ No table found on the webpage.")

        rows = stock_table.find_all("tr")
        if len(rows) < 2:
            raise ValueError("⚠️ Insufficient table data.")

        headers = [th.get_text(strip=True) for th in rows[0].find_all("th")]
        additional_row = [th.get_text(strip=True) for th in rows[1].find_all("th")]
        data = []
        for row in rows[2:]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cells) == len(headers):
                data.append(cells)

        if additional_row:
            data.insert(0, additional_row)

        transposed_data = []
        num_columns = len(headers)
        for col_idx in range(num_columns):
            transposed_row = {
                "Header": headers[col_idx],
                **{f"Row {i+1}": data[i][col_idx] for i in range(len(data))}
            }
            transposed_data.append(transposed_row)

        return json.dumps(transposed_data, indent=2),currency_info
    except Exception as e:
        logging.error(f"⚠️ Error processing table data: {e}")
        return None


def convert_to_dataframe(stock_json):
    """Convert JSON stock data into a Pandas DataFrame."""
    try:
        if not stock_json:
            raise ValueError("⚠️ Input JSON data is empty or None.")
        stock_data = json.loads(stock_json)
        if not isinstance(stock_data, list) or not stock_data:
            raise ValueError("⚠️ Invalid JSON format.")
        return pd.DataFrame(stock_data)
    except (json.JSONDecodeError, ValueError) as e:
        logging.error(f"⚠️ Error decoding JSON: {e}")
        return None


def processed_dataframe(stock_json,columns):
    """Processes stock data into a structured Pandas DataFrame."""
    try:
        stock_info_df = convert_to_dataframe(stock_json)
        if stock_info_df is None or stock_info_df.empty:
            raise ValueError("⚠️ DataFrame is empty or invalid.")
        
        stock_info_df.columns = stock_info_df.iloc[0]
        stock_info_df = stock_info_df[1:].reset_index(drop=True)

        required_columns = ['Fiscal Quarter', 'Period Ending', 'Revenue', 'Net Income'] + columns
        missing_cols = [col for col in required_columns if col not in stock_info_df.columns]
        if missing_cols:
            raise ValueError(f"⚠️ Missing expected columns: {missing_cols}")

        stock_info_df = stock_info_df[required_columns]
        
        stock_info_df['Year'] = stock_info_df['Fiscal Quarter'].str.extract(r'(\d{4})').fillna(0).astype(int)
        stock_info_df['Quarter'] = 'Q' + stock_info_df['Fiscal Quarter'].str.extract(r'(?:Q)?(\d)').fillna(0).astype(int).astype(str)
        stock_info_df.drop(columns=['Fiscal Quarter'], inplace=True)
        
        def clean_date(date_string):
            if not isinstance(date_string, str):
                return None
            if "'" in date_string:
                date_string = date_string.split("'")[-1]
            return pd.to_datetime(date_string.strip(), errors='coerce').date()
        
        stock_info_df['Period Ending'] = stock_info_df['Period Ending'].apply(clean_date)
        stock_info_df = stock_info_df.iloc[:8].reset_index(drop=True)
        
        return stock_info_df
    except Exception as e:
        logging.error(f"⚠️ Error processing DataFrame: {e}")
        return None
    
#--------------------------- Streamlit UI Design ---------------------------#

st.title("📊 COMPANY FINANCIALS")
st.write("🔍 This app takes ticker symbol as input and returns the financial info of the company")
option = st.selectbox("Choose the stock exchange:", ["NASDAQ", "Other"])
st.write("For NASDAQ:- Enter ticker symbol as is (e.g.,TSLA,NVDA)")
st.write("For other:- stockexchange:ticker symbol (e.g. NSE:TATACONSUM,ETR:BMW ) ")
ticker_symbol = st.text_input("Enter the ticker symbol:")

# Check if ticker_symbol is provided
if ticker_symbol:
    if option == "Other":
        if ":" in ticker_symbol:
            # Split the prefix and the rest of the ticker symbol
            prefix, value = ticker_symbol.split(":", 1)
            # Convert prefix to lowercase
            ticker_symbol = f"{prefix.lower()}/{value}"
            stock_url = f"https://stockanalysis.com/quote/{ticker_symbol}/financials/?p=quarterly"
        else:
            stock_url = f"https://stockanalysis.com/stocks/{ticker_symbol}/financials/?p=quarterly"
    elif option == "NASDAQ":
        ticker_symbol=ticker_symbol.lower()
        stock_url = f"https://stockanalysis.com/stocks/{ticker_symbol}/financials/?p=quarterly"

    stock_info,currency_info = get_stock_financials(stock_url)
    if stock_info:
        #columns = st.multiselect("Select the additional data you need:",)
        exclude_values = {'Fiscal Quarter', 'Period Ending', 'Revenue', 'Net Income'}
        stock_json = json.loads(stock_info)
        columns_names = [value for value in stock_json[0].values() if value not in exclude_values]
        columns = st.multiselect("Select additional data:", options=columns_names)
        stock_info_df = processed_dataframe(stock_info,columns)
        if stock_info_df is not None:
            st.write("✅ Financial Data Successfully Retrieved!")
            st.write(f"{currency_info.text}")
            st.dataframe(stock_info_df.style.set_properties(**{'background-color': '#f4f4f4', 'color': '#333', 'border': '1px solid #ddd'}))
        else:
            st.error("❌ Failed to process the financial data.")
    else:
        st.error("❌ Failed to fetch the financial data.")

