import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# Helper to load data
def load_data(source_type="all"):
    
    # Check for overnight signals first (if in Recent/Overnight tab)
    if source_type == "new":
        overnight_path = os.path.join("..", "output", "signals", "overnight_signal.json")
        new_path = os.path.join("..", "output", "signals", "signals_new.json")
        
        # If overnight file exists and is newer than signals_new, use it
        if os.path.exists(overnight_path) and os.path.getsize(overnight_path) > 5:
            if not os.path.exists(new_path) or os.path.getmtime(overnight_path) > os.path.getmtime(new_path):
                path = overnight_path
                st.session_state["is_overnight"] = True
            else:
                path = new_path
                st.session_state["is_overnight"] = False
        else:
            path = new_path
            st.session_state["is_overnight"] = False
    else:
        path = os.path.join("..", "output", "signals", "all_signals.json")

    if not os.path.exists(path):
        return pd.DataFrame()
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()
    
    if not df.empty:
        df['id'] = df['article_id']
        df['title'] = df['headline']
        df['author'] = df.get('source', 'Unknown Source')
        # Use the new full_content field, fallback to condensed_text
        df['full_content'] = df.get('full_content', df.get('condensed_text', ""))
        
        # Parse published_time which has format: "12:11 PM | 04 Feb 2026"
        # Parse published_time which has multiple formats
        def parse_custom_time(time_str):
            try:
                time_str = str(time_str).strip()
                # 1. Handle Pipe format: "12:11 PM | 04 Feb 2026"
                if '|' in time_str:
                    time_part, date_part = time_str.split('|')
                    combined = f"{date_part.strip()} {time_part.strip()}"
                    return pd.to_datetime(combined, format='%d %b %Y %I:%M %p', errors='coerce')
                
                # 2. Handle "February 05, 2026 at 10:53 AM" (The Hindu Business Line)
                if ' at ' in time_str:
                    return pd.to_datetime(time_str, format='%B %d, %Y at %I:%M %p', errors='coerce')
                
                # 3. Handle specific ISO-like format: "2026-02-05 10:55:07"
                return pd.to_datetime(time_str, errors='coerce')
            except:
                return pd.NaT
        
        # Use published_time for display, fallback to predicted_at if necessary
        time_source = df.get('published_time', df.get('predicted_at', pd.Series([datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")] * len(df))))
        df['timestamp'] = time_source.apply(parse_custom_time)
        
        # Fill NaNs in timestamp with predicted_at if the main parser failed
        mask_nat = df['timestamp'].isna()
        if mask_nat.any():
             # Try parsing predicted_at as fallback for failed ones
             df.loc[mask_nat, 'timestamp'] = pd.to_datetime(df.loc[mask_nat, 'predicted_at'].astype(str).str.replace(' IST', '').str.replace('T', ' '), errors='coerce')

        df['date'] = df['timestamp'].dt.date
        df['formatted_date'] = df['timestamp'].dt.strftime('%d %b %Y').fillna("Date N/A")
        df['time'] = df['timestamp'].dt.strftime('%H:%M').fillna("--:--")
        df['sentiment_label'] = df['sentiment'].str.upper()
        df['signal_prediction'] = df.get('predicted_signal', "HOLD")
        df['signal_confidence'] = df.get('signal_confidence', 0.0) * 100
        
        # Handle overnight specific display logic (now showing sentiment bias)
        if st.session_state.get("is_overnight", False) and source_type == "new":
             # We preserve the predicted_signal (BULLISH/BEARISH/NEUTRAL) 
             # and the confidence now that we have real bias values
             pass

        df = df.sort_values('timestamp', ascending=False)
        
        # Deduplicate to prevent Streamlit key errors
        df = df.drop_duplicates(subset=['id'])
        
    return df

# Session State
if "data_all" not in st.session_state:
    st.session_state.data_all = load_data("all")
if "data_new" not in st.session_state:
    st.session_state.data_new = load_data("new")
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "recent"
if "view" not in st.session_state:
    st.session_state.view = "list"
if "selected_article_id" not in st.session_state:
    st.session_state.selected_article_id = None
if "is_overnight" not in st.session_state:
    st.session_state.is_overnight = False

# ... (view state init)

# Sidebar
with st.sidebar:
    # Custom Styled Sidebar Title
    st.markdown("""
        <div style="
            text-align: left;
            font-size: 2rem;
            font-weight: 800;
            color: #ffffff;
            text-transform: uppercase;
            text-shadow: 0 0 5px rgba(0, 210, 255, 0.4);
            margin-bottom: 20px;
        ">
        📊 SignalNews
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("⏱️ Recent (New Batch)", key="btn_recent", use_container_width=True):
        st.session_state.active_tab = "recent"
        st.session_state.view = "list"
    
    if st.button("🕤 Previous (Today)", key="btn_previous", use_container_width=True):
        st.session_state.active_tab = "previous"
        st.session_state.view = "list"
        
    if st.button("⬇️ Historic (All)", key="btn_historic", use_container_width=True):
        st.session_state.active_tab = "historic"
        st.session_state.view = "list"
    
    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.session_state.data_all = load_data("all")
        st.session_state.data_new = load_data("new")
        st.rerun()

# Filter Data based on Active Tab
if st.session_state.active_tab == "recent":
    df_raw = st.session_state.data_new
    # Filter to show only "today's" news in the recent tab
    if not df_raw.empty and 'date' in df_raw.columns:
         today = datetime.now().date()
         df = df_raw[df_raw['date'] == today]
    else:
         df = df_raw

    if st.session_state.get("is_overnight", False):
        page_title = "🌙 AFTER MARKET HOUR NEWS"
        st.info("ℹ️ Market Closed: Showing overnight news sentiment bias. Trade signals will generate at 9:30 AM.")
    else:
        page_title = "RECENT SIGNALS (LATEST BATCH)"
    
elif st.session_state.active_tab == "previous":
    full_df = st.session_state.data_all
    if not full_df.empty:
        today = datetime.now().date()
        df = full_df[full_df['date'] == today]
    else:
        df = pd.DataFrame()
    page_title = "TODAY'S SIGNALS"

else:  # historic
    df = st.session_state.data_all
    page_title = "HISTORIC SIGNALS"


def show_list_view():
    st.markdown(f"## **{page_title}**")
    st.caption(f"Showing {len(df)} articles")
    
    import base64
    def get_base64_of_bin_file(bin_file):
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()

    # Background Image CSS (Refined: Blurred & Darkened)
    try:
        bin_str = get_base64_of_bin_file("trading_bg.png")
        page_bg_img = '''
        <style>
        /* Container for the background */
        [data-testid="stAppViewContainer"] > .main {
            background-color: transparent;
        }
        
        /* The Background Image Element */
        .stApp {
            background: transparent;
        }
        
        .stApp::before {
            content: "";
            position: fixed;
            top: 0; 
            left: 0;
            width: 100vw; 
            height: 100vh;
            background-image: url("data:image/png;base64,%s");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            
            filter: blur(4px) brightness(0.35) contrast(1.1); 
            z-index: -1;
        }
        </style>
        ''' % bin_str
        st.markdown(page_bg_img, unsafe_allow_html=True)
    except Exception as e:
        pass

    # Custom CSS for Hover Effect (Headlines Only + Sidebar)
    st.markdown("""
        <style>
        /* Target ONLY buttons in the main area (Headlines) */
        section[data-testid="stMain"] div.stButton button {
            border: 1px solid #444; /* Default subtle border */
            transition: all 0.3s ease-in-out;
            border-radius: 8px;
            background-color: rgba(20, 20, 30, 0.8); /* Semi-transparent button bg */
        }

        /* Hover State for Headlines - Cyan */
        section[data-testid="stMain"] div.stButton button:hover {
            border: 1px solid #00d2ff !important;
            background-color: rgba(0, 210, 255, 0.15) !important;
            box-shadow: 0 0 15px rgba(0, 210, 255, 0.4);
            color: #00d2ff !important;
            transform: scale(1.01);
        }
        
        /* ---------------------------------------------------- */
        /* Sidebar Buttons - Yellow Hover Effect "In Sides" */
        /* ---------------------------------------------------- */
        section[data-testid="stSidebar"] div.stButton button {
            border: 1px solid #444;
            transition: all 0.3s ease-in-out;
            background-color: rgba(30,30,30,0.8);
        }
        
        section[data-testid="stSidebar"] div.stButton button:hover {
            border: 1px solid #FFD700 !important; /* Gold/Yellow Border */
            color: #FFD700 !important;
            background-color: rgba(255, 215, 0, 0.15) !important; /* Faint yellow tint */
            box-shadow: 0 0 10px rgba(255, 215, 0, 0.4); /* Yellow glow */
        }

        /* Ensure the container doesn't block the effect */
        [data-testid="stHorizontalBlock"] {
            border: none;
            background-color: transparent;
        }
        </style>
    """, unsafe_allow_html=True)
    
    for index, row in df.iterrows():
        col1, col2, col3, col4, col5 = st.columns([0.3, 1, 1, 5, 1])
        
        with col1:
            st.write("★")
        with col2:
            st.write(row["formatted_date"])
        with col3:
            st.write(row["time"])
        with col4:
            if st.button(f"{row['title']}", key=f"btn_{row['id']}", use_container_width=True):
                st.session_state.selected_article_id = row['id']
                st.session_state.view = "detail"
                st.rerun()
        with col5:
            # Display signal with color
            signal = row['signal_prediction']
            if signal == "BUY":
                st.success(f"↗ {signal}")
            elif signal == "SELL":
                st.error(f"↘ {signal}")
            else:  # HOLD
                st.warning(f"→ {signal}")
        
        st.write("") # Spacing instead of divider


def show_detail_view():
    article = df[df['id'] == st.session_state.selected_article_id].iloc[0]
    
    # Back button
    if st.button("← Back to List"):
        st.session_state.view = "list"
        st.rerun()

    # Article Title
    st.title(article['title'])
    
    # Meta information
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"**{article.get('source', 'Unknown Source')}**", unsafe_allow_html=True)
    with col2:
        # Handle NaN or null formatted_date
        formatted_date = article.get('formatted_date', '')
        if formatted_date and not (isinstance(formatted_date, float)):
            st.write(f"**{formatted_date.upper()}**")
        else:
            st.write("**DATE N/A**")
        st.write(f"**{article.get('time', '')} IST**")
    
    st.divider()

    # Content with INLINE CSS to ensure it renders correctly
    content_html = f"""
    <div style="
        background-color: rgba(10, 10, 15, 0.85);
        padding: 30px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        color: #e0e0e0;
        font-size: 1.1rem;
        line-height: 1.6;
        margin-top: 20px;
    ">
        {article['full_content'].replace(chr(10), '<br><br>')}
    </div>
    """
    st.markdown(content_html, unsafe_allow_html=True)
    
    
    # Cards Section
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("SENTIMENT ANALYSIS")
        
        # Sentiment
        scol1, scol2 = st.columns([1, 1])
        with scol1:
            st.write("**Sentiment**")
        with scol2:
            # Color based on sentiment
            if article['sentiment_label'] == "POSITIVE":
                st.success(article['sentiment_label'])
            elif article['sentiment_label'] == "NEGATIVE":
                st.error(article['sentiment_label'])
            else:
                st.info(article['sentiment_label'])
        
        # Sentiment Score
        st.write("**Sentiment Score**")
        # Ensure score is within [0.0, 1.0] for progress bar using absolute intensity
        score_intensity = max(0.0, min(1.0, abs(article['sentiment_score'])))
        st.progress(score_intensity)
        st.write(f"**{article['sentiment_score']:.2f}**")
    
    with col2:
        st.subheader("SIGNAL INTELLIGENCE")
        
        # Predicted Signal
        scol1, scol2 = st.columns([1, 1])
        with scol1:
            st.write("**Predicted Signal**")
        with scol2:
            # Color based on signal
            if article['signal_prediction'] in ["BUY", "BULLISH"]:
                st.success(f"↗ {article['signal_prediction']}")
            elif article['signal_prediction'] in ["SELL", "BEARISH"]:
                st.error(f"↘ {article['signal_prediction']}")
            else:
                st.warning(f"→ {article['signal_prediction']}")
        
        st.write("")  # Spacing
        
        # Signal Confidence
        scol1, scol2 = st.columns([1, 1])
        with scol1:
            st.write("**Signal Confidence**")
        with scol2:
            st.write(f"### {article['signal_confidence']:.1f}%")


if st.session_state.view == "list":
    show_list_view()
else:
    show_detail_view()
