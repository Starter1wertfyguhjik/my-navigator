import streamlit as st
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import pytz
from streamlit_searchbox import st_searchbox # Новая библиотека

st.set_page_config(page_title="Smart Navigator MSK", layout="wide")

# Инициализация списка точек в сессии
if "points_list" not in st.session_state:
    st.session_state.points_list = []
if "route_data" not in st.session_state:
    st.session_state.route_data = None

st.title("🚗 Умный Навигатор с живым поиском")

# ---------------- ФУНКЦИЯ ПОИСКА ДЛЯ АВТОКОМПЛИТА ----------------
def search_addresses(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": search_term, "format": "json", "limit": 8, "countrycodes": "ru"}
    headers = {"User-Agent": "SmartNav_Pro_Search"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        return [x["display_name"] for x in r.json()]
    except:
        return []

# ---------------- КЭШИРОВАННЫЙ ГЕОКОДЕР ----------------
@st.cache_data
def get_coordinates_cached(address):
    try:
        geolocator = Nominatim(user_agent="smart_nav_pro_2026")
        loc = geolocator.geocode(address, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, loc.address
    except:
        pass
    return None

# ---------------- SIDEBAR ----------------
with st.sidebar:
    st.header("📍 Настройка маршрута")

    # 1. ЖИВОЙ ПОИСК ДЛЯ СТАРТА
    st.write("**Точка старта:**")
    start_addr = st_searchbox(
        search_addresses,
        key="start_search",
        placeholder="Начните вводить адрес старта...",
        default="Москва, Красная площадь"
    )

    st.divider()

    # 2. ДОБАВЛЕНИЕ ТОЧЕК ЧЕРЕЗ ЖИВОЙ ПОИСК
    st.write("**Добавить точку назначения:**")
    new_point_addr = st_searchbox(
        search_addresses,
        key="point_search",
        placeholder="Введите адрес точки..."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        close_h = st.number_input("Закрытие (час)", 0, 23, 18)
    with col2:
        if st.button("➕ Добавить"):
            if new_point_addr:
                st.session_state.points_list.append({"addr": new_point_addr, "close": close_h})
                st.toast(f"Добавлено: {new_point_addr[:30]}...")

    # Отображение списка добавленных точек
    if st.session_state.points_list:
        st.write("**Ваш список точек:**")
        for i, p in enumerate(st.session_state.points_list):
            st.caption(f"{i+1}. {p['addr'][:40]}... | {p['close']}:00")
        
        if st.button("🗑 Очистить список"):
            st.session_state.points_list = []
            st.rerun()

    st.divider()
    btn_calc = st.button("🚀 ПОСТРОИТЬ МАРШРУТ", use_container_width=True)

# ---------------- ОПТИМИЗАЦИЯ ----------------
def optimize_route(start, points_list):
    speed = 30
    tz_moscow = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz_moscow)
    current_pos = start
    ordered = []
    temp = points_list[:]

    while temp:
        best = None
        min_score = float('inf')
        for p in temp:
            dist = geodesic(current_pos, (p["lat"], p["lon"])).km
            travel_hours = dist / speed
            arrival = now + timedelta(hours=travel_hours)

            if p["close"]:
                close_time = now.replace(hour=p["close"], minute=0, second=0, microsecond=0)
                remaining = (close_time - arrival).total_seconds() / 3600
                score = dist + (remaining * 10) if remaining >= 0 else 2000 + dist
            else:
                score = dist + 200

            if score < min_score:
                min_score = score
                best = p

        chosen = best if best else temp[0]
        dist_to_chosen = geodesic(current_pos, (chosen["lat"], chosen["lon"])).km
        now += timedelta(hours=dist_to_chosen / speed)
        current_pos = (chosen["lat"], chosen["lon"])
        ordered.append(chosen)
        temp.remove(chosen)

    return ordered, datetime.now(tz_moscow).strftime("%H:%M")

# ---------------- ЛОГИКА РАСЧЕТА ----------------
if btn_calc:
    if not start_addr:
        st.error("Укажите адрес старта")
    elif not st.session_state.points_list:
        st.error("Добавьте хотя бы одну точку")
    else:
        start_coords = get_coordinates_cached(start_addr)
        if start_coords:
            points_data = []
            with st.spinner("Геокодирование точек..."):
                for p in st.session_state.points_list:
                    coords = get_coordinates_cached(p["addr"])
                    if coords:
                        points_data.append({"lat": coords[0], "lon": coords[1], "name": coords[2], "close": p["close"]})
            
            if points_data:
                ordered_stops, msk_time = optimize_route((start_coords[0], start_coords[1]), points_data)
                st.session_state.route_data = {"start": start_coords, "stops": ordered_stops, "time": msk_time}
                st.rerun()
        else:
            st.error("Не удалось найти координаты старта")

# ---------------- КАРТА И ВЫВОД ----------------
if st.session_state.route_data:
    res = st.session_state.route_data
    s_lat, s_lon, s_name = res["start"]
    stops = res["stops"]

    st.info(f"🕒 Время выезда (МСК): {res['time']}")

    all_c = [(s_lat, s_lon)] + [(p['lat'], p['lon']) for p in stops] + [(s_lat, s_lon)]
    m = folium.Map(location=[s_lat, s_lon], zoom_start=12)
    folium.PolyLine(all_c, color="#2980b9", weight=5).add_to(m)
    folium.Marker([s_lat, s_lon], icon=folium.Icon(color="red")).add_to(m)
    for i, p in enumerate(stops, 1):
        folium.Marker([p["lat"], p["lon"]], tooltip=f"{i}. {p['name']}", icon=folium.Icon(color="blue")).add_to(m)

    st_folium(m, width="100%", height=500, returned_objects=[], key="map")

    # Кнопка навигации
    origin = f"{s_lat},{s_lon}"
    waypts = "|".join([f"{p['lat']},{p['lon']}" for p in stops])
    google_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={origin}&waypoints={waypts}&travelmode=driving"

    st.markdown(f'<a href="{google_url}" target="_blank"><div style="background:#28a745;color:white;padding:20px;text-align:center;border-radius:15px;font-size:24px;font-weight:bold;">🚀 В НАВИГАТОР</div></a>', unsafe_allow_html=True)
