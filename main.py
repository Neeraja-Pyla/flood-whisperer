import streamlit as st
from huggingface_hub import InferenceClient
from geopy.geocoders import Nominatim
import folium
from streamlit_folium import st_folium
from langdetect import detect
from dotenv import load_dotenv
import os
import requests
from datetime import datetime
import streamlit.components.v1 as components

# Optional translator
try:
    from googletrans import Translator
    google_translator = Translator()
except Exception:
    google_translator = None

# 🌪 Basic UI Setup
st.set_page_config(page_title="🌍 Disaster Whisperer", layout="wide")
st.title("🌍 Disaster Whisperer – Live Maps + Multilingual + SMS Alerts")

# Sidebar
st.sidebar.header("Configuration")

# API keys
openai_key = st.sidebar.text_input("OpenAI API Key (optional)", type="password")
hfh_model = st.sidebar.text_input("Hugging Face model (optional)", value="HuggingFaceH4/zephyr-7b-beta")
owm_key = st.sidebar.text_input("OpenWeather API Key (optional)", type="password")

# Twilio credentials
st.sidebar.subheader("📡 Twilio SMS Settings")
twilio_sid = st.sidebar.text_input("Twilio SID", type="password")
twilio_token = st.sidebar.text_input("Twilio Auth Token", type="password")
twilio_phone = st.sidebar.text_input("Twilio Phone Number (e.g., +1234567890)")

lang_pref = st.sidebar.selectbox("UI Language", ["English", "Hindi", "Telugu"])

# 🌐 UI Translation Dictionary
ui_texts = {
    "English": {
        "report_title": "Report a Situation",
        "city_label": "City / Pincode / Landmark",
        "severity_label": "Severity",
        "severity_opts": ["Low", "Moderate", "High", "Extreme"],
        "describe_label": "Describe the situation",
        "analyze_btn": "Analyze & Show Map",
        "weather_title": "Live Weather & Alerts",
        "weather_desc": "OpenWeather shows real-time data & alerts (requires API key).",
        "persistent_title": "✅ Last Generated Advice",
        "advice_header": "AI-Generated Safety Advice",
        "default_advice": "Stay alert! Move to a safe area immediately if danger is nearby.",
        "sms_success": "📱 Alert messages successfully sent to local residents.",
        "sms_fail": "⚠ SMS alert failed. Please check Twilio configuration."
    },
    "Hindi": {
        "report_title": "स्थिति की रिपोर्ट करें",
        "city_label": "शहर / पिनकोड / स्थान",
        "severity_label": "गंभीरता",
        "severity_opts": ["कम", "मध्यम", "उच्च", "अत्यधिक"],
        "describe_label": "स्थिति का वर्णन करें",
        "analyze_btn": "विश्लेषण करें और मानचित्र दिखाएँ",
        "weather_title": "लाइव मौसम और अलर्ट",
        "weather_desc": "ओपनवेदर वास्तविक समय डेटा और अलर्ट दिखाता है (API कुंजी आवश्यक)।",
        "persistent_title": "✅ अंतिम उत्पन्न सलाह",
        "advice_header": "एआई द्वारा उत्पन्न सुरक्षा सलाह",
        "default_advice": "सतर्क रहें! खतरा पास हो तो तुरंत सुरक्षित स्थान पर जाएं।",
        "sms_success": "📱 स्थानीय लोगों को अलर्ट संदेश भेजे गए हैं।",
        "sms_fail": "⚠ एसएमएस अलर्ट विफल। कृपया ट्विलियो सेटिंग जांचें।"
    },
    "Telugu": {
        "report_title": "పరిస్థితిని నివేదించండి",
        "city_label": "నగరం / పిన్‌కోడ్ / ప్రదేశం",
        "severity_label": "తీవ్రత",
        "severity_opts": ["తక్కువ", "మోస్తరు", "అధిక", "తీవ్రమైనది"],
        "describe_label": "పరిస్థితిని వివరించండి",
        "analyze_btn": "విశ్లేషించి మ్యాప్ చూపించు",
        "weather_title": "ప్రత్యక్ష వాతావరణం మరియు హెచ్చరికలు",
        "weather_desc": "ఓపెన్‌వెదర్ రియల్‌టైమ్ డేటా మరియు హెచ్చరికలను చూపుతుంది (API కీ అవసరం).",
        "persistent_title": "✅ చివరిగా రూపొందించిన సలహా",
        "advice_header": "AI సృష్టించిన భద్రతా సలహా",
        "default_advice": "జాగ్రత్తగా ఉండండి! ప్రమాదం దగ్గరలో ఉంటే వెంటనే సురక్షిత ప్రదేశానికి వెళ్ళండి.",
        "sms_success": "📱 స్థానిక ప్రజలకు హెచ్చరిక సందేశాలు పంపబడ్డాయి.",
        "sms_fail": "⚠ SMS హెచ్చరిక విఫలమైంది. దయచేసి Twilio కాన్ఫిగరేషన్ తనిఖీ చేయండి."
    }
}
ui = ui_texts[lang_pref]

# Initialize helpers
geolocator = Nominatim(user_agent="disaster-whisperer")
hf_client = None
try:
    hf_client = InferenceClient(model=hfh_model)
except Exception:
    hf_client = None

for key in ["advice", "map_data", "generated_time"]:
    if key not in st.session_state:
        st.session_state[key] = None

# Core helpers
def geocode_place(place):
    try:
        loc = geolocator.geocode(place, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except Exception:
        pass
    return None

def fetch_weather(lat, lon, api_key):
    if not api_key:
        return None
    try:
        url = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&exclude=minutely,hourly&units=metric&appid={api_key}"
        r = requests.get(url, timeout=10)
        return r.json() if r.ok else None
    except Exception:
        return None

def translate_text(text, target):
    if google_translator:
        try:
            lang_map = {"English": "en", "Hindi": "hi", "Telugu": "te"}
            return google_translator.translate(text, dest=lang_map[target]).text
        except Exception:
            pass
    return text

def generate_advice(prompt, openai_key=None, hf_client=None):
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            return r.choices[0].message.content.strip()
        except Exception:
            pass
    if hf_client:
        try:
            r = hf_client.text_generation(prompt, max_new_tokens=150)
            if isinstance(r, dict) and "generated_text" in r:
                return r["generated_text"].strip()
            return str(r).strip()
        except Exception:
            pass
    return ui["default_advice"]
# 📡 SMS Alert System (uses sidebar Twilio credentials)
def send_alert_sms(phone_numbers, message):
    try:
        from twilio.rest import Client
        if not (twilio_sid and twilio_token and twilio_phone):
            raise Exception("Twilio keys missing in sidebar.")
        client = Client(twilio_sid, twilio_token)
        for number in phone_numbers:
            try:
                msg = client.messages.create(
                    body=message,
                    from_=twilio_phone,   # or use messaging_service_sid if configured
                    to=number
                )
                st.success(f"✅ SMS sent to {number} (SID: {msg.sid})")
            except Exception as inner_e:
                st.error(f"❌ Error sending to {number}: {inner_e}")
        return True
    except Exception as e:
        st.error(f"⚠ {ui['sms_fail']} ({e})")
        return False

# Layout
left, right = st.columns([2, 1])
with left:
    st.subheader(ui["report_title"])
    place = st.text_input(ui["city_label"], placeholder="e.g., Hyderabad or 500001")
    severity = st.selectbox(ui["severity_label"], ui["severity_opts"])
    report = st.text_area(ui["describe_label"], height=140)
    analyze = st.button(ui["analyze_btn"])

with right:
    st.subheader(ui["weather_title"])
    st.write(ui["weather_desc"])

# Logic
if analyze:
    if not place or not report:
        st.warning("Please enter both place and report.")
        st.stop()

    geo = geocode_place(place)
    if not geo:
        st.error("Could not locate this place.")
        st.stop()
    lat, lon, addr = geo
    st.success(f"📍 {addr} ({lat:.4f}, {lon:.4f})")

    weather_data = fetch_weather(lat, lon, owm_key)
    summary = ""
    if weather_data and "current" in weather_data:
        cur = weather_data["current"]
        summary = f"Temp {cur.get('temp')}°C, weather: {cur.get('weather',[{}])[0].get('description','')}."
        st.metric("🌡 Temp", f"{cur.get('temp')}°C")

    prompt = f"Disaster in {place}, severity: {severity}. Report: {report}. {summary} Give clear, life-saving advice."
    advice = generate_advice(prompt, openai_key, hf_client)
    advice_translated = translate_text(advice, lang_pref)

    st.session_state.advice = advice_translated
    st.session_state.map_data = (lat, lon, place)
    st.session_state.generated_time = datetime.now().strftime("%I:%M %p • %b %d, %Y")

    # 📲 SMS Alert Dispatch
    local_contacts = ["+916301475493","+917075297477","+919666030209"]  # Replace dynamically
    alert_msg = f"🚨 {severity.upper()} ALERT for {place}!\n{advice_translated}"
    if send_alert_sms(local_contacts, alert_msg):
        st.success(ui["sms_success"])

# Persistent display
if st.session_state.advice:
    st.markdown(f"## {ui['persistent_title']}")
    components.html(f"""
    <div style="background:rgba(255,255,255,0.95);
                border-radius:16px;
                padding:1rem 1.5rem;
                box-shadow:0 4px 20px rgba(0,0,0,0.08);
                animation:fadeIn 1.5s ease;">
        <h4 style="color:#0072ff;margin-top:0;">{ui['advice_header']}</h4>
        <p style="font-size:1rem;line-height:1.6;color:#222;">{st.session_state.advice}</p>
        <p style="color:gray;font-size:0.8rem;text-align:right;">⏱ {st.session_state.generated_time}</p>
    </div>
    <style>@keyframes fadeIn{{from{{opacity:0;transform:translateY(20px);}}to{{opacity:1;transform:translateY(0);}}}}</style>
    """, height=240)

    if st.session_state.map_data:
        lat, lon, place = st.session_state.map_data
        m = folium.Map(location=[lat, lon], zoom_start=9)
        folium.Marker([lat, lon], popup=place, tooltip="Reported Location",
                      icon=folium.Icon(color="red")).add_to(m)
        folium.Circle([lat, lon], radius=10000, color="crimson",
                      fill=True, fill_opacity=0.1).add_to(m)
        st_folium(m, width=900, height=500)

st.markdown("---")
st.caption("🌍 Disaster Whisperer • Multilingual • AI • Live Weather • SMS-Enabled Alerts")
