import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests

MAPBOX_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

st.set_page_config(page_title="Pro Navigator v2.0", layout="wide")

if 'route_data' not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор")

with st.sidebar:
    st.header("📍 Маршрут")

    start_addr = st.text_input(
        "Ваш адрес (Старт/Финиш)",
        "Москва, Красная площадь"
    )

    dest_raw = st.text_area(
        "Точки через ;",
        "Москва, Тверская 1; Москва, Новый Арбат 10; Москва, ВДНХ"
    )

    btn_calc = st.button("🗺️ Построить маршрут")


# ---------- функции ----------

def get_coordinates(address):

    try:
        geolocator = Nominatim(user_agent="nav_app")
        loc = geolocator.geocode(address)

        if loc:
            return (loc.latitude, loc.longitude, loc.address)

    except:
        pass

    return None


def get_mapbox_route(points):

    if MAPBOX_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
        return None

    coords = ";".join([f"{p[1]},{p[0]}" for p in points])

    url = f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords}"

    params = {
        "access_token": MAPBOX_TOKEN,
        "geometries": "geojson",
        "overview": "full"
    }

    try:

        r = requests.get(url, params=params)
        data = r.json()

        if "routes" in data:
            return data["routes"][0]["geometry"]["coordinates"]

    except:
        pass

    return None


# ---------- расчет ----------

if btn_calc:

    start = get_coordinates(start_addr)

    if start:

        points = []

        for a in dest_raw.split(";"):

            coords = get_coordinates(a.strip())

            if coords:
                points.append({
                    "lat": coords[0],
                    "lon": coords[1],
                    "name": coords[2]
                })

        current = (start[0], start[1])

        ordered = []
        temp = points[:]

        while temp:

            next_pt = min(
                temp,
                key=lambda x: geodesic(
                    current,
                    (x['lat'], x['lon'])
                ).km
            )

            ordered.append(next_pt)

            current = (next_pt['lat'], next_pt['lon'])

            temp.remove(next_pt)

        st.session_state.route_data = {
            "start": start,
            "ordered_stops": ordered
        }

    else:
        st.error("Не найден стартовый адрес")


# ---------- карта ----------

if st.session_state.route_data:

    data = st.session_state.route_data

    s_lat, s_lon, s_name = data["start"]

    stops = data["ordered_stops"]

    all_coords = [(s_lat, s_lon)] + \
        [(p['lat'], p['lon']) for p in stops] + \
        [(s_lat, s_lon)]

    road = get_mapbox_route(all_coords)

    m = folium.Map(
        location=[s_lat, s_lon],
        zoom_start=12
    )

    if road:

        path = [[p[1], p[0]] for p in road]

        folium.PolyLine(
            path,
            color="red",
            weight=6
        ).add_to(m)

    else:

        folium.PolyLine(
            all_coords,
            color="blue"
        ).add_to(m)

    folium.Marker(
        [s_lat, s_lon],
        tooltip="СТАРТ"
    ).add_to(m)

    for i, p in enumerate(stops, 1):

        folium.Marker(
            [p['lat'], p['lon']],
            tooltip=f"{i}. {p['name']}"
        ).add_to(m)

    st_folium(m, width="100%", height=500)

  # ---------- ссылка навигатора ----------

    origin = f"{s_lat},{s_lon}"

    if stops:
        waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
        google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"
    else:
        google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&travelmode=driving"

    st.markdown(f"""
    <a href="{google_url}">
    <div style="
    background-color:#28a745;
    color:white;
    padding:20px;
    text-align:center;
    border-radius:15px;
    font-size:22px;
    font-weight:bold;
    cursor:pointer;">
    🚀 ЗАПУСТИТЬ НАВИГАТОР
    </div>
    </a>
    """, unsafe_allow_html=True)






