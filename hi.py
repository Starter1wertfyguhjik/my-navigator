import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests

# =========================
# НАСТРОЙКИ
# =========================

MAPBOX_TOKEN = "ВАШ_MAPBOX_TOKEN"

st.set_page_config(page_title="Pro Navigator", layout="wide")

if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор")

# =========================
# SIDEBAR
# =========================

with st.sidebar:

    st.header("Маршрут")

    start_addr = st.text_input(
        "Старт",
        "Москва, Красная площадь"
    )

    dest_raw = st.text_area(
        "Адреса через ;",
        "Москва, Тверская 1; Москва, Арбат 10; Москва, ВДНХ"
    )

    st.write("Время пребывания (часы)")

    t1 = st.number_input("Точка 1",1,8,1)
    t2 = st.number_input("Точка 2",1,8,1)
    t3 = st.number_input("Точка 3",1,8,1)

    btn_calc = st.button("Построить маршрут")

# =========================
# ГЕОКОДЕР
# =========================

def get_coordinates(address):

    try:

        geolocator = Nominatim(user_agent="smart_nav")

        loc = geolocator.geocode(address)

        if loc:
            return (loc.latitude, loc.longitude, loc.address)

    except:
        pass

    return None


# =========================
# MAPBOX ДОРОГА
# =========================

def get_mapbox_route(points):

    if MAPBOX_TOKEN == "ВАШ_MAPBOX_TOKEN":
        return None

    coords = ";".join([f"{p[1]},{p[0]}" for p in points])

    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords}"

    params = {
        "access_token": MAPBOX_TOKEN,
        "geometries": "geojson"
    }

    try:

        r = requests.get(url, params=params)

        data = r.json()

        if "routes" in data:
            return data["routes"][0]["geometry"]["coordinates"]

    except:
        pass

    return None


# =========================
# РАСЧЕТ
# =========================

if btn_calc:

    start_res = get_coordinates(start_addr)

    if start_res:

        points = []

        durations = [t1,t2,t3]

        for i,a in enumerate(dest_raw.split(";")):

            coords = get_coordinates(a.strip())

            if coords:

                points.append({
                    "lat":coords[0],
                    "lon":coords[1],
                    "name":coords[2],
                    "duration":durations[i] if i<len(durations) else 1
                })

        current_pos = (start_res[0],start_res[1])

        ordered = []

        temp = points[:]

        while temp:

            next_pt = min(
                temp,
                key=lambda x: geodesic(
                    current_pos,
                    (x["lat"],x["lon"])
                ).km
            )

            ordered.append(next_pt)

            current_pos=(next_pt["lat"],next_pt["lon"])

            temp.remove(next_pt)

        st.session_state.route_data = {
            "start":start_res,
            "ordered":ordered
        }

# =========================
# КАРТА
# =========================

if st.session_state.route_data:

    data = st.session_state.route_data

    s_lat,s_lon,s_name = data["start"]

    stops = data["ordered"]

    coords=[(s_lat,s_lon)]

    for p in stops:
        coords.append((p["lat"],p["lon"]))

    coords.append((s_lat,s_lon))

    road = get_mapbox_route(coords)

    m = folium.Map(
        location=[s_lat,s_lon],
        zoom_start=12
    )

    if road:

        path=[[p[1],p[0]] for p in road]

        folium.PolyLine(
            path,
            color="red",
            weight=6
        ).add_to(m)

    else:

        folium.PolyLine(
            coords,
            color="blue"
        ).add_to(m)

    folium.Marker(
        [s_lat,s_lon],
        tooltip="СТАРТ",
        icon=folium.Icon(color="red")
    ).add_to(m)

    for i,p in enumerate(stops,1):

        folium.Marker(
            [p["lat"],p["lon"]],
            tooltip=f"{i}. {p['name']} ({p['duration']}ч)",
            icon=folium.Icon(color="blue")
        ).add_to(m)

    st_folium(m,width="100%",height=500)

# =========================
# GOOGLE MAPS
# =========================

    origin=f"{s_lat},{s_lon}"

    waypoints="|".join(
        [f"{p['lat']},{p['lon']}" for p in stops]
    )

    google_url=f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"

    st.markdown(f"""
    <a href="{google_url}">
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
    """,unsafe_allow_html=True)

# =========================
# СПИСОК
# =========================

    with st.expander("План маршрута"):

        st.write(f"Старт: {s_name}")

        for i,p in enumerate(stops,1):
            st.write(f"{i}. {p['name']} — {p['duration']} ч")

        st.write("Финиш: возврат")
