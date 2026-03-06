import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

# ==========================
# НАСТРОЙКИ
# ==========================

MAPBOX_TOKEN = "ВАШ_MAPBOX_TOKEN"

st.set_page_config(page_title="Маршрутный планировщик", layout="wide")

st.title("🚗 Планировщик маршрута")

# ==========================
# ФУНКЦИЯ ПОДСКАЗОК АДРЕСА
# ==========================

def get_address_suggestions(query):

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json"

    params = {
        "access_token": MAPBOX_TOKEN,
        "autocomplete": "true",
        "limit": 5
    }

    r = requests.get(url, params=params)
    data = r.json()

    suggestions = []

    for feature in data["features"]:
        suggestions.append(feature["place_name"])

    return suggestions


# ==========================
# ПОЛУЧЕНИЕ КООРДИНАТ
# ==========================

def geocode(address):

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{address}.json"

    params = {
        "access_token": MAPBOX_TOKEN,
        "limit": 1
    }

    r = requests.get(url, params=params)
    data = r.json()

    if len(data["features"]) > 0:

        coords = data["features"][0]["center"]

        return coords[1], coords[0]

    return None, None


# ==========================
# АЛГОРИТМ ПЛАНИРОВАНИЯ
# ==========================

def schedule_locations(locations, start_time=8):

    current_time = start_time
    ordered = []

    for loc in sorted(locations, key=lambda x: x["open"]):

        if current_time < loc["open"]:
            current_time = loc["open"]

        if current_time + loc["duration"] <= loc["close"]:
            ordered.append(loc)
            current_time += loc["duration"]

    return ordered


# ==========================
# ХРАНИЛИЩЕ ТОЧЕК
# ==========================

if "locations" not in st.session_state:
    st.session_state.locations = []

# ==========================
# ДОБАВЛЕНИЕ АДРЕСА
# ==========================

st.subheader("Добавить точку")

query = st.text_input("Введите адрес")

selected_address = None

if query:

    suggestions = get_address_suggestions(query)

    if suggestions:
        selected_address = st.selectbox(
            "Выберите адрес",
            suggestions
        )

col1, col2, col3 = st.columns(3)

with col1:
    open_time = st.number_input("Открытие", 0, 23, 9)

with col2:
    close_time = st.number_input("Закрытие", 0, 23, 18)

with col3:
    duration = st.number_input("Длительность визита (часы)", 1, 8, 1)

if st.button("Добавить точку"):

    if selected_address:

        lat, lon = geocode(selected_address)

        st.session_state.locations.append({

            "address": selected_address,
            "lat": lat,
            "lon": lon,
            "open": open_time,
            "close": close_time,
            "duration": duration
        })

# ==========================
# СПИСОК ТОЧЕК
# ==========================

st.subheader("Точки маршрута")

if st.session_state.locations:

    df = pd.DataFrame(st.session_state.locations)

    st.dataframe(df)

# ==========================
# ПЛАНИРОВАНИЕ
# ==========================

if st.button("Оптимизировать по времени"):

    ordered = schedule_locations(st.session_state.locations)

    st.session_state.locations = ordered

    st.success("Маршрут упорядочен!")

# ==========================
# КАРТА
# ==========================

if st.session_state.locations:

    df = pd.DataFrame(st.session_state.locations)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=120,
        pickable=True
    )

    view = pdk.ViewState(
        latitude=df["lat"].mean(),
        longitude=df["lon"].mean(),
        zoom=10
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="mapbox://styles/mapbox/streets-v11",
        mapbox_key=MAPBOX_TOKEN
    )

    st.pydeck_chart(deck)

# ==========================
# GOOGLE MAPS
# ==========================

if len(st.session_state.locations) >= 2:

    addresses = [loc["address"] for loc in st.session_state.locations]

    origin = addresses[0]
    destination = addresses[-1]

    waypoints = "|".join(addresses[1:-1])

    google_url = f"""
    https://www.google.com/maps/dir/?api=1
    &origin={origin}
    &destination={destination}
    &waypoints={waypoints}
    &travelmode=driving
    """

    st.markdown(f"""
    <a href="{google_url}" style="text-decoration:none;">
    <div style="
    background-color:#28a745;
    color:white;
    padding:20px;
    text-align:center;
    border-radius:15px;
    font-size:22px;
    font-weight:bold;">
    🚀 ЗАПУСТИТЬ НАВИГАТОР
    </div>
    </a>
    """, unsafe_allow_html=True)


