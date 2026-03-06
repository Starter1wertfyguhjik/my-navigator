import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime

# --- НАСТРОЙКИ ---
MAPBOX_TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ"

st.set_page_config(page_title="Pro Navigator v2.0", layout="wide")

if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор: Реальные дороги + Пробки")

# ---------------- БОКОВАЯ ПАНЕЛЬ ----------------

with st.sidebar:

    st.header("📍 Маршрут")

    start_addr = st.text_input(
        "Ваш адрес (Старт/Финиш)",
        "Москва, Красная площадь"
    )

    dest_raw = st.text_area(
        "Точки через точку с запятой",
        "Москва, Тверская 1; Москва, Новый Арбат 10; Москва, ВДНХ"
    )

    st.write("### ⏰ Время закрытия точек")

    close1 = st.number_input("Точка 1 закрывается (час)", 1, 24, 18)
    close2 = st.number_input("Точка 2 закрывается (час)", 1, 24, 18)
    close3 = st.number_input("Точка 3 закрывается (час)", 1, 24, 18)
    close_times = [close1, close2, close3]

    btn_calc = st.button("🗺️ Построить оптимальный путь")

    st.write("---")
    st.info("Маршрут строится по расстоянию и времени закрытия точек")

# ---------------- ФУНКЦИИ ----------------

def get_coordinates(address):

    try:
        geolocator = Nominatim(user_agent="smart_nav_2026")
        loc = geolocator.geocode(address, timeout=10)

        if loc:
            return (loc.latitude, loc.longitude, loc.address)

    except:
        return None

    return None


def get_mapbox_route(points):

    if MAPBOX_TOKEN == "ВАШ_ТОКЕН_ЗДЕСЬ":
        return None

    coords_str = ";".join([f"{p[1]},{p[0]}" for p in points])

    url = f"https://api.mapbox.com/directions/v5/mapbox/driving-traffic/{coords_str}"

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

# ---------------- ПОСТРОЕНИЕ МАРШРУТА ----------------

if btn_calc:

    with st.spinner("Считаем маршрут..."):

        start_res = get_coordinates(start_addr)

        if start_res:

            points_list = []

            addresses = dest_raw.split(";")

            for i, a in enumerate(addresses):

                coords = get_coordinates(a.strip())

                if coords:

                    close_time = close_times[i] if i < len(close_times) else 24

                    points_list.append({
                        "lat": coords[0],
                        "lon": coords[1],
                        "name": coords[2],
                        "close": close_time
                    })

           ordered = []
temp_pts = points_list[:]

current_pos = (start_res[0], start_res[1])

current_time = datetime.now().hour
speed = 40

while temp_pts:

    candidates = []

    for p in temp_pts:

        dist = geodesic(
            current_pos,
            (p["lat"], p["lon"])
        ).km

        travel_time = dist / speed

        arrival = current_time + travel_time

        # если успеваем
        if arrival <= p["close"]:
            candidates.append((p, dist))

    # если есть доступные точки
    if candidates:

        next_pt = min(candidates, key=lambda x: x[1])[0]

    else:
        # если ни в одну не успеваем — берем ближайшую
        next_pt = min(
            temp_pts,
            key=lambda x: geodesic(
                current_pos,
                (x["lat"], x["lon"])
            ).km
        )

    ordered.append(next_pt)

    dist = geodesic(
        current_pos,
        (next_pt["lat"], next_pt["lon"])
    ).km

    travel_time = dist / speed

    current_time += travel_time

    current_pos = (next_pt["lat"], next_pt["lon"])

    temp_pts.remove(next_pt)

# ---------------- ОТРИСОВКА КАРТЫ ----------------

if st.session_state.route_data:

    data = st.session_state.route_data

    s_lat, s_lon, s_full_name = data["start"]

    stops = data["ordered_stops"]

    all_coords = [(s_lat, s_lon)] + [(p["lat"], p["lon"]) for p in stops] + [(s_lat, s_lon)]

    road_geometry = get_mapbox_route(all_coords)

    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)

    folium.TileLayer(
        tiles="https://{s}.google.com/vt/lyrs=m@221097413,traffic&x={x}&y={y}&z={z}",
        attr="Google Traffic",
        name="Пробки",
        overlay=True,
        subdomains=["mt0","mt1","mt2","mt3"]
    ).add_to(m)

    if road_geometry:

        path = [[p[1], p[0]] for p in road_geometry]

        folium.PolyLine(
            path,
            color="#FF0000",
            weight=6,
            opacity=0.8
        ).add_to(m)

    else:

        folium.PolyLine(
            all_coords,
            color="blue",
            weight=3,
            dash_array="10"
        ).add_to(m)

    folium.Marker(
        [s_lat, s_lon],
        tooltip="СТАРТ / ФИНИШ",
        icon=folium.Icon(color="red", icon="home")
    ).add_to(m)

    for i, p in enumerate(stops, 1):

        folium.Marker(
            [p["lat"], p["lon"]],
            tooltip=f"{i}. {p['name']} (до {p['close']}:00)",
            icon=folium.Icon(color="blue")
        ).add_to(m)

    st_folium(m, width="100%", height=500)

# ---------------- КНОПКА НАВИГАЦИИ ----------------

    origin = f"{s_lat},{s_lon}"

    waypoints = "|".join([f"{p['lat']},{p['lon']}" for p in stops])

    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypoints}&travelmode=driving"

    st.markdown(f"""
    <a href="{google_url}" style="text-decoration: none;">
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

# ---------------- ТЕКСТ МАРШРУТА ----------------

    with st.expander("Посмотреть план маршрута"):

        st.write(f"🚩 **Старт:** {s_full_name}")

        for i, p in enumerate(stops, 1):
            st.write(f"{i}. {p['name']} (до {p['close']}:00)")

        st.write(f"🏁 **Возврат:** {s_full_name}")


