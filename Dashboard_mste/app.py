import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime

# Helper to load data
def load_data(source_type="all"):
    if source_type == "new":
        path = os.path.join("..", "output", "signals", "signals_new.json")
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
        df['full_content'] = df.get('full_content', df['condensed_text'])
        
        # Parse published_time which has format: "12:11 PM | 04 Feb 2026"
        def parse_custom_time(time_str):
            try:
                time_str = str(time_str).strip()
                # Handle the custom format "HH:MM AM/PM | DD Mon YYYY"
                if '|' in time_str:
                    time_part, date_part = time_str.split('|')
                    time_part = time_part.strip()
                    date_part = date_part.strip()
                    # Combine and parse: "04 Feb 2026 12:11 PM"
                    combined = f"{date_part} {time_part}"
                    return pd.to_datetime(combined, format='%d %b %Y %I:%M %p', errors='coerce')
                # Fallback to standard parsing for predicted_at format
                else:
                    time_str = time_str.replace(' IST', '').replace('T', ' ')
                    return pd.to_datetime(time_str, errors='coerce')
            except:
                return pd.NaT
        
        # Use published_time for display, fallback to predicted_at if necessary
        time_source = df.get('published_time', df['predicted_at'])
        df['timestamp'] = time_source.apply(parse_custom_time)
        
        df['date'] = df['timestamp'].dt.date
        df['formatted_date'] = df['timestamp'].dt.strftime('%d %b %Y')
        df['time'] = df['timestamp'].dt.strftime('%H:%M')
        df['sentiment_label'] = df['sentiment'].str.upper()
        df['signal_prediction'] = df['predicted_signal']
        df['signal_confidence'] = df['signal_confidence'] * 100
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

# ... (view state init)

# Sidebar
with st.sidebar:
    st.title("📊 SignalNews")
    
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
    df = st.session_state.data_new
    page_title = "Recent Signals (Latest Batch)"
    
elif st.session_state.active_tab == "previous":
    full_df = st.session_state.data_all
    if not full_df.empty:
        today = datetime.now().date()
        df = full_df[full_df['date'] == today]
    else:
        df = pd.DataFrame()
    page_title = "Today's Signals"

else:  # historic
    df = st.session_state.data_all
    page_title = "Historic Signals"


def show_list_view():
    st.header(page_title)
    st.caption(f"Showing {len(df)} articles")
    
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
        
        st.divider()


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
        st.caption(f"{article.get('time', '')} IST")
    
    st.divider()
    
    # Show Full Content
    content_to_show = article.get('full_content') or article.get('condensed_text', 'No content available.')
    st.write(content_to_show)
    
    # URL Link
    if article.get('url'):
        st.write("")
        st.link_button("🌐 Read Original Article", article['url'], use_container_width=True)
    
    st.write("")  # Spacing
    
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
            if article['signal_prediction'] == "BUY":
                st.success(f"↗ {article['signal_prediction']}")
            elif article['signal_prediction'] == "SELL":
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
