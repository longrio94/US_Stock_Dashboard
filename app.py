import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
from google import genai
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import feedparser
from dateutil import parser as date_parser
import json
import os
import time

# --- Config & Setup ---
PORTFOLIO_FILE = "portfolio.json"
analyzer = SentimentIntensityAnalyzer()

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f)

@st.cache_data(ttl=1800)
def get_recent_news(ticker_symbol, days=10):
    url = f"https://news.google.com/rss/search?q={ticker_symbol}+stock+when:{days}d&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    news_items = []
    for entry in feed.entries[:15]:
        try: pub_date = date_parser.parse(entry.published).strftime('%Y-%m-%d %H:%M')
        except: pub_date = "Unknown Date"
        news_items.append({
            'title': entry.title,
            'publisher': entry.source.title if hasattr(entry, 'source') else 'Google News',
            'link': entry.link, 'published': pub_date
        })
    return news_items

def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=window-1, adjust=False).mean()
    ema_down = down.ewm(com=window-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

def calculate_macd(data, fast=12, slow=26, signal=9):
    exp1 = data['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = data['Close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

# --- CACHED DATA FETCHERS TO PREVENT RATE LIMITING ---

@st.cache_data(ttl=1800)
def get_deep_dive_data(ticker_symbol):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)
    df = yf.download(ticker_symbol, start=start_date, end=end_date, progress=False)
    if df.empty: return None, None, None
    if isinstance(df.columns, pd.MultiIndex): df.columns = [col[0] for col in df.columns]

    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    df['RSI_14'] = calculate_rsi(df)
    df['MACD_12_26_9'], df['MACDs_12_26_9'] = calculate_macd(df)
    
    stock = yf.Ticker(ticker_symbol)
    try: info = stock.info
    except: info = {}
    news = get_recent_news(ticker_symbol, days=10)
    return df, news, info

@st.cache_data(ttl=900)
def get_portfolio_prices(tickers):
    if not tickers: return pd.DataFrame()
    return yf.download(tickers, period="1d", group_by='ticker', progress=False)

@st.cache_data(ttl=3600)
def get_risk_historical_data(tickers):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    spy_data = yf.download("SPY", start=start_date, end=end_date, progress=False)['Close']
    if isinstance(spy_data, pd.DataFrame): spy_data = spy_data.iloc[:, 0]
    
    if not tickers: return spy_data, pd.DataFrame()
    port_data = yf.download(tickers, start=start_date, end=end_date, progress=False)['Close']
    return spy_data, port_data

@st.cache_data(ttl=86400)
def get_company_sector(ticker_symbol):
    try:
        time.sleep(0.5) 
        return yf.Ticker(ticker_symbol).info.get('sector', 'Unknown')
    except:
        return 'Unknown'


# --- App Initialization ---
st.set_page_config(page_title="Moon Mission Control", layout="wide", page_icon="🚀")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.title("🚀 Moon Mission Control")
        st.markdown("#### *Hello beautiful astronauts, get your 1-way ticket to the Moon 🌕*")
        st.markdown("Please log in to access the launchpad.")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Ignite Engines 🚀")
            if submitted:
                if username.strip().lower() == "halorio" and password.strip() == "admin123":
                    st.session_state['logged_in'] = True
                    st.rerun()
                else:
                    st.error("Invalid launch codes.")
    st.stop()

# --- Sidebar ---
st.sidebar.title("Mission Config 🪐")
st.sidebar.markdown("##### *Hello beautiful astronauts, get your 1-way ticket to the Moon! 🚀*")
ticker = st.sidebar.text_input("Target Asteroid (Ticker e.g., AAPL)", "AAPL").upper()
st.sidebar.markdown("---")
if st.sidebar.button("Abort Mission (Logout)"):
    st.session_state['logged_in'] = False
    st.rerun()

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["🔭 Telescope (Deep Dive)", "💎 Diamond Hands (Portfolio)", "🛡️ Asteroid Defense (Risk)"])

# ==============================================================================
# TAB 1: DEEP DIVE ANALYSIS
# ==============================================================================
with tab1:
    try:
        data, recent_news, company_info = get_deep_dive_data(ticker)
    except Exception as e:
        st.error("⚠️ YFinance Rate Limit Hit! Yahoo Finance has temporarily blocked your IP for making too many requests. Please wait a few minutes before trying again.")
        data, recent_news, company_info = None, None, None

    if data is not None and not data.empty:
        if company_info:
            long_name = company_info.get('longName', ticker)
            exchange = company_info.get('exchange', 'Unknown Exchange')
            summary = company_info.get('longBusinessSummary', 'No background information available.')
            st.title(f"{long_name} ({ticker}) - {exchange}")
            with st.expander("Company Background"): st.write(summary)
        else:
            long_name = ticker
            st.title(f"Deep Dive Analysis: {ticker}")

        latest = data.iloc[-1]
        prev = data.iloc[-2]
        current_price = float(latest['Close'])
        prev_price = float(prev['Close'])
        price_change = current_price - prev_price
        pct_change = (price_change / prev_price) * 100
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Current Price", f"${current_price:.2f}", f"{price_change:.2f} ({pct_change:.2f}%)")
        rsi_val = float(latest.get('RSI_14', 0))
        col2.metric("RSI (14)", f"{rsi_val:.2f}", "Overbought (>70) / Oversold (<30)", delta_color="off")
        macd_val = float(latest.get('MACD_12_26_9', 0))
        macd_sig = float(latest.get('MACDs_12_26_9', 0))
        col3.metric("MACD", f"{macd_val:.3f}", f"Signal: {macd_sig:.3f}", delta_color="normal" if macd_val > macd_sig else "inverse")
        sma50 = float(latest.get('SMA_50', 0))
        sma200 = float(latest.get('SMA_200', 0))
        col4.metric("SMA 50 / SMA 200", f"${sma50:.2f} / ${sma200:.2f}", "Golden Cross" if sma50 > sma200 else "Death Cross", delta_color="normal" if sma50 > sma200 else "inverse")
                    
        st.markdown("---")
        chart_col, news_col = st.columns([2, 1])
        with chart_col:
            st.subheader("Historical Price, Volume & Regimes")
            chart_data = data.tail(252)
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.2, 0.7])
            fig.add_trace(go.Candlestick(x=chart_data.index, open=chart_data['Open'], high=chart_data['High'], low=chart_data['Low'], close=chart_data['Close'], name='Price'), row=1, col=1)
            
            if 'SMA_50' in chart_data.columns: fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['SMA_50'], line=dict(color='blue', width=1.5), name='SMA 50'), row=1, col=1)
            if 'SMA_200' in chart_data.columns: fig.add_trace(go.Scatter(x=chart_data.index, y=chart_data['SMA_200'], line=dict(color='red', width=1.5), name='SMA 200'), row=1, col=1)
            
            if 'Volume' in chart_data.columns:
                colors = ['green' if row['Close'] >= row['Open'] else 'red' for index, row in chart_data.iterrows()]
                fig.add_trace(go.Bar(x=chart_data.index, y=chart_data['Volume'], marker_color=colors, name='Volume'), row=2, col=1)
            
            fig.update_layout(template='plotly_dark', height=650, margin=dict(l=0, r=0, t=10, b=0), hovermode='x unified', xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with news_col:
            st.subheader("10-Day News Crawl")
            news_text = ""
            if recent_news:
                with st.container(height=650, border=True):
                    for n in recent_news:
                        title, publisher, link, published = n.get('title',''), n.get('publisher',''), n.get('link','#'), n.get('published','')
                        compound = analyzer.polarity_scores(title)['compound']
                        if compound >= 0.05: sentiment = "🟢 Positive"
                        elif compound <= -0.05: sentiment = "🔴 Negative"
                        else: sentiment = "⚪ Neutral"
                        news_text += f"- [{published}] {title} ({publisher}) - Sentiment: {sentiment}\n"
                        st.markdown(f"**[{title}]({link})**")
                        st.caption(f"*{publisher}* • {published} • {sentiment}")
                        st.divider()
            else:
                st.write("No recent news found.")
                
        st.markdown("---")
        st.subheader("🤖 AI News-Driven Insights")
        
        try: api_key = st.secrets["GEMINI_API_KEY"]
        except: api_key = None
            
        if not api_key or api_key == "your_api_key_here":
            st.warning("Google Gemini API Key is missing in `.streamlit/secrets.toml`.")
        else:
            if st.button("Generate Deep Dive & Insights", type="primary"):
                with st.spinner("Synthesizing 10-day news narrative..."):
                    try:
                        prompt = f"""
                        You are an expert fundamental and growth stock analyst. Synthesize the recent news narrative over the last 10 days for {ticker} ({long_name}) and extract actionable insights. Focus heavily on fundamental news and catalysts.
                        
                        RECENT 10-DAY NEWS HEADLINES:
                        {news_text}
                        
                        TECHNICAL CONTEXT:
                        - Price: ${current_price:.2f}
                        - 50 SMA: ${sma50:.2f} | 200 SMA: ${sma200:.2f} | RSI: {rsi_val:.2f}
                        
                        Provide:
                        1. **The 10-Day Narrative**: Synthesis of news themes.
                        2. **Business Catalyst & Sentiment Shift**: Impact on market sentiment.
                        3. **Growth Expectation & Verdict**: Aggressive growth forecast and Buy/Hold/Sell verdict.
                        """
                        client = genai.Client(api_key=api_key)
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                                st.markdown(response.text)
                                break
                            except Exception as e:
                                if "503" in str(e) and attempt < max_retries - 1:
                                    time.sleep(2 ** attempt)  # Wait 1s, then 2s before retrying
                                    continue
                                else:
                                    st.error(f"⚠️ Google Gemini API Error: The AI model is currently experiencing high demand. Please wait a moment and try again.\n\nDetails: {str(e)}")
                                    break
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    else:
        st.warning("Data not found or Yahoo Finance Rate Limit active. Please try again later.")


# ==============================================================================
# TAB 2: MY PORTFOLIO
# ==============================================================================
with tab2:
    st.title("My Portfolio")
    portfolio = load_portfolio()

    with st.form("add_holding_form"):
        st.subheader("Add / Update Holding")
        st.markdown("Enter 0 shares to remove a holding.")
        col1, col2, col3 = st.columns(3)
        with col1: p_ticker = st.text_input("Ticker").upper()
        with col2: p_shares = st.number_input("Number of Shares", min_value=0.0, step=0.1)
        with col3: p_price = st.number_input("Average Purchase Price ($)", min_value=0.0, step=1.0)
        
        submit_portfolio = st.form_submit_button("Load onto Spaceship 🛸")
        if submit_portfolio and p_ticker:
            if p_shares == 0:
                if p_ticker in portfolio: del portfolio[p_ticker]
            else:
                portfolio[p_ticker] = {"shares": p_shares, "avg_price": p_price}
            save_portfolio(portfolio)
            st.success(f"Loaded {p_ticker} into the cargo bay! 🚀")
            st.balloons()
            st.rerun()

    st.markdown("---")
    
    if portfolio:
        st.subheader("Current Holdings & Performance")
        tickers = list(portfolio.keys())
        try:
            px_data = get_portfolio_prices(tickers)
        except Exception as e:
            st.error("Hit Yahoo Finance Rate Limit! Prices might be stale.")
            px_data = pd.DataFrame()

        portfolio_data = []
        total_invested = 0
        total_current_value = 0
        
        for t in tickers:
            shares = portfolio[t]["shares"]
            avg_price = portfolio[t]["avg_price"]
            invested = shares * avg_price
            
            current_price = avg_price
            try:
                if not px_data.empty:
                    if len(tickers) == 1: current_price = float(px_data['Close'].iloc[-1])
                    else: current_price = float(px_data['Close'][t].iloc[-1])
            except: pass
            
            current_val = shares * current_price
            pl_dollars = current_val - invested
            pl_pct = (pl_dollars / invested * 100) if invested > 0 else 0
            
            total_invested += invested
            total_current_value += current_val
            
            portfolio_data.append({
                "Ticker": t, "Shares": shares, "Avg Price": f"${avg_price:.2f}",
                "Current Price": f"${current_price:.2f}", "Invested": invested,
                "Current Value": current_val, "P/L ($)": pl_dollars, "P/L (%)": pl_pct
            })
            
        df_port = pd.DataFrame(portfolio_data)
        total_pl = total_current_value - total_invested
        total_pl_pct = (total_pl / total_invested * 100) if total_invested > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Invested", f"${total_invested:,.2f}")
        m2.metric("Current Value", f"${total_current_value:,.2f}", f"{total_pl:,.2f} ({total_pl_pct:.2f}%)")
        
        df_display = df_port.copy()
        df_display["Invested"] = df_display["Invested"].apply(lambda x: f"${x:,.2f}")
        df_display["Current Value"] = df_display["Current Value"].apply(lambda x: f"${x:,.2f}")
        df_display["P/L ($)"] = df_display["P/L ($)"].apply(lambda x: f"${x:,.2f}")
        df_display["P/L (%)"] = df_display["P/L (%)"].apply(lambda x: f"{x:,.2f}%")
        
        st.dataframe(df_display, use_container_width=True)
        
        st.subheader("Asset Allocation")
        fig_pie = px.pie(df_port, values='Current Value', names='Ticker', template='plotly_dark')
        st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.info("Your portfolio is empty. Add a holding above.")

# ==============================================================================
# TAB 3: RISK MANAGEMENT
# ==============================================================================
with tab3:
    st.title("Risk Management & AI Stress Test")
    portfolio = load_portfolio()
    
    if not portfolio:
        st.info("Add holdings to your Portfolio tab to see risk analytics.")
    else:
        tickers = list(portfolio.keys())
        st.write("Analyzing risk for:", ", ".join(tickers))
        
        with st.spinner("Calculating Portfolio Beta, Sector info, and Value at Risk (VaR)..."):
            try:
                spy_returns_data, port_data = get_risk_historical_data(tickers)
                spy_returns = spy_returns_data.pct_change().dropna()
            except Exception as e:
                st.error("⚠️ Hit Yahoo Finance Rate Limit. Cannot fetch historical data for Risk calculations.")
                spy_returns_data, port_data, spy_returns = None, pd.DataFrame(), pd.Series()
            
            port_sectors = {}
            betas = {}
            var_95 = {}
            current_vals = {}
            
            for t in tickers:
                port_sectors[t] = get_company_sector(t)
                
                try:
                    if len(tickers) == 1: current_vals[t] = portfolio[t]['shares'] * float(port_data.iloc[-1])
                    else: current_vals[t] = portfolio[t]['shares'] * float(port_data[t].iloc[-1])
                except:
                    current_vals[t] = portfolio[t]['shares'] * portfolio[t]['avg_price']
                
                try:
                    asset_returns = port_data.pct_change().dropna() if len(tickers) == 1 else port_data[t].pct_change().dropna()
                    percentile_5 = np.percentile(asset_returns, 5)
                    var_dollar = abs(percentile_5 * current_vals[t])
                    var_95[t] = {"pct": abs(percentile_5)*100, "dollar": var_dollar}
                    
                    aligned = pd.concat([asset_returns, spy_returns], axis=1).dropna()
                    aligned.columns = ['Asset', 'SPY']
                    covar = np.cov(aligned['Asset'], aligned['SPY'])[0, 1]
                    var = np.var(aligned['SPY'])
                    betas[t] = covar / var if var > 0 else 1.0
                except: 
                    betas[t] = 1.0
                    var_95[t] = {"pct": 0.0, "dollar": 0.0}
            
            # --- Display Risk Metrics ---
            st.subheader("Sector Concentration")
            sector_counts = {}
            for t, sec in port_sectors.items():
                val = current_vals[t]
                sector_counts[sec] = sector_counts.get(sec, 0) + val
                
            fig_sec = px.pie(names=list(sector_counts.keys()), values=list(sector_counts.values()), template='plotly_dark')
            st.plotly_chart(fig_sec, use_container_width=True)
            
            st.subheader("Risk Metrics (Beta & 95% Daily VaR)")
            st.markdown("*Value at Risk (VaR) represents the maximum expected loss over 1 trading day with 95% confidence based on 1-year historical data.*")
            
            metrics_data = []
            total_var_dollar = 0
            for t in tickers:
                metrics_data.append({
                    "Ticker": t, "Sector": port_sectors[t], "Beta (1Y)": f"{betas[t]:.2f}", 
                    "95% Daily VaR (%)": f"{var_95[t]['pct']:.2f}%", "95% Daily VaR ($)": f"${var_95[t]['dollar']:,.2f}"
                })
                total_var_dollar += var_95[t]['dollar']
                
            metrics_df = pd.DataFrame(metrics_data)
            st.table(metrics_df)
            st.metric("Estimated Portfolio Daily VaR (Uncorrelated)", f"${total_var_dollar:,.2f}")
            
        st.markdown("---")
        st.subheader("🤖 Chief Risk Officer: Macro Stress Test")
        
        try: api_key = st.secrets["GEMINI_API_KEY"]
        except: api_key = None
        
        if not api_key or api_key == "your_api_key_here":
            st.warning("Google Gemini API Key is missing.")
        else:
            if st.button("Run AI Portfolio Stress Test", type="primary"):
                with st.spinner("Simulating macro stresses and evaluating vulnerabilities..."):
                    try:
                        macro_news_raw = get_recent_news("economy+markets", days=3)
                        macro_news_text = "".join([f"- {n['title']}\n" for n in macro_news_raw[:10]])
                            
                        port_str = "".join([f"- {t}: Sector={port_sectors[t]}, Beta={betas[t]:.2f}, 95% VaR=${var_95[t]['dollar']:,.2f}\n" for t in tickers])
                            
                        prompt = f"""
                        You are the Chief Risk Officer for an aggressive growth fund. Evaluate the following portfolio against current macroeconomic news.
                        
                        PORTFOLIO METRICS (Volatility & Value at Risk):
                        {port_str}
                        Total Uncorrelated 95% Daily VaR: ${total_var_dollar:.2f}
                        
                        LATEST MACRO NEWS (Last 3 Days):
                        {macro_news_text}
                        
                        Provide a 'Risk Management Report' in markdown:
                        1. **Macro Stress Test**: How do the current macro news headlines threaten this specific portfolio? What is the worst-case scenario?
                        2. **Risk & VaR Warnings**: Analyze the sector exposure, Betas, and the Value at Risk. Is the daily risk tolerance (VaR) dangerously high?
                        3. **Risk Mitigation Strategy**: Provide actionable advice to hedge or rebalance this portfolio.
                        """
                        client = genai.Client(api_key=api_key)
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                                st.markdown(response.text)
                                break
                            except Exception as e:
                                if "503" in str(e) and attempt < max_retries - 1:
                                    time.sleep(2 ** attempt)
                                    continue
                                else:
                                    st.error(f"⚠️ Google Gemini API Error: The AI model is currently experiencing high demand. Please wait a moment and try again.\n\nDetails: {str(e)}")
                                    break
                    except Exception as e:
                        st.error(f"Error generating Risk Report: {str(e)}")
