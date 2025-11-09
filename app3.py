import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
import logging
# from langchain.prompts import PromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')
#-------------------------------------------------------------------------------------------------------------

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
    
def get_report(df,api_key):
    llm =ChatGroq(
       model="meta-llama/llama-4-maverick-17b-128e-instruct",
       temperature=0.1,
       api_key=api_key,
    )

 

    sysytem_prompt = f'''
    Consider yourself as a financial analyst with 15 years of experience in analyzing company financials.
    You are given financial data for a company over the last 8 quarters (e.g., revenue, net income, etc.). Using only this data (no assumptions), generate a clear, professional, and engaging financial narrative report that follows these instructions:

---

### Structure & Content

1. **Executive Summary (100 words exactly)**

   * Summarize key performance trends in revenue and net income.
   * Use simple analogies (e.g., “Revenue is the fuel driving growth”).
   * Capture the arc: past performance, challenges, and what it could imply—without predicting.
   * Present as bullet points or numbered list, totaling exactly 100 words.

2. **Detailed Sections**

   * **Trends & Patterns**

     * Highlight quarter-over-quarter growth, dips, seasonality, or volatility.
     * Cite specific examples, such as “Q3 revenue dipped 12% after three consecutive quarters of gains.”
   * **Explanations & Insights**

     * Offer plausible, data-driven reasons for each trend (e.g., “Rising cost of goods sold reduced Q3 net income”).
     * Clearly label these as observations, not forecasts.
   * **Hidden/Helpful Insights**

     * Point out margin fluctuations (gross margin, net margin).
     * Note any cash flow patterns or free cash flow changes.
     * Identify expense-to-revenue ratios or shifts in operating expenses.
     * Call attention to one-off events (e.g., “Extra marketing spend in Q2 boosted revenue but squeezed margins”).
     * Highlight any seasonality (e.g., “Sales traditionally peak in Q4, which held true here”).


3. **Optional Enhancements** (only if data supports)

   * **Sentiment Notes**: Mention any visible public or market feedback hints, such as a strong product launch correlating with Q2 revenue.
   * **What-If Scenarios**: Show simple calculations, for example:

     1. If revenue grows 10% next quarter and margin stays constant, net income would rise by approximately X%.
     2. Include formula: “New Net Income ≈ Current Net Income × (1 + Revenue Growth)”.

---

### Style & Output Requirements

* Use **plain English** and **professional tone**, but keep language simple.
* Present all content as **bullet points or numbered lists** rather than paragraphs.
* Label each section clearly (e.g., “Executive Summary,” “Trends & Patterns,” etc.).
* If any quarter’s data is missing, insert a bullet saying: “\[QX data not provided].”
* Never assume or predict beyond the provided eight quarters.
* End with the note:

  > “Insights are based only on the provided data and do not represent forecasts.”

---

**Example Outline Format (Detailed Mode)**

* **Executive Summary (100 words)**

  1. Company’s revenue grew steadily from Q1 to Q3, acting like “fuel in the tank.”
  2. In Q4, net income dropped 15% after operating expenses spiked—pausing momentum.
  3. Gross margin expanded from 25% to 28% between Q2 and Q3, then fell to 22% in Q4.
  4. Cash flow remained positive all quarters, though free cash flow dipped in Q4.
  5. Seasonal pattern: Q2 and Q4 are strongest, while Q1 and Q3 lag behind.

* **Trends & Patterns**

  * Q1–Q2 revenue growth: +10%, driven by higher unit sales.
  * Q3 dip: −12% revenue, possibly due to rising raw material costs.
  * Q4 bounce: +8% revenue but net income down due to marketing spend.

* **Explanations & Insights**

  * Operating expenses rose 20% in Q3—likely new hiring or R\&D investment.
  * Gross margin fell in Q4 from 28% to 22%, suggesting price promotions.
  * Net margin stayed above 10% except Q4 (dropped to 6%).

* **Hidden/Helpful Insights**

  * Cash conversion cycle shortened from 60 days (Q1) to 45 days (Q3).
  * Free cash flow positive every quarter; peaked in Q2.
  * R\&D expense ratio increased from 5% (Q1) to 8% (Q4), hinting at future product pipeline.
  * SG\&A as a percentage of revenue: stable at 12% until Q4’s rise to 15%.


* **Optional Enhancements**

  * **Sentiment Notes**: Q2 product launch drove social media buzz, aligning with the 10% revenue jump.
  * **What-If Scenarios**: If revenue grows 10% in Q5, net income ≈ Current Net Income × 1.10.

* **Disclaimers**

  > Insights are based only on the provided data and do not represent forecasts.

    {df}'''

    prompt_template = PromptTemplate(
        input_variables=["question"],
        template=sysytem_prompt + "\n" + "{question}"
    )

    chain = prompt_template|llm|StrOutputParser()

    result = chain.invoke(
        {"question":"Generate Report"}
    )
    return result
    
#--------------------------- Streamlit UI Design ---------------------------#

st.title("📊 COMPANY FINANCIALS")
st.write("🔍 This app takes ticker symbol as input and returns the financial info of the company")
option = st.selectbox("Choose the stock exchange:", ["NASDAQ", "Other"])
st.write("For NASDAQ:- Enter ticker symbol as is (e.g.,TSLA,NVDA)")
st.write("For other:- stockexchange:ticker symbol (e.g. NSE:TATACONSUM,ETR:BMW ) ")
ticker_symbol = st.text_input("Enter the ticker symbol:")
#groq_api_key = st.text_input("Get your Groq API key from https://console.groq.com/home", type="password")

# Check if ticker_symbol is provided
if ticker_symbol: #and groq_api_key:
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
            st.write("Get your Groq API key from https://console.groq.com/home and Click below button to generate report")
            groq_api_key = st.text_input("Enter API Key", type="password")
            if groq_api_key:
                if st.button("Request Report"):
                    report = get_report(stock_info_df, groq_api_key)
                    if report:
                        st.write("---------- Generated Report ----------")
                        st.write(report)
        else:
            st.error("❌ Failed to process the financial data.")
    else:
        st.error("❌ Failed to fetch the financial data.")


