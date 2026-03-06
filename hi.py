import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime

MAPBOX_TOKEN = ""

st.set_page_config(page_title="Smart Navigator", layout="wide")

if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор")

# ---------------- ПОИСК С ПОДСКАЗКАМИ ----------------

def address_search(query):

    url = "https://nominatim.openstreetmap.org/search"

    params = {
        "q": query,
        "format": "json",
        "limit": 5
    }

    try:
        r = requests.get(url, params=params)
        data = r.json()
        return [x["display_name"] for x in data]
    except:
        return []

# ---------------- SIDEBAR ----------------

with st.sidebar:

    st.header("📍 Маршрут")

    start_query = st.text_input("Введите старт")

    suggestions = address_search(start_query) if start_query else []

    start_addr = st.selectbox(
        "Выберите адрес",
        suggestions if suggestions else ["Введите адрес выше"]
    )

    dest_raw = st.text_area(
        "Точки (каждая строка новая точка)",
        """Москва, Тверская 1 | 18
Москва, Новый Арбат 10 | 20
Москва, ВДНХ"""
    )

    btn_calc = st.button("Построить маршрут")

# ---------------- ФУНКЦИИ ----------------

def get_coordinates(address):

    try:
        geolocator = Nominatim(user_agent="smart_nav")

        loc = geolocator.geocode(address)

        if loc:
            return loc.latitude, loc.longitude, loc.address

    except:
        return None

    return None


def get_mapbox_route(points):

    if not MAPBOX_TOKEN:
        return None

    coords = ";".join([f"{p[1]},{p[0]}" for p in points])

    url = f"https://api.mapbox.com/directions/v5/mapbox/driving/{coords}"

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
        return None

    return None

# ---------------- ПАРСИНГ ТОЧЕК ----------------

def parse_points(text):

    points = []

    lines = text.split("\n")

    for line in lines:

        if "|" in line:

            addr, time = line.split("|")

            try:
                close = int(time.strip())
            except:
                close = None

        else:

            addr = line
            close = None

        points.append((addr.strip(), close))

    return points

# ---------------- СОРТИРОВКА С УЧЁТОМ ВРЕМЕНИ ----------------

def optimize_route(start, points):

    speed = 40

    now = datetime.now().hour

    current_pos = start

    ordered = []

    temp = points[:]

    while temp:

        best = None
        best_dist = None

        for p in temp:

            dist = geodesic(
                current_pos,
                (p["lat"], p["lon"])
            ).km

            travel = dist / speed

            arrival = now + travel

            if p["close"] and arrival > p["close"]:
                continue

            if best_dist is None or dist < best_dist:
                best = p
                best_dist = dist

        if not best:
            best = temp[0]

        ordered.append(best)

        dist = geodesic(
            current_pos,
            (best["lat"], best["lon"])
        ).km

        now += dist / speed

        current_pos = (best["lat"], best["lon"])

        temp.remove(best)

    return ordered

# ---------------- ПОСТРОЕНИЕ ----------------

if btn_calc:

    start_coords = get_coordinates(start_addr)

    if not start_coords:
        st.error("Не найден старт")
    else:

        parsed = parse_points(dest_raw)

        points = []

        for addr, close in parsed:

            coords = get_coordinates(addr)

            if coords:

                points.append({
                    "lat": coords[0],
                    "lon": coords[1],
                    "name": coords[2],
                    "close": close
                })

        ordered = optimize_route(
            (start_coords[0], start_coords[1]),
            points
        )

        st.session_state.route_data = {
            "start": start_coords,
            "stops": ordered
        }

# ---------------- КАРТА ----------------

if st.session_state.route_data:

    data = st.session_state.route_data

    s_lat, s_lon, s_name = data["start"]

    stops = data["stops"]

    coords = [(s_lat, s_lon)]

    for p in stops:
        coords.append((p["lat"], p["lon"]))

    coords.append((s_lat, s_lon))

    route = get_mapbox_route(coords)

    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)

    if route:

        path = [[p[1], p[0]] for p in route]

        folium.PolyLine(path, color="red", weight=6).add_to(m)

    else:

        folium.PolyLine(coords, color="blue", weight=4).add_to(m)

    folium.Marker(
        [s_lat, s_lon],
        tooltip="СТАРТ / ФИНИШ",
        icon=folium.Icon(color="red")
    ).add_to(m)

    for i, p in enumerate(stops, 1):

        label = p["name"]

        if p["close"]:
            label += f" | до {p['close']}:00"

        folium.Marker(
            [p["lat"], p["lon"]],
            tooltip=f"{i}. {label}",
            icon=folium.Icon(color="blue")
        ).add_to(m)

    st_folium(m, width="100%", height=500)

# ---------------- КНОПКА НАВИГАЦИИ ----------------

    origin = f"{s_lat},{s_lon}"

    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])

    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"

    st.markdown(
        f"""
        <a href="{google_url}" target="_blank" style="text-decoration:none;">
        <div style="
        background:#28a745;
        color:white;
        padding:20px;
        text-align:center;
        border-radius:15px;
        font-size:22px;
        font-weight:bold;">
        🚀 ЗАПУСТИТЬ НАВИГАТОР
        </div>
        </a>
        """,
        unsafe_allow_html=True
    )

# ---------------- СПИСОК ----------------

    with st.expander("План маршрута"):

        st.write(f"🚩 Старт: {s_name}")

        for i, p in enumerate(stops, 1):

            text = p["name"]

            if p["close"]:
                text += f" (до {p['close']}:00)"

            st.write(f"{i}. {text}")

        st.write("🏁 Возврат к старту")
