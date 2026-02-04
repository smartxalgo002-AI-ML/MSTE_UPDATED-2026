import pandas as pd
from faker import Faker
import random
from datetime import datetime, timedelta

fake = Faker()

def generate_mock_data(num_articles=50):
    """Generates a DataFrame of mock news articles."""
    data = []
    
    # Categories for some realism
    categories = ['Technology', 'Finance', 'Global Markets', 'Economy', 'Energy', 'Healthcare']
    
    for i in range(num_articles):
        # 30% chance of being "today" to ensure we have data for "Previous" tab
        if random.random() < 0.3:
            date_obj = datetime.now()
            # Random time today
            start_of_day = datetime.now().replace(hour=0, minute=0, second=0)
            seconds_since_midnight = (date_obj - start_of_day).seconds
            random_seconds = random.randint(0, seconds_since_midnight)
            full_datetime = start_of_day + timedelta(seconds=random_seconds)
        else:
            # Older data
            date_obj = fake.date_between(start_date='-30d', end_date='-1d')
            time_obj = fake.time_object()
            full_datetime = datetime.combine(date_obj, time_obj)
            
        date = full_datetime.date()
        time_str = full_datetime.strftime("%I:%M %p")

        # All data including signals, sentiment, etc. will come from backend
        # Mock data simulates what backend would provide
        sentiment_score = random.uniform(0.1, 0.99)
        sentiment_label = random.choice(["POSITIVE", "NEGATIVE", "NEUTRAL"])
        
        signal_confidence = random.uniform(70, 99)
        # Backend will provide the signal (BUY, SELL, or HOLD)
        signal_prediction = random.choice(["BUY", "SELL", "HOLD"])

        data.append({
            "id": i,
            "datetime": full_datetime,
            "date": date,
            "formatted_date": date.strftime("%b %d, %Y"),
            "time": time_str,
            "title": fake.sentence(nb_words=10).strip("."),
            "snippet": fake.paragraph(nb_sentences=3),
            "author": fake.name(),
            "category": random.choice(categories),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "signal_prediction": signal_prediction,
            "signal_confidence": signal_confidence,
            "full_content": "\n\n".join(fake.paragraphs(nb=5))
        })
        
    # Sort by datetime descending
    df = pd.DataFrame(data)
    df = df.sort_values(by="datetime", ascending=False).reset_index(drop=True)
    return df

if __name__ == "__main__":
    df = generate_mock_data()
    print(df.head())
